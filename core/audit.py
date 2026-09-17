"""
ZeroLeak Core — Hash-Chained Audit Log
=======================================
Provides a tamper-evident, append-only audit log stored in SQLite.

Chain structure:
    H(n) = SHA-256( event_json + H(n-1) )

If any past event is modified, all subsequent hashes become invalid.
"""

from __future__ import annotations
import json
import time
import hashlib
import sqlite3
from typing import Optional
from pathlib import Path

DB_PATH = Path("zeroleak.db")
GENESIS_HASH = "0" * 64    # SHA-256 of genesis block


# ---------------------------------------------------------------------------
# DB initialisation
# ---------------------------------------------------------------------------

def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    """Create database tables if they do not exist."""
    conn = _get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS exams (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            created_at    REAL NOT NULL,
            release_time  REAL NOT NULL,
            status        TEXT NOT NULL DEFAULT 'SEALED',
            ipfs_cid      TEXT,
            sha256_plain  TEXT,
            key_hex       TEXT,
            nonce_b64     TEXT,
            ciphertext_b64 TEXT
        );

        CREATE TABLE IF NOT EXISTS print_instances (
            id            TEXT PRIMARY KEY,
            exam_id       TEXT NOT NULL REFERENCES exams(id),
            centre_id     INTEGER NOT NULL,
            hall_id       INTEGER NOT NULL,
            print_num     INTEGER NOT NULL,
            authorized_at REAL NOT NULL,
            operator      TEXT,
            watermark_payload TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            seq           INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id       TEXT NOT NULL,
            event_type    TEXT NOT NULL,
            timestamp     REAL NOT NULL,
            actor         TEXT,
            metadata_json TEXT,
            prev_hash     TEXT NOT NULL,
            event_hash    TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def _compute_hash(event_data: dict, prev_hash: str) -> str:
    """Compute H(event_json + prev_hash)."""
    payload = json.dumps(event_data, sort_keys=True) + prev_hash
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_latest_hash(conn: sqlite3.Connection, exam_id: str) -> str:
    row = conn.execute(
        "SELECT event_hash FROM audit_events WHERE exam_id = ? ORDER BY seq DESC LIMIT 1",
        (exam_id,),
    ).fetchone()
    return row["event_hash"] if row else GENESIS_HASH


def append_event(
    exam_id:    str,
    event_type: str,
    actor:      str = "system",
    metadata:   Optional[dict] = None,
    db_path:    Path = DB_PATH,
) -> dict:
    """
    Append a new event to the hash-chained audit log.

    Returns:
        The newly created audit event as a dict.
    """
    conn = _get_conn(db_path)
    ts = time.time()
    meta_json = json.dumps(metadata or {})

    event_data = {
        "exam_id":    exam_id,
        "event_type": event_type,
        "timestamp":  ts,
        "actor":      actor,
        "metadata":   metadata or {},
    }

    prev_hash  = _get_latest_hash(conn, exam_id)
    event_hash = _compute_hash(event_data, prev_hash)

    conn.execute(
        """INSERT INTO audit_events
           (exam_id, event_type, timestamp, actor, metadata_json, prev_hash, event_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (exam_id, event_type, ts, actor, meta_json, prev_hash, event_hash),
    )
    conn.commit()
    conn.close()

    return {**event_data, "prev_hash": prev_hash, "event_hash": event_hash}


def get_audit_log(exam_id: str, db_path: Path = DB_PATH) -> list[dict]:
    """Return the full hash-chained audit trail for an exam."""
    conn = _get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM audit_events WHERE exam_id = ? ORDER BY seq ASC",
        (exam_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def verify_chain(exam_id: str, db_path: Path = DB_PATH) -> tuple[bool, str]:
    """
    Verify integrity of the entire audit chain for an exam.

    Returns:
        (ok: bool, message: str)
    """
    events = get_audit_log(exam_id, db_path)
    if not events:
        return True, "Empty chain — nothing to verify"

    prev = GENESIS_HASH
    for ev in events:
        event_data = {
            "exam_id":    ev["exam_id"],
            "event_type": ev["event_type"],
            "timestamp":  ev["timestamp"],
            "actor":      ev["actor"],
            "metadata":   json.loads(ev["metadata_json"]),
        }
        if ev["prev_hash"] != prev:
            return False, f"Chain break at seq {ev['seq']}: prev_hash mismatch"
        expected = _compute_hash(event_data, prev)
        if ev["event_hash"] != expected:
            return False, f"Chain break at seq {ev['seq']}: hash tampered"
        prev = ev["event_hash"]

    return True, f"Chain valid — {len(events)} events verified"


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile, pprint

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)

    init_db(db)
    eid = "EXAM-001"

    e1 = append_event(eid, "PAPER_SEALED",     actor="admin",    metadata={"sha256": "abc"}, db_path=db)
    e2 = append_event(eid, "PAPER_SCHEDULED",  actor="admin",    metadata={"release": "10:00"}, db_path=db)
    e3 = append_event(eid, "PRINT_AUTHORIZED", actor="centre14", metadata={"hall": 3}, db_path=db)

    log = get_audit_log(eid, db)
    print(f"Audit log: {len(log)} events")

    ok, msg = verify_chain(eid, db)
    assert ok, msg
    print(f"✅  {msg}")

    # Tamper detection
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE audit_events SET actor = 'hacker' WHERE seq = 2")
    conn.commit()
    conn.close()

    ok2, msg2 = verify_chain(eid, db)
    assert not ok2, "Should have detected tampering!"
    print(f"✅  Tamper detected: {msg2}")

    db.unlink()
