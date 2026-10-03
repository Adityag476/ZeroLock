"""
ZeroLeak — POST /api/investigate
Upload a leaked photo → forensic decode → provenance verdict.
"""

import os, sys, time, uuid, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.db import get_conn
from core.decoder import decode_photo
from core.honey_token import investigate_plaintext_leak, compile_center_paper

router = APIRouter()

UPLOAD_DIR = tempfile.mkdtemp(prefix="zeroleak_uploads_")


class HoneyTokenRequest(BaseModel):
    leaked_text:   str
    paper_id:      Optional[str] = "EXAM-2026-MAIN"
    total_centres: Optional[int] = 50


class HoneyTokenResult(BaseModel):
    investigation_id:     str
    status:               str   # LEAD | INCONCLUSIVE | VERIFIED | INVALID
    message:              str
    implicated_centre_id: Optional[int] = None
    confidence:           float
    separation_margin:    float = 0.0
    tokens_matched_count: int = 0
    tokens_matched:       list[dict] = []
    runner_up_centre_id:  Optional[int] = None
    runner_up_confidence: float = 0.0
    numbers_detected:     list[float] = []
    subline:              Optional[str] = None
    signals:              Optional[dict] = None
    present_signals:      Optional[list[str]] = None
    ranked_centres:       Optional[list[dict]] = None


class InvestigationResult(BaseModel):
    investigation_id: str
    status:           str   # VERIFIED | CORRUPTED | UNKNOWN
    message:          str
    confidence:       float
    centre_id:        Optional[int]   = None
    hall_id:          Optional[int]   = None
    print_num:        Optional[int]   = None
    timestamp:        Optional[int]   = None
    bit_count:        int             = 0
    anchor_found:     bool            = False
    exam_match:       Optional[dict]  = None
    gap_sample:       list[float]     = []
    threshold:        Optional[float] = None
    mode:             Optional[str]   = "fiducial"
    gap_count:        Optional[int]   = None


