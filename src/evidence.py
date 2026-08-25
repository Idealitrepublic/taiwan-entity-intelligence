"""Unified Evidence schema used by all public-record connectors."""
import hashlib
import json
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"


def make_evidence(**kwargs):
    """Create the canonical nested Evidence object used by analysis code."""
    raw = kwargs.get("raw_payload")
    source_name = str(kwargs["source_name"])
    record_id = str(kwargs["source_record_id"])
    entity_id = str(kwargs["entity_id"])
    fact_type = str(kwargs["fact_type"])
    evidence_id = hashlib.sha256(
        f"{source_name}|{record_id}|{entity_id}|{fact_type}".encode("utf-8")
    ).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "observed_at": now,
        "retrieved_at": now,
        "source": {
            "type": kwargs["source_type"],
            "name": source_name,
            "record_id": record_id,
            "url": kwargs.get("source_url"),
            "published_at": kwargs.get("source_published_at"),
        },
        "subject": {
            "id": entity_id,
            "type": kwargs["entity_type"],
        },
        "fact": {
            "type": fact_type,
            "relation": kwargs.get("relation_type"),
            "title": kwargs.get("title"),
            "summary": kwargs.get("summary"),
        },
        "target_entity_id": kwargs.get("target_entity_id"),
        "target_entity_type": kwargs.get("target_entity_type"),
        "confidence": float(kwargs.get("confidence", 1.0)),
        "status": kwargs.get("status", "active"),
        "raw": raw,
    }


def row_to_evidence(row):
    """Convert a SQLite evidence row into the canonical nested Evidence object."""
    data = dict(row)
    raw = data.get("raw_payload_json")
    if isinstance(raw, str) and raw:
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {"_raw_payload": raw}
    elif raw is None:
        raw = None
    return {
        "schema_version": data.get("schema_version", SCHEMA_VERSION),
        "evidence_id": data.get("evidence_id"),
        "observed_at": data.get("observed_at"),
        "retrieved_at": data.get("retrieved_at"),
        "source": {
            "type": data.get("source_type"),
            "name": data.get("source_name"),
            "record_id": data.get("source_record_id"),
            "url": data.get("source_url"),
            "published_at": data.get("source_published_at"),
        },
        "subject": {
            "id": data.get("entity_id"),
            "type": data.get("entity_type"),
        },
        "fact": {
            "type": data.get("fact_type"),
            "relation": data.get("relation_type"),
            "title": data.get("title"),
            "summary": data.get("summary"),
        },
        "target_entity_id": data.get("target_entity_id"),
        "target_entity_type": data.get("target_entity_type"),
        "confidence": float(data.get("confidence", 1.0)),
        "status": data.get("status", "active"),
        "raw": raw,
    }


def dedupe_evidence(rows):
    seen = set()
    out = []
    for row in rows:
        key = row.get("evidence_id") or json.dumps(
            row, ensure_ascii=False, sort_keys=True, default=str
        )
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out
