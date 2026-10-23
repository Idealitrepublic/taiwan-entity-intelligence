"""Verified upstream notices; never infer a maintenance window from an HTTP error."""
from __future__ import annotations

from datetime import datetime, timezone


MOEA_MAINTENANCE = {
    "source": "經濟部商工行政資料開放平臺 / MOEA registry",
    "starts_at": "2026-10-23T19:00:00+08:00",
    "ends_at": "2026-10-27T00:00:00+08:00",
    "source_url": "https://gcis.nat.gov.tw/mainNew/",
    "notice_url": "https://data.gcis.nat.gov.tw/ns/news/detail?oid=8D1E61CE-E802-404D-B0C8-317549F580C2",
    "affected": ["公司登記", "董監事"],
}


def active_source_notices(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    start = datetime.fromisoformat(MOEA_MAINTENANCE["starts_at"])
    end = datetime.fromisoformat(MOEA_MAINTENANCE["ends_at"])
    return [MOEA_MAINTENANCE.copy()] if start <= now < end else []
