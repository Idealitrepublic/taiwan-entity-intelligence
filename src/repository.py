"""Repository functions for entities, tenders, and unified evidence."""

from typing import Dict, List, Any, Optional

from .db import connect, columns, tables
from .evidence import make_evidence, row_to_evidence


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
    """Best-effort tender lookup against the local schema."""
    table_names = set(tables(conn))
    results: List[Dict[str, Any]] = []
    candidate_columns = (
        "winner_name", "得標廠商", "得標廠商名稱", "winner_company_name", "公司名稱"
    )

    for table in ("tender_winners", "tenders"):
        if table not in table_names:
            continue
        cols = columns(conn, table)
        winner_col: Optional[str] = next((c for c in candidate_columns if c in cols), None)
        if not winner_col:
            continue
        sql = 'SELECT * FROM "{}" WHERE "{}" LIKE ? LIMIT ?'.format(table, winner_col)
        for row in conn.execute(sql, ("%{}%".format(company_name), limit)).fetchall():
            results.append(dict(row))
    return results


def _evidence_table_ready(conn) -> bool:
    return "evidence" in set(tables(conn))


def upsert_evidence(conn, evidence: Dict[str, Any]) -> None:
    if not _evidence_table_ready(conn):
        raise RuntimeError("evidence table is not initialized")
    fields = list(evidence.keys())
    placeholders = ",".join(["?"] * len(fields))
    sql = "INSERT OR REPLACE INTO evidence ({}) VALUES ({})".format(
        ",".join(fields), placeholders
    )
    conn.execute(sql, [evidence[f] for f in fields])


def evidence_for_entity(conn, entity_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    if not _evidence_table_ready(conn):
        return []
    rows = conn.execute(
        """SELECT * FROM evidence
           WHERE entity_id = ? OR target_entity_id = ?
           ORDER BY COALESCE(observed_at, source_published_at, retrieved_at) DESC
           LIMIT ?""",
        (entity_id, entity_id, limit),
    ).fetchall()
    return [row_to_evidence(row) for row in rows]


def evidence_summary(conn, entity_id: str) -> Dict[str, int]:
    if not _evidence_table_ready(conn):
        return {}
    rows = conn.execute(
        """SELECT fact_type, COUNT(*) AS n FROM evidence
           WHERE entity_id = ? OR target_entity_id = ?
           GROUP BY fact_type ORDER BY n DESC""",
        (entity_id, entity_id),
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def materialize_company_evidence(conn, uniform_number: str, company_name: str) -> int:
    """Turn currently available local facts into source-backed evidence rows.

    This is intentionally conservative: it records only facts that are already
    present in local source tables. It does not infer wrongdoing or ownership.
    """
    count = 0
    company_id = "company:{}".format(uniform_number)

    for person in company_people(conn, uniform_number):
        name = person.get("person_name")
        if not name:
            continue
        evidence = make_evidence(
            source_type="registry",
            source_name="company_directors",
            source_record_id="{}:{}:{}".format(uniform_number, name, person.get("position") or ""),
            entity_id=company_id,
            entity_type="company",
            fact_type="corporate_role",
            relation_type=person.get("position") or "director_relationship",
            target_entity_id="person:{}".format(name),
            target_entity_type="person",
            title="公司董監事／代表人關係",
            summary="{} 與 {} 存在公開公司登記職務關係。".format(company_name, name),
            confidence=1.0,
            raw_payload=person,
        )
        upsert_evidence(conn, evidence)
        count += 1

    for tender in company_tenders(conn, company_name):
        tender_id = tender.get("tender_id") or tender.get("案號") or tender.get("標案編號") or tender.get("id")
        if not tender_id:
            continue
        evidence = make_evidence(
            source_type="procurement",
            source_name="local_tender_database",
            source_record_id=str(tender_id),
            entity_id=company_id,
            entity_type="company",
            fact_type="government_tender",
            relation_type="tender_winner",
            target_entity_id="tender:{}".format(tender_id),
            target_entity_type="tender",
            title=tender.get("tender_name") or tender.get("標案名稱") or tender.get("案名") or str(tender_id),
            summary="公司與政府採購紀錄的來源關係。",
            confidence=1.0,
            raw_payload=tender,
        )
        upsert_evidence(conn, evidence)
        count += 1

    conn.commit()
    return count
