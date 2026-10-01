import os, sys, time, uuid, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.db import get_conn
from core.renderer import generate_watermarked_pdf
from core.audit import append_event
from core.crypto import decrypt_pdf

router = APIRouter()


@router.get("/{exam_id}")
def print_exam(
    exam_id:   str,
    centre_id: int = Query(...),
    hall_id:   int = Query(...),
):
    """
    JIT generate a centre-specific watermarked PDF.
    Requires exam to be in AUTHORIZED or SEALED (past release time) status.
    Increments print counter and logs to audit trail.
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Exam not found")

    now = time.time()
    if now < row["release_time"] and row["status"] not in ("AUTHORIZED",):
        conn.close()
        raise HTTPException(403, "TIMELOCK: paper not yet released")

    # Load questions parsed from uploaded exam document
    questions_raw = row["questions_json"] if "questions_json" in row.keys() else None
    if not questions_raw:
        conn.close()
        raise HTTPException(400, "Exam has no parsed questions. Please re-upload the document.")
    questions = json.loads(questions_raw)

    # Get or compute sequential print number for this centre+hall
    existing = conn.execute(
        "SELECT COUNT(*) as cnt FROM print_instances WHERE exam_id=? AND centre_id=? AND hall_id=?",
        (exam_id, centre_id, hall_id),
    ).fetchone()
    print_num = (existing["cnt"] or 0) + 1
    ts = int(now)

    # Generate watermarked PDF using actual uploaded exam questions
    exam_title = row["name"]
    pdf_bytes = generate_watermarked_pdf(
        questions=questions,
        centre_id=centre_id,
        hall_id=hall_id,
        print_num=print_num,
        timestamp=ts,
        exam_title=exam_title,
    )

    # Log print instance
    instance_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO print_instances
          (id, exam_id, centre_id, hall_id, print_num, authorized_at, timestamp_epoch)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (instance_id, exam_id, centre_id, hall_id, print_num, now, ts))
    conn.execute("UPDATE exams SET status = 'PRINTING' WHERE id = ?", (exam_id,))
    conn.commit()
    conn.close()

    append_event(
        exam_id, "PRINT_GENERATED",
        actor=f"centre-{centre_id}",
        metadata={
            "centre_id": centre_id,
            "hall_id":   hall_id,
            "print_num": print_num,
            "timestamp": ts,
            "instance_id": instance_id,
        },
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="exam_{centre_id}_{hall_id}_{print_num}.pdf"'},
    )
