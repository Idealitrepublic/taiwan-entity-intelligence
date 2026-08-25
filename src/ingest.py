"""Import external public-record datasets into the unified evidence table.

Supported inputs are CSV and JSON files. The importer is intentionally
schema-light: source-specific column mappings are supplied on the command
line so each dataset can preserve its original payload and provenance.
"""

import argparse
import csv
import json
import os
from typing import Any, Dict, Iterable, List

from .db import connect
from .evidence import make_evidence
from .repository import upsert_evidence


SOURCE_PRESETS = {
    "judicial": {"source_type": "judicial", "source_name": "judicial_court_records", "fact_type": "court_record"},
    "procurement": {"source_type": "procurement", "source_name": "government_procurement", "fact_type": "government_tender"},
    "penalty": {"source_type": "administrative_penalty", "source_name": "government_penalties", "fact_type": "administrative_penalty"},
    "fraud": {"source_type": "fraud_signal", "source_name": "government_fraud_alerts", "fact_type": "fraud_signal"},
}


def load_records(path: str) -> Iterable[Dict[str, Any]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            yield from csv.DictReader(fh)
        return
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, list):
            yield from payload
        elif isinstance(payload, dict):
            for key in ("data", "records", "results", "items"):
                if isinstance(payload.get(key), list):
                    yield from payload[key]
                    return
            yield payload
        return
    raise ValueError("只支援 CSV / JSON：{}".format(path))


def ingest(
    db_path: str,
    path: str,
    source_key: str,
    entity_field: str,
    record_id_field: str,
    target_field: str = "",
    title_field: str = "",
    date_field: str = "",
    url_field: str = "",
) -> int:
    preset = SOURCE_PRESETS[source_key]
    conn = connect(db_path)
    count = 0
    for row in load_records(path):
        entity_value = str(row.get(entity_field) or "").strip()
        record_id = str(row.get(record_id_field) or "").strip()
        if not entity_value or not record_id:
            continue

        target_value = str(row.get(target_field) or "").strip() if target_field else ""
        entity_id = entity_value if ":" in entity_value else "company:{}".format(entity_value)
        target_id = None
        if target_value:
            target_id = target_value if ":" in target_value else target_value

        evidence = make_evidence(
            source_type=preset["source_type"],
            source_name=preset["source_name"],
            source_record_id=record_id,
            entity_id=entity_id,
            entity_type="company" if entity_id.startswith("company:") else "entity",
            fact_type=preset["fact_type"],
            relation_type="source_record",
            target_entity_id=target_id,
            target_entity_type="entity" if target_id else None,
            title=str(row.get(title_field) or preset["fact_type"]) if title_field else preset["fact_type"],
            summary=None,
            source_url=str(row.get(url_field) or "") if url_field else None,
            source_published_at=str(row.get(date_field) or "") if date_field else None,
            confidence=1.0,
            raw_payload=row,
        )
        upsert_evidence(conn, evidence)
        count += 1
    conn.commit()
    conn.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Import public records into T.E.I. evidence schema")
    parser.add_argument("source", choices=sorted(SOURCE_PRESETS))
    parser.add_argument("path")
    parser.add_argument("--db", default="data/entity.db")
    parser.add_argument("--entity-field", required=True)
    parser.add_argument("--record-id-field", required=True)
    parser.add_argument("--target-field", default="")
    parser.add_argument("--title-field", default="")
    parser.add_argument("--date-field", default="")
    parser.add_argument("--url-field", default="")
    args = parser.parse_args()
    count = ingest(**vars(args), source_key=args.source)
    print("Imported {} evidence records.".format(count))


if __name__ == "__main__":
    main()
