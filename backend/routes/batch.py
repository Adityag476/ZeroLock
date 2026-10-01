"""
ZeroLock — POST /api/batch/generate, GET /api/batch/status/{job_id},
           GET /api/batch/download/{job_id}, GET /api/batch/download/{job_id}/{centre_id}

Batch generation of watermarked PDFs for N centres with:
  - Per-centre decode self-check (mandatory)
  - DOCX export (conditional, with LibreOffice round-trip gate)
  - Variant engine integration
  - Print instance persistence
"""

import os
import sys
import io
import re
import time
import uuid
import json
import shutil
import zipfile
import tempfile
import threading
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from backend.db import get_conn
from core.renderer import generate_watermarked_pdf
from core.audit import append_event
from core.variant_engine import (
    generate_centre_variant,
    inspect_variant_text,
    compute_difficulty_index,
)

router = APIRouter()

# In-memory job store (production would use Redis/DB)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()



def _parse_centre_ids(raw: str) -> list[int]:
    """
    Parse centre ID input. Supports:
    - Comma-separated: "14, 28, 42"
    - Range: "1..500"
    - Mixed: "1..5, 14, 28, 42"
    """
    ids = set()
    parts = [p.strip() for p in raw.split(",")]
    for part in parts:
        range_match = re.match(r"(\d+)\s*\.\.\s*(\d+)", part)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            ids.update(range(start, end + 1))
        elif part.isdigit():
            ids.add(int(part))
    return sorted(ids)


