"""
ZeroLeak — POST /api/exams
Create and register a new exam paper (encrypt + IPFS + on-chain stub).
"""

import os, sys, time, uuid, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.db import get_conn
from backend.ipfs_client import pin_bytes
import json
from backend.paper_parse import parse_upload, ParseError, CapacityError
from core.crypto import encrypt_pdf, split_key
from core.audit import append_event, init_db

router = APIRouter()


class ExamCreateResponse(BaseModel):
    exam_id:        str
    sha256_plain:   str
    ipfs_cid:       str
    status:         str
    audit_hash:     str
    question_count: int
    preview:        str
    engine:         str


@router.post("/", response_model=ExamCreateResponse)
async def create_exam(
    file:         UploadFile = File(...),
    name:         str = Form(...),
    release_time: float = Form(...),   # Unix epoch seconds
):
    """
    Upload a PDF/DOCX exam paper.
    - Parses document into structured questions with capacity guards
    - Encrypts with AES-256-GCM
    - Splits key via Shamir 3-of-5
    - Pins encrypted blob to IPFS
    - Registers in local DB with SEALED status and parsed questions
    - Appends PAPER_SEALED audit event
    """
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(400, "Empty file")

    filename = file.filename or "paper.pdf"

    # Parse and validate document content
    try:
        parsed = parse_upload(pdf_bytes, filename)
    except (ParseError, CapacityError) as e:
        raise HTTPException(400, detail=str(e))

    exam_title = (name or "").strip() or parsed.get("title", "").strip() or "Secure Examination Paper"
    if len(exam_title) > 60:
        exam_title = exam_title[:57] + "..."

    questions = parsed["questions"]
    questions_json = json.dumps(questions, ensure_ascii=False)
    first_200 = (" ".join(questions))[:200]
    engine = parsed["engine"]

    exam_id = str(uuid.uuid4())
    created_at = time.time()

    # Encrypt
    enc = encrypt_pdf(pdf_bytes)

    # Upload ciphertext to IPFS
    cipher_bytes = (enc["nonce_b64"] + "." + enc["ciphertext_b64"]).encode()
    ipfs_cid = pin_bytes(cipher_bytes, filename=f"{exam_id}.enc")

    # Store in DB
    conn = get_conn()
    conn.execute("""
        INSERT INTO exams
          (id, name, created_at, release_time, status, ipfs_cid, sha256_plain,
           nonce_b64, ciphertext_b64, key_hex, questions_json)
        VALUES (?, ?, ?, ?, 'SEALED', ?, ?, ?, ?, ?, ?)
    """, (
        exam_id, exam_title, created_at, release_time, ipfs_cid,
        enc["sha256_plain"], enc["nonce_b64"], enc["ciphertext_b64"], enc["key_hex"],
        questions_json,
    ))

    # Store Shamir shares (one per centre slot — centres 1–5)
    shares = split_key(enc["key_hex"], threshold=3, shares=5)
    for s in shares:
        conn.execute("""
            INSERT INTO shamir_shares (exam_id, centre_id, share_id, share_hex)
            VALUES (?, ?, ?, ?)
        """, (exam_id, f"CENTRE-{s['share_id']}", s["share_id"], s["share_hex"]))

    conn.commit()
    conn.close()

    # Audit event
    ev = append_event(
        exam_id, "PAPER_SEALED",
        actor="admin",
        metadata={"sha256": enc["sha256_plain"], "ipfs_cid": ipfs_cid, "name": exam_title},
    )

    return ExamCreateResponse(
        exam_id=exam_id,
        sha256_plain=enc["sha256_plain"],
        ipfs_cid=ipfs_cid,
        status="SEALED",
        audit_hash=ev["event_hash"],
        question_count=len(questions),
        preview=first_200,
        engine=engine,
    )


@router.get("/")
def list_exams():
    """List all registered exams."""
    conn = get_conn()
    rows = conn.execute("SELECT id, name, status, release_time, ipfs_cid, questions_json FROM exams ORDER BY created_at DESC").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        q_list = json.loads(d["questions_json"]) if d.get("questions_json") else []
        d["question_count"] = len(q_list)
        d["preview"] = (" ".join(q_list))[:200] if q_list else ""
        result.append(d)
    return result


@router.get("/{exam_id}")
def get_exam(exam_id: str):
    """Get exam details (without key material)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, name, status, release_time, ipfs_cid, sha256_plain, questions_json FROM exams WHERE id = ?",
        (exam_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Exam not found")
    d = dict(row)
    q_list = json.loads(d["questions_json"]) if d.get("questions_json") else []
    d["question_count"] = len(q_list)
    d["preview"] = (" ".join(q_list))[:200] if q_list else ""
    return d