@router.post("/", response_model=InvestigationResult)
async def investigate(
    file:      UploadFile = File(...),
    debug:     bool = False,
):
    """
    Upload a photograph of a leaked exam paper.
    Returns a forensic provenance verdict.

    Status codes:
      VERIFIED   — watermark decoded, centre/hall/print identified
      CORRUPTED  — partial signal detected but RS decode failed
      UNKNOWN    — no ZeroLeak watermark found
    """
    # Save uploaded file
    suffix = os.path.splitext(file.filename or "photo.jpg")[-1] or ".jpg"
    fd, img_path = tempfile.mkstemp(suffix=suffix, dir=UPLOAD_DIR)
    os.close(fd)
    try:
        with open(img_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        debug_dir = tempfile.mkdtemp(prefix="zl_debug_") if debug else None
        result = decode_photo(img_path, debug_dir=debug_dir)

    finally:
        try:
            os.unlink(img_path)
        except Exception:
            pass

    inv_id = str(uuid.uuid4())
    now    = time.time()

    # Look up matching print instance in DB (if VERIFIED)
    exam_match = None
    if result.get("status") == "VERIFIED":
        conn = get_conn()
        row = conn.execute("""
            SELECT pi.*, e.name as exam_name
            FROM print_instances pi
            JOIN exams e ON pi.exam_id = e.id
            WHERE pi.centre_id = ? AND pi.hall_id = ? AND pi.print_num = ?
            ORDER BY pi.authorized_at DESC LIMIT 1
        """, (
            result.get("centre_id"),
            result.get("hall_id"),
            result.get("print_num"),
        )).fetchone()
        conn.close()
        if row:
            exam_match = {
                "exam_name":    row["exam_name"],
                "exam_id":      row["exam_id"],
                "instance_id":  row["id"],
                "authorized_at": row["authorized_at"],
            }

    # Persist investigation record
    conn = get_conn()
    conn.execute("""
        INSERT INTO investigations
          (id, uploaded_at, image_filename, status, centre_id, hall_id, print_num,
           timestamp_epoch, confidence, bit_count, anchor_found, message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        inv_id, now, file.filename,
        result.get("status", "UNKNOWN"),
        result.get("centre_id"),
        result.get("hall_id"),
        result.get("print_num"),
        result.get("timestamp"),
        result.get("confidence", 0.0),
        result.get("bit_count", 0),
        1 if result.get("anchor_found") else 0,
        result.get("message", ""),
    ))
    conn.commit()
    conn.close()

    return InvestigationResult(
        investigation_id=inv_id,
        status=result.get("status", "UNKNOWN"),
        message=result.get("message", "No ZeroLeak watermark detected"),
        confidence=float(result.get("confidence", 0.0)),
        centre_id=result.get("centre_id"),
        hall_id=result.get("hall_id"),
        print_num=result.get("print_num"),
        timestamp=result.get("timestamp"),
        bit_count=int(result.get("bit_count", 0)),
        anchor_found=bool(result.get("anchor_found", False)),
        exam_match=exam_match,
        gap_sample=result.get("gap_sample", []),
        threshold=result.get("threshold"),
        mode=result.get("mode", "fiducial"),
        gap_count=result.get("gap_count", result.get("bit_count", 0)),
    )


@router.get("/history")
def investigation_history(limit: int = 20):
    """List recent investigations."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM investigations ORDER BY uploaded_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/honey-token", response_model=HoneyTokenResult)
async def investigate_honey_token(payload: HoneyTokenRequest):
    """
    Investigate leaked plaintext questions (e.g. retyped in Telegram / WhatsApp).
    Dual-channel inspector: scores both number-profile match and swap-vector match.
    Reports centre, confidence, and statistical separation margin.
    """
    from core.variant_engine import inspect_variant_text
    import json

    conn = get_conn()
    exam_row = None
    if payload.paper_id:
        exam_row = conn.execute("SELECT * FROM exams WHERE id = ?", (payload.paper_id,)).fetchone()
    if not exam_row:
        exam_row = conn.execute("SELECT * FROM exams ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()

    questions_to_use = []
    if exam_row:
        q_raw = exam_row["questions_json"] if "questions_json" in exam_row.keys() else None
        if q_raw:
            try:
                questions_to_use = json.loads(q_raw)
            except Exception:
                questions_to_use = []

    total_c = payload.total_centres or 50
    cids = list(range(1, total_c + 1))
    
    exam_secret = (exam_row["exam_secret"] if exam_row and "exam_secret" in exam_row.keys() else None) or None

    # 1. Run variant inspector across all present signals
    var_res = inspect_variant_text(
        leaked_text=payload.leaked_text,
        exam_id=payload.paper_id or "EXAM-2026-MAIN",
        questions=questions_to_use,
        centre_ids=cids,
        exam_secret=exam_secret,
    )

    # 2. Run legacy numerical template inspector
    legacy_res = investigate_plaintext_leak(
        leaked_text=payload.leaked_text,
        paper_id=payload.paper_id or "EXAM-2026-MAIN",
        total_registered_centres=total_c,
    )

    sep = float(var_res.get("separation_margin", 0.0))
    top_cid = var_res.get("implicated_centre_id")
    is_lead = (
        var_res.get("status") in ("LEAD", "VERIFIED")
        and sep >= 50.0
        and top_cid is not None
        and top_cid in cids
    )

    if is_lead:
        status = "LEAD"
        cid = top_cid
        conf = float(var_res.get("confidence", 0.0))
        msg = f"INVESTIGATIVE LEAD (not proof): Centre #{cid} · margin +{round(sep, 1)}%"
        subline = "Corroborate with unlock timing, print custodian, and access logs before action."
        runner_cid = var_res.get("runner_up_centre_id")
        runner_conf = float(var_res.get("runner_up_score", 0.0))
        tokens_count = int(var_res.get("swap_matches", 0) + var_res.get("number_matches", 0))
        tokens = []
        numbers_found = []
        signals = var_res.get("signals", {})
        present_signals = var_res.get("present_signals", [])
        ranked_centres = var_res.get("ranked_centres", [])
    elif legacy_res.get("status") == "VERIFIED" and legacy_res.get("implicated_centre_id") in cids:
        status = "LEAD"
        cid = legacy_res.get("implicated_centre_id")
        conf = float(legacy_res.get("confidence", 0.0))
        runner_conf = float(legacy_res.get("runner_up_confidence", 0.0))
        sep = max(0.0, round(conf - runner_conf, 1))
        msg = f"INVESTIGATIVE LEAD (not proof): Centre #{cid} · margin +{round(sep, 1)}%"
        subline = "Corroborate with unlock timing, print custodian, and access logs before action."
        runner_cid = legacy_res.get("runner_up_centre_id")
        tokens_count = int(legacy_res.get("tokens_matched_count", 0))
        tokens = legacy_res.get("tokens_matched", [])
        numbers_found = legacy_res.get("numbers_detected", [])
        signals = {}
        present_signals = []
        ranked_centres = []
    else:
        status = "INCONCLUSIVE"
        cid = None
        conf = 0.0
        sep = 0.0
        msg = "No conclusive textual match — no attribution made."
        subline = ""
        runner_cid = None
        runner_conf = 0.0
        tokens_count = 0
        tokens = []
        numbers_found = legacy_res.get("numbers_detected", [])
        signals = var_res.get("signals", {})
        present_signals = var_res.get("present_signals", [])
        ranked_centres = var_res.get("ranked_centres", [])

    inv_id = str(uuid.uuid4())
    now = time.time()

    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO investigations
              (id, uploaded_at, image_filename, status, centre_id, hall_id, print_num,
               timestamp_epoch, confidence, bit_count, anchor_found, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inv_id, now, "retyped_telegram_leak.txt",
            status, cid, None, None, int(now),
            conf / 100.0, tokens_count, 0, msg,
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass

    return HoneyTokenResult(
        investigation_id=inv_id,
        status=status,
        message=msg,
        implicated_centre_id=cid,
        confidence=conf,
        separation_margin=sep,
        tokens_matched_count=tokens_count,
        tokens_matched=tokens,
        runner_up_centre_id=runner_cid,
        runner_up_confidence=runner_conf,
        numbers_detected=numbers_found,
        subline=subline,
        signals=signals,
        present_signals=present_signals,
        ranked_centres=ranked_centres,
    )


@router.get("/honey-token/sample/{centre_id}")
def get_honey_token_sample(centre_id: int):
    """Returns sample questions and simulated leak text for testing."""
    questions = compile_center_paper(centre_id=centre_id)
    simulated_leak = (
        f"[Intercepted Transmission — Channel #NEET_LEAKS]\n"
        f"Q1: {questions[0]['text']}\n"
        f"Q2: {questions[1]['text']}\n"
        f"Fast answer needed!! 5 mins left!"
    )
    return {
        "centre_id": centre_id,
        "questions": questions,
        "simulated_leak": simulated_leak,
    }

