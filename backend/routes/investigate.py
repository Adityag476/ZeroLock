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
    status:               str   # VERIFIED | INCONCLUSIVE | INVALID
    message:              str
    implicated_centre_id: Optional[int] = None
    confidence:           float
    tokens_matched_count: int = 0
    tokens_matched:       list[dict] = []
    runner_up_centre_id:  Optional[int] = None
    runner_up_confidence: float = 0.0
    numbers_detected:     list[float] = []


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
    Analyzes numerical parameters and correlates against all Centre signatures.
    """
    res = investigate_plaintext_leak(
        leaked_text=payload.leaked_text,
        paper_id=payload.paper_id or "EXAM-2026-MAIN",
        total_registered_centres=payload.total_centres or 50,
    )
    inv_id = str(uuid.uuid4())
    now    = time.time()

    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO investigations
              (id, uploaded_at, image_filename, status, centre_id, hall_id, print_num,
               timestamp_epoch, confidence, bit_count, anchor_found, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inv_id, now, "retyped_telegram_leak.txt",
            res.get("status", "INCONCLUSIVE"),
            res.get("implicated_centre_id"),
            None, None, int(now),
            float(res.get("confidence", 0.0)) / 100.0,
            int(res.get("tokens_matched_count", 0)),
            0,
            res.get("message", ""),
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass

    return HoneyTokenResult(
        investigation_id=inv_id,
        status=res.get("status", "INCONCLUSIVE"),
        message=res.get("message", ""),
        implicated_centre_id=res.get("implicated_centre_id"),
        confidence=float(res.get("confidence", 0.0)),
        tokens_matched_count=int(res.get("tokens_matched_count", 0)),
        tokens_matched=res.get("tokens_matched", []),
        runner_up_centre_id=res.get("runner_up_centre_id"),
        runner_up_confidence=float(res.get("runner_up_confidence", 0.0)),
        numbers_detected=res.get("numbers_detected", []),
    )


@router.get("/honey-token/sample/{centre_id}")
def get_honey_token_sample(centre_id: int):
    """Returns sample questions and simulated leak text for testing."""
    questions = compile_center_paper(centre_id=centre_id)
    simulated_leak = (
        f"🚨 LEAK ALERT [Telegram Channel #NEET_LEAKS]\n"
        f"Q1: {questions[0]['text']}\n"
        f"Q2: {questions[1]['text']}\n"
        f"Fast answer needed!! 5 mins left!"
    )
    return {
        "centre_id": centre_id,
        "questions": questions,
        "simulated_leak": simulated_leak,
    }

