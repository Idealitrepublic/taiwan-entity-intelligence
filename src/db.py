"""SQLite access helpers for the local entity database."""

import os
import sqlite3
from typing import List, Dict, Any


DEFAULT_DB = os.path.join("data", "entity.db")


def connect(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            "找不到資料庫：{}。請把本機 entity.db 放在 data/。".format(db_path)
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
