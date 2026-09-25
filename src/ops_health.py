"""Read-only operational signals over saved, non-secret run artifacts."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from statistics import quantiles
from zoneinfo import ZoneInfo


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def hours_since(value, now):
    parsed = parse_time(value)
    return max(0, (now - parsed).total_seconds() / 3600) if parsed else None


def alert(code, severity, message, source="platform"):
    return {"code": code, "severity": severity, "source": source, "message": message}


def evaluate(status, health, state, *, now=None, runtime_events=(),
             report_max_age_hours=24, sync_max_age_hours=36):
    """Never infer population coverage or treat source closure as ingestion failure."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    alerts = []
    report_age = hours_since(health.get("generated_at"), now)
    if report_age is None or report_age > report_max_age_hours:
        alerts.append(alert("data_health_stale", "High", "Data Health report is missing or stale", "data_health"))
    high_sources = sorted(item.get("source", "unknown") for item in health.get("metrics", [])
                          if item.get("severity") in ("High", "Critical"))
    if high_sources:
        alerts.append(alert("data_health_high", "High", "High-severity sources: " + ", ".join(high_sources),
                            "data_health"))
    for item in health.get("metrics", []):
        source = item.get("source") or "unknown"
        provenance = item.get("provenance_rate")
        duplicate = item.get("duplicate_rate")
        if provenance is not None and provenance < 1:
            alerts.append(alert(f"provenance:{source}", "Medium", "Sample provenance is incomplete", source))
        if duplicate is not None and duplicate > 0:
            alerts.append(alert(f"duplicates:{source}", "Medium", "Duplicate sample identifiers found", source))

    progress = state.get("judicial_progress") or {}
    total = progress.get("total_batches") or 0
    completed = len(progress.get("completed_batches") or [])
    attempted = len(state.get("judicial_batch_stats") or {})
    pending = len(state.get("judicial_pending") or {})
    unavailable = len(state.get("judicial_source_unavailable") or {})
    quality = health.get("judicial_window_quality") or {}
    if quality and (quality.get("completed_batches") != completed or
                    quality.get("attempted_batches") != attempted or
                    quality.get("pending_jids") != pending or
                    quality.get("upstream_unavailable_jids") != unavailable):
        alerts.append(alert("health_checkpoint_mismatch", "High",
                            "Data Health judicial counts disagree with checkpoint", "data_health"))
    last_attempt_age = hours_since(state.get("last_attempt") or status.get("last_attempt"), now)
    last_success_age = hours_since(state.get("last_sync") or status.get("last_sync"), now)
    if not total or attempted > total or completed > attempted:
        alerts.append(alert("judicial_checkpoint_invalid", "High", "Judicial checkpoint totals are inconsistent", "judiciary"))
    if total and completed < total:
        if last_attempt_age is None or last_attempt_age > 2:
            alerts.append(alert("judicial_cursor_stalled", "High", "Judicial cursor has not advanced for two hours",
                                "judiciary"))
    if pending:
        alerts.append(alert("judicial_pending", "High", f"{pending} judicial documents await retry", "judiciary"))
    judicial_status = status.get("judicial_status")
    errors = status.get("errors") or []
    service_closed_only = (bool(errors) and
                           all(row.get("source") == "judicial" and
                               row.get("error_type") == "service_closed" for row in errors) and
                           now.astimezone(ZoneInfo("Asia/Taipei")).hour >= 6)
    if judicial_status in ("error", "partial") and not service_closed_only:
        alerts.append(alert("judicial_sync_failed", "High", "Latest judicial sync failed or is partial", "judiciary"))
    if last_success_age is None or last_success_age > sync_max_age_hours:
        alerts.append(alert("judicial_sync_stale", "High", "No successful judicial publication within freshness target",
                            "judiciary"))
    if unavailable:
        alerts.append(alert("judicial_upstream_unavailable", "Medium",
                            f"{unavailable} JList documents remain unavailable from JDoc", "judiciary"))

    grouped_errors = Counter((row.get("source") or "unknown", row.get("error_type") or "unknown")
                             for row in errors)
    for (source, error_type), count in sorted(grouped_errors.items()):
        if error_type == "service_closed" and source == "judicial":
            continue
        if error_type == "upstream_document_error" and not pending:
            continue
        alerts.append(alert(f"source_error:{source}:{error_type}", "High",
                            f"{count} source error(s) of type {error_type}", source))

    requests = [row for row in runtime_events if row.get("event") == "request_complete"
                and isinstance(row.get("status"), int)]
    if len(requests) >= 20:
        errors_5xx = sum(row["status"] >= 500 for row in requests)
        limited_429 = sum(row["status"] == 429 for row in requests)
        if errors_5xx / len(requests) >= 0.05:
            alerts.append(alert("runtime_5xx", "High", "5xx rate reached 5% in the supplied log sample"))
        if limited_429 / len(requests) >= 0.1:
            alerts.append(alert("runtime_429", "Medium", "429 rate reached 10% in the supplied log sample"))
    durations = [row["duration_ms"] for row in requests
                 if isinstance(row.get("duration_ms"), (int, float)) and row["duration_ms"] >= 0]
    p95 = round(quantiles(durations, n=20)[18], 1) if len(durations) >= 20 else None
    if p95 is not None and p95 > 5000:
        alerts.append(alert("runtime_p95", "Medium", "p95 request duration exceeds five seconds"))
    alerts.sort(key=lambda item: (item["severity"] != "High", item["code"]))
    run = status.get("run") or {}
    return {
        "generated_at": now.isoformat(), "environment": "development", "read_only": True,
        "signals": {"data_health_age_hours": round(report_age, 2) if report_age is not None else None,
                    "last_attempt_age_hours": round(last_attempt_age, 2) if last_attempt_age is not None else None,
                    "last_success_age_hours": round(last_success_age, 2) if last_success_age is not None else None,
                    "judicial_total_batches": total, "judicial_attempted_batches": attempted,
                    "judicial_completed_batches": completed, "judicial_pending": pending,
                    "judicial_upstream_unavailable": unavailable,
                    "last_run_id": run.get("id"), "last_run_source": run.get("source"),
                    "last_run_duration_ms": run.get("duration_ms"),
                    "last_run_window_id": run.get("window_id"),
                    "last_run_batch_index": run.get("batch_index"),
                    "runtime_sample_size": len(requests), "runtime_p95_ms": p95},
        "alerts": alerts, "high_count": sum(item["severity"] == "High" for item in alerts),
    }


def update_alert_history(previous, current, now):
    """Deduplicate by stable code; retain first/last seen and recovery proof."""
    history = dict(previous.get("alerts") or {})
    active = {item["code"]: item for item in current["alerts"]}
    stamp = now.isoformat()
    for code, item in active.items():
        old = history.get(code) or {}
        history[code] = {**item, "first_seen": old.get("first_seen") or stamp,
                         "last_seen": stamp, "repeat_count": int(old.get("repeat_count") or 0) + 1,
                         "status": "active", "resolved_at": None}
    for code, old in list(history.items()):
        if code not in active and old.get("status") == "active":
            history[code] = {**old, "status": "resolved", "resolved_at": stamp}
    return {"updated_at": stamp, "alerts": history}
