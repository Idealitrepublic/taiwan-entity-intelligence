"""Comparable, sample-scoped data-health metrics; unknown is never zero."""
from __future__ import annotations

from datetime import datetime, timezone


SOURCES = (
    "company_registration", "directors", "procurement", "labor_penalties",
    "judiciary", "politicians", "political_contributions",
    "asset_declarations", "entity_resolution",
)


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator > 0 else None


def age_hours(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if at.tzinfo is None:
            return None
        return round(max(0, (now - at.astimezone(timezone.utc)).total_seconds()) / 3600, 1)
    except ValueError:
        return None


def metric(name: str, *, observed: int | None, expected: int | None,
           rows: list[dict] | None = None, identity: str | None = None,
           timestamp: str | None = None, errors: int = 0,
           scope: str, note: str = "", required_data: bool = False,
           now: datetime | None = None) -> dict:
    """Measure only observed records, never infer population completeness."""
    if name not in SOURCES:
        raise ValueError(name)
    now = now or datetime.now(timezone.utc)
    rows = rows or []
    keys = [str(row[identity]) for row in rows if identity and row.get(identity)]
    required = ("source_url", "retrieved_at", "provenance")
    provenance = sum(all(row.get(field) for field in required) for row in rows)
    return {
        "source": name, "scope": scope, "observed": observed, "expected": expected,
        "coverage": ratio(observed, expected) if observed is not None and expected is not None else None,
        "freshness_hours": age_hours(timestamp, now), "error_count": errors,
        "duplicate_rate": ratio(len(keys) - len(set(keys)), len(keys)) if keys else None,
        "provenance_rate": ratio(provenance, len(rows)), "sample_size": len(rows),
        "note": note, "required_data": required_data,
    }


def severity(item: dict) -> str:
    if (item["error_count"] or (item["required_data"] and item["observed"] == 0)
            or (item["coverage"] is not None and item["coverage"] < 0.5)):
        return "High"
    if item["provenance_rate"] is not None and item["provenance_rate"] < 1:
        return "Medium"
    if item["coverage"] is None or item["provenance_rate"] is None:
        return "Unknown"
    if item["duplicate_rate"] and item["duplicate_rate"] > 0:
        return "Medium"
    if item["freshness_hours"] is not None and item["freshness_hours"] > 24 * 30:
        return "Medium"
    return "OK"