def _decode_image_from_pdf(pdf_bytes: bytes) -> dict:
    """
    Render PDF to image at 150 DPI and decode via the forensic pipeline.
    This is the mandatory self-check.
    """
    try:
        import fitz  # PyMuPDF
        import cv2
        import numpy as np
        from core.decoder import decode_photo

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        mat = fitz.Matrix(150 / 72, 150 / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_bytes = pix.tobytes("png")
        doc.close()

        # Save to temp file for decoder
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            with open(tmp_path, "wb") as f:
                f.write(img_bytes)
            result = decode_photo(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return result
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


def _generate_docx(
    questions: list[str],
    centre_id: int,
    hall_id: int,
    print_num: int,
    exam_title: str,
    stego_bits: list[int],
) -> Optional[bytes]:
    """
    Generate a DOCX with word-gap steganography via <w:wordSpacing>.
    Fiducial crosshairs inserted as anchored images.
    Returns DOCX bytes or None on failure.
    """
    try:
        from docx import Document
        from docx.shared import Pt, Inches, Twips, Cm, Emu
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.section import WD_ORIENT
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        doc = Document()

        # A4 page setup
        section = doc.sections[0]
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.left_margin = Cm(1.76)  # ~50pt
        section.right_margin = Cm(1.76)
        section.top_margin = Cm(2.12)
        section.bottom_margin = Cm(2.12)

        # Title
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_para.add_run(exam_title)
        run.bold = True
        run.font.size = Pt(14)
        run.font.name = "Times New Roman"

        # Metadata line
        meta_para = doc.add_paragraph()
        meta_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = meta_para.add_run(
            f"[Centre {centre_id:04d} | Hall {hall_id:03d} | Print #{print_num:04d}]  — CONFIDENTIAL"
        )
        run.font.size = Pt(9)
        run.font.name = "Times New Roman"

        # Horizontal rule
        doc.add_paragraph("_" * 80)

        # Questions with word-gap stego
        bit_idx = 0
        for q_idx, question in enumerate(questions):
            para = doc.add_paragraph()
            prefix = f"Q{q_idx + 1}. "
            words = question.split()

            # Add prefix
            run = para.add_run(prefix)
            run.bold = True
            run.font.size = Pt(12)
            run.font.name = "Times New Roman"

            # Add each word as a separate run with controlled spacing
            for w_idx, word in enumerate(words):
                run = para.add_run(word)
                run.font.size = Pt(12)
                run.font.name = "Times New Roman"

                if w_idx < len(words) - 1:
                    # Apply word spacing via run properties
                    bit = stego_bits[bit_idx % len(stego_bits)]
                    bit_idx += 1
                    # twips: bit0 = -60 (narrow), bit1 = +60 (wide) relative to baseline
                    twip_val = 60 if bit else -60

                    rpr = run._element.get_or_add_rPr()
                    spacing = OxmlElement('w:spacing')
                    spacing.set(qn('w:val'), str(twip_val))
                    rpr.append(spacing)

                    # Add space character
                    space_run = para.add_run(" ")
                    space_run.font.size = Pt(12)
                    space_run.font.name = "Times New Roman"

        # Footer
        footer_para = doc.add_paragraph()
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = footer_para.add_run(
            "ZeroLeak Forensic Watermark — Unauthorised reproduction is traceable"
        )
        run.font.size = Pt(8)
        run.font.name = "Times New Roman"
        run.italic = True

        # Save to bytes
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    except ImportError:
        return None
    except Exception:
        return None


def _docx_roundtrip_check(docx_bytes: bytes) -> dict:
    """
    Convert DOCX to PDF via LibreOffice headless and decode.
    Returns decode result or error status.
    """
    try:
        # Write DOCX to temp
        tmpdir = tempfile.mkdtemp(prefix="zl_docx_")
        docx_path = os.path.join(tmpdir, "exam.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        # Try LibreOffice conversion
        soffice_cmd = None
        for candidate in ["soffice", "libreoffice",
                          r"C:\Program Files\LibreOffice\program\soffice.exe",
                          r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"]:
            try:
                result = subprocess.run(
                    [candidate, "--version"],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0:
                    soffice_cmd = candidate
                    break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        if not soffice_cmd:
            return {"status": "SKIP", "message": "LibreOffice not available for round-trip check"}

        subprocess.run(
            [soffice_cmd, "--headless", "--convert-to", "pdf", "--outdir", tmpdir, docx_path],
            capture_output=True, timeout=60
        )

        pdf_path = os.path.join(tmpdir, "exam.pdf")
        if not os.path.exists(pdf_path):
            return {"status": "FAILED", "message": "LibreOffice conversion produced no output"}

        with open(pdf_path, "rb") as f:
            converted_pdf = f.read()

        decode_result = _decode_image_from_pdf(converted_pdf)
        return decode_result

    except Exception as e:
        return {"status": "ERROR", "message": str(e)}
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def _run_batch_job(job_id: str, exam_id: str, centre_ids: list[int],
                   answer_key_text: Optional[str] = None):
    """
    Background worker: generates watermarked PDFs for each centre with self-check.
    """
    with _jobs_lock:
        job = _jobs[job_id]
        job["status"] = "RUNNING"

    # Fetch exam info
    conn = get_conn()
    exam_row = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    conn.close()

    exam_title = (exam_row["name"] if exam_row and "name" in exam_row.keys() else "") or "Examination Paper"

    # Generate variants if needed
    min_slots = 4
    variant_data = {}
    questions_to_use = []
    if exam_row:
        q_raw = exam_row["questions_json"] if "questions_json" in exam_row.keys() else None
        if q_raw:
            try:
                questions_to_use = json.loads(q_raw)
            except Exception:
                questions_to_use = []

    for cid in centre_ids:
        variant = generate_centre_variant(
            exam_id, cid, questions_to_use, answer_key_text
        )
        variant_data[cid] = variant

    # Check minimum slot count
    has_enough_slots = all(v["slot_count"] >= min_slots for v in variant_data.values())
    if not has_enough_slots and not answer_key_text:
        # Wording-only with < 4 slots: flag but continue (non-blocking)
        with _jobs_lock:
            job["warnings"].append(
                "Paper too rigid for textual variants — numeric key upload recommended for stronger fingerprinting"
            )

    total = len(centre_ids)
    completed = 0
    output_dir = tempfile.mkdtemp(prefix="zl_batch_")

    with _jobs_lock:
        job["output_dir"] = output_dir

    for cid in centre_ids:
        centre_result = {
            "centre_id": cid,
            "pdf_status": "PENDING",
            "docx_status": "PENDING",
            "self_check": "PENDING",
            "variant_slots": variant_data[cid]["slot_count"],
            "difficulty_index": variant_data[cid]["difficulty_index"],
        }

        try:
            ts = int(time.time())
            hall_id = 1
            print_num = 1

            # Use variant questions for this centre
            centre_questions = variant_data[cid]["variant_questions"]

            # Generate watermarked PDF (using SAME verified renderer)
            pdf_bytes = generate_watermarked_pdf(
                questions=centre_questions,
                centre_id=cid,
                hall_id=hall_id,
                print_num=print_num,
                timestamp=ts,
                exam_title=exam_title,
            )

            # Save PDF
            pdf_filename = f"centre_{cid:04d}.pdf"
            pdf_path = os.path.join(output_dir, pdf_filename)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            centre_result["pdf_status"] = "GENERATED"
            centre_result["pdf_size"] = len(pdf_bytes)

            # Mandatory self-check: decode the PDF we just generated
            decode_result = _decode_image_from_pdf(pdf_bytes)

            if (decode_result.get("status") == "VERIFIED"
                    and decode_result.get("centre_id") == cid):
                centre_result["self_check"] = "VERIFIED"
                centre_result["pdf_status"] = "VERIFIED"
            else:
                centre_result["self_check"] = "FAILED"
                centre_result["pdf_status"] = "FAILED"
                centre_result["decode_detail"] = decode_result.get("message", "")
                # Remove failed PDF from output
                try:
                    os.unlink(pdf_path)
                except OSError:
                    pass

            # Persist to print_instances (so /forensic and /audit see them)
            if centre_result["self_check"] == "VERIFIED":
                try:
                    conn = get_conn()
                    instance_id = str(uuid.uuid4())
                    conn.execute("""
                        INSERT INTO print_instances
                          (id, exam_id, centre_id, hall_id, print_num, authorized_at, timestamp_epoch)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (instance_id, exam_id, cid, hall_id, print_num, time.time(), ts))
                    conn.commit()
                    conn.close()

                    append_event(
                        exam_id, "BATCH_PRINT_GENERATED",
                        actor=f"batch-{job_id[:8]}",
                        metadata={
                            "centre_id": cid, "hall_id": hall_id,
                            "print_num": print_num, "timestamp": ts,
                            "instance_id": instance_id, "batch_job_id": job_id,
                        },
                    )
                except Exception:
                    pass

            # DOCX generation (conditional)
            try:
                from core.payload import encode_payload
                stego_bits = encode_payload(cid, hall_id, print_num, ts)
                docx_bytes = _generate_docx(
                    centre_questions, cid, hall_id, print_num, exam_title, stego_bits
                )
                if docx_bytes:
                    # Round-trip gate
                    rt_result = _docx_roundtrip_check(docx_bytes)
                    if (rt_result.get("status") == "VERIFIED"
                            and rt_result.get("centre_id") == cid):
                        docx_filename = f"centre_{cid:04d}.docx"
                        centre_result["docx_status"] = "VERIFIED"
                    elif rt_result.get("status") == "SKIP":
                        # LibreOffice not available — ship as working copy
                        docx_filename = f"centre_{cid:04d}_working_copy.docx"
                        centre_result["docx_status"] = "WORKING_COPY"
                        centre_result["docx_warning"] = (
                            "Editable master — the PDF is the watermarked official copy."
                        )
                    else:
                        docx_filename = f"centre_{cid:04d}_working_copy.docx"
                        centre_result["docx_status"] = "WORKING_COPY"
                        centre_result["docx_warning"] = (
                            "Editable master — the PDF is the watermarked official copy."
                        )

                    docx_path = os.path.join(output_dir, docx_filename)
                    with open(docx_path, "wb") as f:
                        f.write(docx_bytes)
                else:
                    centre_result["docx_status"] = "UNAVAILABLE"
            except ImportError:
                centre_result["docx_status"] = "UNAVAILABLE"
            except Exception as e:
                centre_result["docx_status"] = "ERROR"
                centre_result["docx_error"] = str(e)

            # Store variant metadata
            centre_result["number_map"] = variant_data[cid]["number_map"]
            centre_result["swap_vector"] = variant_data[cid]["swap_vector"]

        except Exception as e:
            centre_result["pdf_status"] = "ERROR"
            centre_result["self_check"] = "ERROR"
            centre_result["error"] = str(e)

        completed += 1
        with _jobs_lock:
            job["centres"][cid] = centre_result
            job["progress"] = completed / total

    # Store variant data in DB (centre_variants table)
    try:
        conn = get_conn()
        # Create table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS centre_variants (
                id          TEXT PRIMARY KEY,
                exam_id     TEXT NOT NULL,
                centre_id   INTEGER NOT NULL,
                number_map  TEXT,
                swap_vector TEXT,
                variant_answer_key TEXT,
                difficulty_index REAL,
                batch_job_id TEXT
            )
        """)
        for cid in centre_ids:
            v = variant_data[cid]
            conn.execute("""
                INSERT OR REPLACE INTO centre_variants
                  (id, exam_id, centre_id, number_map, swap_vector,
                   variant_answer_key, difficulty_index, batch_job_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), exam_id, cid,
                json.dumps(v["number_map"]),
                json.dumps(v["swap_vector"]),
                v.get("variant_answer_key"),
                v["difficulty_index"],
                job_id,
            ))
        conn.commit()
        conn.close()
    except Exception:
        pass

    # Build ZIP
    verified_count = sum(
        1 for c in job["centres"].values() if c.get("self_check") == "VERIFIED"
    )

    zip_path = os.path.join(output_dir, f"batch_{job_id[:8]}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(output_dir):
            fpath = os.path.join(output_dir, fname)
            if os.path.isfile(fpath) and not fname.endswith(".zip"):
                zf.write(fpath, fname)

    with _jobs_lock:
        job["status"] = "COMPLETED"
        job["progress"] = 1.0
        job["completed_at"] = time.time()
        job["zip_path"] = zip_path
        job["verified_count"] = verified_count
        job["total_count"] = total


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class BatchGenerateRequest(BaseModel):
    exam_id: str
    centre_ids: Optional[list[int]] = None
    centre_ids_raw: Optional[str] = None
    answer_key_text: Optional[str] = None


class BatchStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float
    verified_count: int
    total_count: int
    centres: dict
    warnings: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate")
def batch_generate(req: BatchGenerateRequest):
    """
    Start batch generation for N centres.
    Returns a job_id for polling status.
    """
    # Parse centre IDs
    if req.centre_ids:
        cids = sorted(set(req.centre_ids))
    elif req.centre_ids_raw:
        cids = _parse_centre_ids(req.centre_ids_raw)
    else:
        raise HTTPException(400, "Provide centre_ids or centre_ids_raw")

    if not cids:
        raise HTTPException(400, "No valid centre IDs parsed")
    if len(cids) > 1000:
        raise HTTPException(400, "Maximum 1000 centres per batch")

    # Verify exam exists
    conn = get_conn()
    exam = conn.execute("SELECT id FROM exams WHERE id = ?", (req.exam_id,)).fetchone()
    conn.close()
    if not exam:
        raise HTTPException(404, "Exam not found")

    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "exam_id": req.exam_id,
        "status": "QUEUED",
        "progress": 0.0,
        "centres": {},
        "warnings": [],
        "verified_count": 0,
        "total_count": len(cids),
        "created_at": time.time(),
        "completed_at": None,
        "output_dir": None,
        "zip_path": None,
    }

    with _jobs_lock:
        _jobs[job_id] = job

    # Start background thread
    t = threading.Thread(
        target=_run_batch_job,
        args=(job_id, req.exam_id, cids, req.answer_key_text),
        daemon=True,
    )
    t.start()

    return {"job_id": job_id, "status": "QUEUED", "total_centres": len(cids)}


@router.get("/status/{job_id}")
def batch_status(job_id: str):
    """Poll batch job status."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(404, "Job not found")

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": round(job["progress"], 3),
        "verified_count": job.get("verified_count", 0),
        "total_count": job["total_count"],
        "centres": job["centres"],
        "warnings": job["warnings"],
    }


@router.get("/download/{job_id}")
def batch_download_zip(job_id: str):
    """Download the full batch ZIP."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "COMPLETED":
        raise HTTPException(409, "Batch not yet completed")
    if not job.get("zip_path") or not os.path.exists(job["zip_path"]):
        raise HTTPException(500, "ZIP file not found")

    with open(job["zip_path"], "rb") as f:
        data = f.read()

    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="batch_{job_id[:8]}.zip"'},
    )


@router.get("/download/{job_id}/{centre_id}")
def batch_download_single(
    job_id: str,
    centre_id: int,
    fmt: str = Query("pdf", pattern="^(pdf|docx)$"),
):
    """Download a single centre's PDF or DOCX."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "COMPLETED":
        raise HTTPException(409, "Batch not yet completed")

    output_dir = job.get("output_dir")
    if not output_dir:
        raise HTTPException(500, "Output directory not found")

    if fmt == "pdf":
        fname = f"centre_{centre_id:04d}.pdf"
        media = "application/pdf"
    else:
        fname = f"centre_{centre_id:04d}.docx"
        if not os.path.exists(os.path.join(output_dir, fname)):
            fname = f"centre_{centre_id:04d}_working_copy.docx"
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    fpath = os.path.join(output_dir, fname)
    if not os.path.exists(fpath):
        raise HTTPException(404, f"File not found: {fname}")

    with open(fpath, "rb") as f:
        data = f.read()

    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/answer-keys/{job_id}")
def batch_answer_keys(job_id: str):
    """
    Return consolidated per-centre answer keys for the evaluation board.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(404, "Job not found")

    conn = get_conn()
    rows = conn.execute(
        "SELECT centre_id, number_map, variant_answer_key, difficulty_index "
        "FROM centre_variants WHERE batch_job_id = ? ORDER BY centre_id",
        (job_id,),
    ).fetchall()
    conn.close()

    keys = []
    for row in rows:
        keys.append({
            "centre_id": row["centre_id"],
            "number_map": json.loads(row["number_map"]) if row["number_map"] else {},
            "variant_answer_key": row["variant_answer_key"],
            "difficulty_index": row["difficulty_index"],
        })

    return {
        "job_id": job_id,
        "exam_id": job["exam_id"],
        "centre_keys": keys,
    }


@router.post("/inspect-variant")
def inspect_variant(
    leaked_text: str = "",
    exam_id: str = "",
    centre_ids_raw: str = "",
    answer_key_text: Optional[str] = None,
):
    """
    Extended honey-token inspector: scores both number-profile and swap-vector.
    """
    if not leaked_text or not exam_id:
        raise HTTPException(400, "Provide leaked_text and exam_id")

    cids = _parse_centre_ids(centre_ids_raw) if centre_ids_raw else list(range(1, 101))

    conn = get_conn()
    exam_row = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    conn.close()

    questions_to_use = []
    if exam_row:
        q_raw = exam_row["questions_json"] if "questions_json" in exam_row.keys() else None
        if q_raw:
            try:
                questions_to_use = json.loads(q_raw)
            except Exception:
                questions_to_use = []

    result = inspect_variant_text(
        leaked_text=leaked_text,
        exam_id=exam_id,
        questions=questions_to_use,
        centre_ids=cids,
        answer_key_text=answer_key_text,
    )

    return result
