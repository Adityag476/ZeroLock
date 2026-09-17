"""
ZeroLeak — POST /api/unlock/{exam_id}
Centre requests unlock after scheduled release time.
"""

import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db import get_conn
from core.audit import append_event

router = APIRouter()


class UnlockRequest(BaseModel):
    centre_id: int
    hall_id:   int
    otp:       str    # simple passphrase for demo


class UnlockResponse(BaseModel):
    status:       str
    message:      str
    release_time: float
    current_time: float
    time_remaining: float
    audit_hash:   str


@router.post("/{exam_id}", response_model=UnlockResponse)
def unlock_exam(exam_id: str, req: UnlockRequest):
    """
    Simulate the time-lock unlock.
    - If current time < release_time → 403 TIMELOCK error (demo moment #1 revert)
    - Else → AUTHORIZED, append audit event
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "Exam not found")

    now         = time.time()
    release     = row["release_time"]
    remaining   = release - now

    # ── THE TIMELOCK ──────────────────────────────────────────────────────────
    if now < release:
        # Mirror the smart contract revert — demo moment #1
        ev = append_event(
            exam_id, "EARLY_UNLOCK_ATTEMPT",
            actor=f"centre-{req.centre_id}",
            metadata={
                "centre_id":    req.centre_id,
                "hall_id":      req.hall_id,
                "attempted_at": now,
                "release_time": release,
                "blocked_by":   "TIMELOCK",
            },
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error":        "TIMELOCK: release window not open",
                "release_time": release,
                "current_time": now,
                "seconds_remaining": remaining,
                "audit_hash":   ev["event_hash"],
            },
        )
    # ─────────────────────────────────────────────────────────────────────────

    # Update status to AUTHORIZED
    get_conn_w = get_conn()
    get_conn_w.execute("UPDATE exams SET status = 'AUTHORIZED' WHERE id = ?", (exam_id,))
    get_conn_w.commit()
    get_conn_w.close()

    ev = append_event(
        exam_id, "PAPER_UNLOCKED",
        actor=f"centre-{req.centre_id}",
        metadata={"centre_id": req.centre_id, "hall_id": req.hall_id, "unlocked_at": now},
    )

    return UnlockResponse(
        status="AUTHORIZED",
        message=f"Paper unlocked for Centre {req.centre_id}, Hall {req.hall_id}",
        release_time=release,
        current_time=now,
        time_remaining=0.0,
        audit_hash=ev["event_hash"],
    )


@router.post("/{exam_id}/warp")
def warp_exam_timelock(exam_id: str):
    """
    Time-travel / warp the time-lock forward to unlock immediately for live demos.
    Mirrors the Hardhat evm_increaseTime cheat code in EVM environments.
    """
    conn = get_conn()
    row = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Exam not found")

    past_time = time.time() - 10.0
    conn.execute("UPDATE exams SET release_time = ? WHERE id = ?", (past_time, exam_id))
    conn.commit()
    conn.close()

    append_event(
        exam_id, "TIMELOCK_WARP_APPLIED",
        actor="custody-demo-admin",
        metadata={"previous_release": row["release_time"], "warped_to": past_time},
    )

    return {
        "status": "WARPED",
        "message": "Time-lock bypassed via block timestamp warp (+3600s). Paper is now releasable.",
        "release_time": past_time,
    }

