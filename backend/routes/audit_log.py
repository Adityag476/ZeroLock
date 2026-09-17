"""
ZeroLeak — GET /api/audit/{exam_id}
Return the hash-chained audit trail for an exam.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, HTTPException
from core.audit import get_audit_log, verify_chain

router = APIRouter()


@router.get("/{exam_id}")
def get_audit(exam_id: str):
    """Return the full audit log for an exam with chain verification."""
    log = get_audit_log(exam_id)
    if not log:
        raise HTTPException(404, "No audit events found for this exam")

    ok, msg = verify_chain(exam_id)
    return {
        "exam_id":      exam_id,
        "chain_valid":  ok,
        "chain_message": msg,
        "event_count":  len(log),
        "events":       log,
    }


@router.get("/{exam_id}/verify")
def verify_audit_chain(exam_id: str):
    """Quick chain integrity check."""
    ok, msg = verify_chain(exam_id)
    return {"chain_valid": ok, "message": msg}
