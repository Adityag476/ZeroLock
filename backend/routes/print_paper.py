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

    exam_secret = row["exam_secret"] if "exam_secret" in row.keys() else None
    answer_key_text = row["answer_key_text"] if "answer_key_text" in row.keys() else None

    # Generate centre-specific variant with keyed tracers (unique wording, question order, option permutations, canaries, and numbers)
    from core.variant_engine import generate_centre_variant
    variant = generate_centre_variant(
        exam_id=exam_id,
        centre_id=centre_id,
        questions=questions,
        answer_key_text=answer_key_text,
        exam_secret=exam_secret,
    )
    centre_questions = variant["variant_questions"]

    # Store variant metadata in centre_variants so Forensic Tracer can trace both text and photo leaks
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS centre_variants (
                id          TEXT PRIMARY KEY,
                exam_id     TEXT NOT NULL,
                centre_id   INTEGER NOT NULL,
                number_map  TEXT,
                swap_vector TEXT,
                option_perm TEXT,
                q_order     TEXT,
                canary_vector TEXT,
                keyed       INTEGER,
                variant_answer_key TEXT,
                difficulty_index REAL,
                batch_job_id TEXT
            )
        """)
        existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(centre_variants)").fetchall()]
        for col_name, col_type in [
            ("option_perm", "TEXT"),
            ("q_order", "TEXT"),
            ("canary_vector", "TEXT"),
            ("keyed", "INTEGER"),
        ]:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE centre_variants ADD COLUMN {col_name} {col_type}")

        conn.execute("""
            INSERT OR REPLACE INTO centre_variants
              (id, exam_id, centre_id, number_map, swap_vector,
               option_perm, q_order, canary_vector, keyed,
               variant_answer_key, difficulty_index, batch_job_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()), exam_id, centre_id,
            json.dumps(variant.get("number_map", {})),
            json.dumps(variant.get("swap_vector", [])),
            json.dumps(variant.get("option_perm", {})),
            json.dumps(variant.get("q_order", [])),
            json.dumps(variant.get("canary_vector", [])),
            1 if variant.get("keyed") else 0,
            variant.get("variant_answer_key"),
            variant.get("difficulty_index", 1.0),
            "custodian_jit",
        ))
    except Exception:
        pass

    # Generate watermarked PDF using centre-specific variant questions (carries distinct 15/9pt physical spacing for this centre)
    exam_title = row["name"]
    pdf_bytes = generate_watermarked_pdf(
        questions=centre_questions,
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
