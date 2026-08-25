"""Unified evidence model and helpers for cross-source intelligence.

Evidence is the atomic, source-backed fact behind an entity relationship or
risk signal. The schema deliberately separates observed facts from inference.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

SCHEMA_VERSION = "1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(source: str, record_id: str, payload: Optional[Dict[str, Any]] = None) -> str:
    canonical = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, default=str)
    raw = "{}|{}|{}".format(source or "unknown", record_id or "", canonical)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_evidence(
    *,
    source_type: str,
    source_name: str,
    source_record_id: str,
    entity_id: str,
    entity_type: str,
    fact_type: str,
    relation_type: Optional[str] = None,
    target_entity_id: Optional[str] = None,
    target_entity_type: Optional[str] = None,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    source_url: Optional[str] = None,
    source_published_at: Optional[str] = None,
    observed_at: Optional[str] = None,
    confidence: float = 1.0,
    status: str = "active",
    raw_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = raw_payload or {}
    return {
        "evidence_id": stable_id(source_name, str(source_record_id), payload),
        "schema_version": SCHEMA_VERSION,
        "source_type": source_type,
        "source_name": source_name,
        "source_record_id": str(source_record_id),
        "source_url": source_url,
        "source_published_at": source_published_at,
        "observed_at": observed_at,
        "retrieved_at": utc_now(),
        "entity_id": entity_id,
        "entity_type": entity_type,
        "fact_type": fact_type,
        "relation_type": relation_type,
        "target_entity_id": target_entity_id,
        "target_entity_type": target_entity_type,
        "title": title,
        "summary": summary,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "status": status,
        "raw_payload_json": json.dumps(payload, ensure_ascii=False, default=str),
    }


def row_to_evidence(row: Any) -> Dict[str, Any]:
    result = dict(row)
    if result.get("raw_payload_json"):
        try:
            result["raw_payload"] = json.loads(result["raw_payload_json"])
        except (TypeError, ValueError):
            result["raw_payload"] = result["raw_payload_json"]
    return result
