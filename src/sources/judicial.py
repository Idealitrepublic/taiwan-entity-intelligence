"""司法院裁判書 incremental connector.

Credentials are read from environment variables JUDICIAL_USER and
JUDICIAL_PASSWORD. The official API issues a short-lived token, then exposes a
7-day-back change list and individual judgments by jid. We deliberately store
only normalized evidence plus the source payload; no inference is performed.
"""

import json
import os
import urllib.request
from typing import Any, Dict, Iterable, List

from ..evidence import make_evidence

BASE = "https://data.judicial.gov.tw/jdg/api"
USER_AGENT = "Taiwan-Entity-Intelligence/0.1"


def post(path: str, payload: Dict[str, Any]) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def get_token() -> str:
    user = os.environ.get("JUDICIAL_USER")
    password = os.environ.get("JUDICIAL_PASSWORD")
    if not user or not password:
        raise RuntimeError("缺少 JUDICIAL_USER / JUDICIAL_PASSWORD GitHub Secrets")
    result = post("/Auth", {"user": user, "password": password})
    token = result.get("Token") or result.get("token")
    if not token:
        raise RuntimeError("司法院 API 驗證失敗：{}".format(result))
    return token


def changed_jids(token: str) -> List[str]:
    result = post("/JList", {"token": token})
    jids: List[str] = []
    for day in result if isinstance(result, list) else []:
        jids.extend(day.get("list", []))
    return list(dict.fromkeys(jids))


def fetch_judgment(token: str, jid: str) -> Dict[str, Any]:
    return post("/JDoc", {"token": token, "j": jid})


def evidence_rows() -> Iterable[Dict[str, Any]]:
    token = get_token()
    for jid in changed_jids(token):
        doc = fetch_judgment(token, jid)
        if doc.get("error"):
            # The official API may signal that a previously public judgment was removed.
            yield make_evidence(
                source_type="judicial",
                source_name="judicial_court_records",
                source_record_id=jid,
                entity_id="judgment:{}".format(jid),
                entity_type="judgment",
                fact_type="court_record_status",
                title="裁判書已移除或不可公開",
                summary=doc.get("error"),
                source_url="https://opendata.judicial.gov.tw/",
                confidence=1.0,
                status="removed",
                raw_payload=doc,
            )
            continue

        jfull = doc.get("JFULLX") or {}
        yield make_evidence(
            source_type="judicial",
            source_name="judicial_court_records",
            source_record_id=doc.get("JID") or jid,
            entity_id="judgment:{}".format(doc.get("JID") or jid),
            entity_type="judgment",
            fact_type="court_record",
            title=doc.get("JTITLE"),
            summary=jfull.get("JFULLCONTENT"),
            source_url="https://opendata.judicial.gov.tw/",
            source_published_at=doc.get("JDATE"),
            confidence=1.0,
            raw_payload=doc,
        )
