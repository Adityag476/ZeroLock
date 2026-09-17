"""
ZeroLeak — GET /api/print/{exam_id}
JIT generate a watermarked PDF for the given centre and hall.
"""

import os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.db import get_conn
from core.renderer import generate_watermarked_pdf
from core.audit import append_event
from core.crypto import decrypt_pdf

router = APIRouter()

SAMPLE_QUESTIONS = [
    "Explain the working principle of a digital watermark. How does it differ from a traditional visible watermark? Discuss the trade-offs between robustness and imperceptibility in forensic applications.",
    "A train departs from Station A at 60 km/h and returns from Station B at 40 km/h. Assuming the distance between the stations is constant, calculate the average speed of the entire journey and explain why it is not simply the arithmetic mean.",
    "Describe how Reed-Solomon error correction codes work. Explain why redundancy is necessary when recovering data from a noisy analog channel such as a printed and photographed document.",
    "Define the term homography in the context of computer vision. Show how it is used to perform perspective correction on a photograph of a document taken at an arbitrary angle.",
    "A rectangular block of mass 10 kg rests on a horizontal surface. The coefficient of static friction is 0.4. Calculate the minimum horizontal force required to set it in motion. Take g = 9.8 m/s^2.",
    "Explain the key difference between symmetric encryption such as AES and asymmetric encryption such as RSA. For each, describe a real-world scenario where that scheme would be the preferred choice.",
    "Using integration, find the area enclosed between the parabola y = x^2 and the straight line y = x + 2. Show all intermediate steps and verify your answer geometrically.",
    "Describe Shamir's Secret Sharing scheme. Explain why a threshold k-of-n scheme is more resistant to both collusion and key loss compared with splitting a secret into n equal non-overlapping parts.",
    "The concentration of a drug in the bloodstream follows C(t) = 8e^(-0.5t) mg/L. Calculate the time at which the concentration falls below 1 mg/L and find the total drug exposure over that period.",
    "Compare the OSI model and the TCP/IP model. For each layer of the OSI model identify the closest equivalent in TCP/IP and give one protocol that operates at that layer.",
]


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

    # Get or compute sequential print number for this centre+hall
    existing = conn.execute(
        "SELECT COUNT(*) as cnt FROM print_instances WHERE exam_id=? AND centre_id=? AND hall_id=?",
        (exam_id, centre_id, hall_id),
    ).fetchone()
    print_num = (existing["cnt"] or 0) + 1
    ts = int(now)

    # Generate watermarked PDF
    exam_name = row["name"]
    pdf_bytes = generate_watermarked_pdf(
        questions=SAMPLE_QUESTIONS,
        centre_id=centre_id,
        hall_id=hall_id,
        print_num=print_num,
        timestamp=ts,
        exam_title=exam_name,
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
