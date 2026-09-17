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
from core.crypto import encrypt_pdf, split_key
from core.audit import append_event, init_db

router = APIRouter()


class ExamCreateResponse(BaseModel):
    exam_id:      str
    sha256_plain: str
    ipfs_cid:     str
    status:       str
    audit_hash:   str


@router.post("/", response_model=ExamCreateResponse)
async def create_exam(
    file:         UploadFile = File(...),
    name:         str = Form(...),
    release_time: float = Form(...),   # Unix epoch seconds
):
    """
    Upload a PDF exam paper.
    - Encrypts with AES-256-GCM
    - Splits key via Shamir 3-of-5
    - Pins encrypted blob to IPFS
    - Registers in local DB with SEALED status
    - Appends PAPER_SEALED audit event
    """
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(400, "Empty file")

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
           nonce_b64, ciphertext_b64, key_hex)
        VALUES (?, ?, ?, ?, 'SEALED', ?, ?, ?, ?, ?)
    """, (
        exam_id, name, created_at, release_time, ipfs_cid,
        enc["sha256_plain"], enc["nonce_b64"], enc["ciphertext_b64"], enc["key_hex"],
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
        metadata={"sha256": enc["sha256_plain"], "ipfs_cid": ipfs_cid, "name": name},
    )

    return ExamCreateResponse(
        exam_id=exam_id,
        sha256_plain=enc["sha256_plain"],
        ipfs_cid=ipfs_cid,
        status="SEALED",
        audit_hash=ev["event_hash"],
    )


@router.get("/")
def list_exams():
    """List all registered exams."""
    conn = get_conn()
    rows = conn.execute("SELECT id, name, status, release_time, ipfs_cid FROM exams ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/{exam_id}")
def get_exam(exam_id: str):
    """Get exam details (without key material)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, name, status, release_time, ipfs_cid, sha256_plain FROM exams WHERE id = ?",
        (exam_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Exam not found")
    return dict(row)
