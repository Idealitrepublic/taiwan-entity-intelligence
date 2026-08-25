"""SQLite access helpers for the local entity database."""

import os
import sqlite3
from typing import List, Dict, Any


DEFAULT_DB = os.path.join("data", "entity.db")

EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_url TEXT,
    source_published_at TEXT,
    observed_at TEXT,
    retrieved_at TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    relation_type TEXT,
    target_entity_id TEXT,
    target_entity_type TEXT,
    title TEXT,
    summary TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'active',
    raw_payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence(entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_target ON evidence(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_name, source_record_id);
CREATE INDEX IF NOT EXISTS idx_evidence_fact ON evidence(fact_type);
"""


def migrate(conn: sqlite3.Connection) -> None:
    """Create additive local schemas needed by the intelligence layer."""
    conn.executescript(EVIDENCE_SCHEMA)
    conn.commit()


def connect(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            "找不到資料庫：{}。請把本機 entity.db 放在 data/。".format(db_path)
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    return conn


def tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute('PRAGMA table_info("{}")'.format(table.replace('"', '""'))).fetchall()
    return [row[1] for row in rows]


def query_all(conn: sqlite3.Connection, sql: str, params=()) -> List[Dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]
