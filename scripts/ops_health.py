#!/usr/bin/env python3
"""Produce a local, sanitized operations dashboard without source/API writes."""
import argparse
from collections import deque
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ops_health import evaluate, update_alert_history  # noqa: E402


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def runtime_events(path):
    if not path:
        return []
    rows = deque(maxlen=10000)
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append({key: item.get(key) for key in ("event", "status", "duration_ms")})
    return list(rows)


def write_private_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w",
                   encoding="utf-8") as stream:
        temp.chmod(0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
    temp.replace(path)


def write_private_text(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w",
                   encoding="utf-8") as stream:
        temp.chmod(0o600)
        stream.write(value)
    temp.replace(path)


def markdown(report):
    signals = report["signals"]
    rows = ["# T.E.I. Operations — Development", "",
            f"Generated: {report['generated_at']}",
            f"Owner: {report['owner']}",
            f"High alerts: {report['high_count']}", "",
            "| Signal | Value |", "|---|---:|"]
    rows.extend(f"| {key} | {value if value is not None else 'unknown'} |"
                for key, value in signals.items())
    rows.extend(["", "## Active alerts", ""])
    rows.extend(f"- [{item['severity']}] {item['code']}: {item['message']} "
                f"(first {item['first_seen']}; repeats {item['repeat_count']})"
                for item in report["active_alerts"])
    if not report["active_alerts"]:
        rows.append("- None")
    rows.extend(["", "This is an operator-local status view, not a public dashboard or national coverage claim."])
    return "\n".join(rows) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", type=Path, default=ROOT / "data/public_sync_status.json")
    parser.add_argument("--state", type=Path, default=ROOT / "data/public_sync_state.json")
    parser.add_argument("--health", type=Path, default=ROOT / "reports/data_health.json")
    parser.add_argument("--runtime-logs", type=Path, help="Optional sanitized request_complete NDJSON export")
    parser.add_argument("--output", type=Path, default=ROOT / "data/ops_health.json")
    parser.add_argument("--alert-state", type=Path, default=ROOT / "data/ops_alerts.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "data/ops_health.md")
    parser.add_argument("--check", action="store_true", help="Exit nonzero while High alerts exist")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    result = evaluate(read_json(args.status), read_json(args.health), read_json(args.state),
                      now=now, runtime_events=runtime_events(args.runtime_logs))
    history = update_alert_history(read_json(args.alert_state) if args.alert_state.exists() else {}, result, now)
    report = {**result, "owner": os.environ.get("TEI_OPS_OWNER") or "project maintainer",
              "active_alerts": [history["alerts"][item["code"]] for item in result["alerts"]]}
    write_private_json(args.alert_state, history)
    write_private_json(args.output, report)
    write_private_text(args.markdown, markdown(report))
    print(json.dumps({"high_count": result["high_count"], "active_alerts": len(result["alerts"]),
                      "report": str(args.output)}, ensure_ascii=False))
    return 2 if args.check and result["high_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
