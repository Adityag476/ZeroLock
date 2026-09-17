"""
ZeroLeak Backend — SQLite Database & Schema
"""

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("ZEROLEAK_DB", "zeroleak.db"))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS exams (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            created_at      REAL NOT NULL,
            release_time    REAL NOT NULL,
            status          TEXT NOT NULL DEFAULT 'DRAFT',
            ipfs_cid        TEXT,
            sha256_plain    TEXT,
            nonce_b64       TEXT,
            ciphertext_b64  TEXT,
            key_hex         TEXT,
            unlock_time_unix REAL,
            on_chain_paper_id TEXT
        );

        CREATE TABLE IF NOT EXISTS shamir_shares (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id     TEXT NOT NULL REFERENCES exams(id),
            centre_id   TEXT NOT NULL,
            share_id    INTEGER NOT NULL,
            share_hex   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS print_instances (
            id            TEXT PRIMARY KEY,
            exam_id       TEXT NOT NULL REFERENCES exams(id),
            centre_id     INTEGER NOT NULL,
            hall_id       INTEGER NOT NULL,
            print_num     INTEGER NOT NULL,
            authorized_at REAL NOT NULL,
            operator      TEXT,
            timestamp_epoch INTEGER NOT NULL,
            on_chain_tx   TEXT
        );

        CREATE TABLE IF NOT EXISTS investigations (
            id            TEXT PRIMARY KEY,
            uploaded_at   REAL NOT NULL,
            image_filename TEXT,
            status        TEXT NOT NULL,
            centre_id     INTEGER,
            hall_id       INTEGER,
            print_num     INTEGER,
            timestamp_epoch INTEGER,
            confidence    REAL,
            bit_count     INTEGER,
            anchor_found  INTEGER,
            message       TEXT
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

    # Safe schema migration for print_instances
    existing_cols = [c[1] for c in conn.execute("PRAGMA table_info(print_instances)").fetchall()]
    if "timestamp_epoch" not in existing_cols:
        conn.execute("ALTER TABLE print_instances ADD COLUMN timestamp_epoch INTEGER DEFAULT 0")
    if "on_chain_tx" not in existing_cols:
        conn.execute("ALTER TABLE print_instances ADD COLUMN on_chain_tx TEXT")

    conn.commit()
    conn.close()
