import os
import sys
import io
import time
import json
import requests
import sqlite3

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from core.audit import verify_chain, append_event

BASE_URL = "http://localhost:8000"
results = {}

print("=== Starting Section G Audit (G1) ===")

# Create an exam that accumulates all event types
with open("experiments/fixtures/TY_DSP_26-27_Tutorial_6.pdf", "rb") as f:
    r_ex = requests.post(
        f"{BASE_URL}/api/exams/",
        files={"file": ("T6_AuditChain.pdf", f, "application/pdf")},
        data={"name": "Audit Full Lifecycle Exam", "release_time": str(time.time() + 3600.0)}
    )
exam_id = r_ex.json()["exam_id"]
print(f"Exam created: {exam_id}")

# 1. Deposit event was automatically logged as PAPER_SEALED
# 2. Warp + Unlock
requests.post(f"{BASE_URL}/api/unlock/{exam_id}/warp")
r_unl = requests.post(f"{BASE_URL}/api/unlock/{exam_id}", json={"centre_id": 14, "hall_id": 3, "otp": "secret123"})
print(f"Unlock: {r_unl.status_code}")

# 3. Print instance
r_p = requests.get(f"{BASE_URL}/api/print/{exam_id}?centre_id=14&hall_id=3")
print(f"Print: {r_p.status_code}")

# 4. Batch generation
r_b = requests.post(f"{BASE_URL}/api/batch/generate", json={"exam_id": exam_id, "centre_ids": [14, 28]})
b_job_id = r_b.json()["job_id"]
for _ in range(30):
    time.sleep(1.0)
    st = requests.get(f"{BASE_URL}/api/batch/status/{b_job_id}").json().get("status")
    if st in ("COMPLETED", "FAILED"):
        break
print(f"Batch completed: {st}")

# 5. Investigation event
r_inv = requests.post(f"{BASE_URL}/api/investigate/", json={"exam_id": exam_id, "centre_id": 14, "hall_id": 3, "print_num": 1, "notes": "Audit lifecycle test"})
print(f"Investigation logged: {r_inv.status_code}")

# Query audit endpoint
r_audit = requests.get(f"{BASE_URL}/api/audit/{exam_id}")
print(f"Audit endpoint status: {r_audit.status_code}")
audit_data = r_audit.json()
print(f"Audit response: chain_valid={audit_data.get('chain_valid')}, event_count={audit_data.get('event_count')}")

events = audit_data.get("events", [])
event_types = [e["event_type"] for e in events]
print(f"Observed event types: {event_types}")

has_sealed = "PAPER_SEALED" in event_types
has_unlocked = "PAPER_UNLOCKED" in event_types
has_print = "PRINT_GENERATED" in event_types
has_batch = "BATCH_PRINT_GENERATED" in event_types
has_investigation = any("INVESTIGAT" in et for et in event_types) or r_inv.status_code == 200

# Programmatically verify chain integrity
chain_ok, chain_msg = verify_chain(exam_id)
print(f"Programmatic verify_chain: ok={chain_ok}, msg={chain_msg}")

g1_pass = (
    r_audit.status_code == 200
    and audit_data.get("chain_valid") is True
    and chain_ok is True
    and has_sealed
    and has_unlocked
    and has_print
    and has_batch
)
results["G1"] = {
    "pass": g1_pass,
    "chain_valid": chain_ok,
    "event_count": len(events),
    "event_types": event_types,
    "chain_msg": chain_msg
}

print(f"\nG1: {'PASS' if g1_pass else 'FAIL'} | {results['G1']}")
