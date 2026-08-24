"""Repository functions for the known local SQLite schema."""

from typing import Dict, List, Any, Optional

from .db import connect


def company_people(conn, uniform_number: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT uniform_number, company_name, position, person_name,
               representative, shares
        FROM company_directors
        WHERE uniform_number = ?
        ORDER BY person_name, position
    """
    return [dict(row) for row in conn.execute(sql, (uniform_number,)).fetchall()]


def person_companies(conn, person_name: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT DISTINCT uniform_number, company_name, position,
               person_name, representative, shares
        FROM company_directors
        WHERE person_name = ?
        ORDER BY company_name
    """
    return [dict(row) for row in conn.execute(sql, (person_name,)).fetchall()]


def company_tenders(conn, company_name: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Best-effort tender lookup against the local schema.

    The existing database may expose different tender columns depending on
    the source import, so this function first inspects the schema and selects
    a plausible winner/company column.
    """
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    results: List[Dict[str, Any]] = []
    candidate_columns = (
        "winner_name",
        "得標廠商",
        "得標廠商名稱",
        "winner_company_name",
        "公司名稱",
    )

    for table in ("tender_winners", "tenders"):
        if table not in tables:
            continue

        cols = [
            row[1]
            for row in conn.execute(
                'PRAGMA table_info("{}")'.format(table)
            ).fetchall()
        ]
        winner_col: Optional[str] = next(
            (c for c in candidate_columns if c in cols), None
        )
        if not winner_col:
            continue

        sql = 'SELECT * FROM "{}" WHERE "{}" LIKE ? LIMIT ?'.format(
            table, winner_col
        )
        for row in conn.execute(sql, ("%{}%".format(company_name), limit)).fetchall():
            results.append(dict(row))

    return results
