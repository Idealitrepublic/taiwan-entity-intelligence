"""司法院裁判書 incremental connector.

Credentials are read from environment variables JUDICIAL_USER and
JUDICIAL_PASSWORD. The official API issues a short-lived token, then exposes a
7-day-back change list and individual judgments by jid. We deliberately store
only normalized evidence plus the source payload; no inference is performed.
"""

import json
import hashlib
import os
import re
import urllib.request
from typing import Any, Dict, Iterable, List

from ..evidence import make_evidence
from .judicial_index import judgment_url

BASE = "https://data.judicial.gov.tw/jdg/api"
USER_AGENT = "Taiwan-Entity-Intelligence/0.1"
JID = re.compile(r"^[A-Z]{4},\d{2,3},[^,\s]+,\d+,\d{8},\d+$")


def normalize_jid(value: str) -> str:
    jid = str(value or "").strip()
    if not JID.fullmatch(jid):
        raise ValueError("Invalid judicial JID")
    return jid


def normalize_jdate(value: str) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) != 8:
        raise ValueError("Invalid judicial date")
    from datetime import date
    return date.fromisoformat(f"{digits[:4]}-{digits[4:6]}-{digits[6:]}").isoformat()


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
    if not isinstance(result, dict):
        raise RuntimeError("司法院 API 驗證回應格式錯誤")
    token = result.get("Token") or result.get("token")
    if not token:
        raise RuntimeError("司法院 API 驗證失敗")
    return token


def changed_jids(token: str) -> List[str]:
    result = post("/JList", {"token": token})
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError("Judicial JList rejected the request")
    if not isinstance(result, list):
        raise ValueError("Judicial JList returned an invalid response")
    jids: List[str] = []
    for day in result:
        if not isinstance(day, dict):
            raise ValueError("Judicial JList day is invalid")
        entries = day.get("list", day.get("LIST"))
        if not isinstance(entries, list):
            raise ValueError("Judicial JList day has no JID list")
        jids.extend(normalize_jid(item) for item in entries)
    return list(dict.fromkeys(jids))


def fetch_judgment(token: str, jid: str) -> Dict[str, Any]:
    result = post("/JDoc", {"token": token, "j": normalize_jid(jid)})
    if not isinstance(result, dict):
        raise ValueError("Judicial JDoc returned an invalid response")
    return result


def _versioned_evidence(row: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Keep corrections/removals as separate immutable Evidence versions."""
    content_hash = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    row["evidence_id"] = hashlib.sha256(
        f"judicial_court_records|{row['source']['record_id']}|{content_hash}|{row['fact']['type']}"
        .encode("utf-8")).hexdigest()
    row["source"]["content_hash"] = content_hash
    return row


def evidence_rows() -> Iterable[Dict[str, Any]]:
    token = get_token()
    for jid in changed_jids(token):
        doc = fetch_judgment(token, jid)
        error = str(doc.get("error") or "")
        if error:
            if not any(marker in error for marker in ("移除", "不存在", "不公開", "已刪除")):
                raise RuntimeError("Judicial JDoc rejected the request")
            # The official API may signal that a previously public judgment was removed.
            yield _versioned_evidence(make_evidence(
                source_type="judicial",
                source_name="judicial_court_records",
                source_record_id=jid,
                entity_id="judgment:{}".format(jid),
                entity_type="judgment",
                fact_type="court_record_status",
                title="裁判書已移除或不可公開",
                summary=error,
                source_url=judgment_url(jid),
                confidence=1.0,
                status="removed",
                raw_payload=doc,
            ), doc)
            continue

        document_jid = normalize_jid(doc.get("JID") or jid)
        if document_jid != jid:
            raise ValueError("Judicial JDoc JID does not match JList")
        date = normalize_jdate(doc.get("JDATE") or jid.split(",")[4])
        if date.replace("-", "") != jid.split(",")[4]:
            raise ValueError("Judicial JDoc date does not match JID")
        jfull = doc.get("JFULLX") or {}
        if isinstance(jfull, str):
            jfull = {"JFULLCONTENT": jfull}
        if not isinstance(jfull, dict):
            raise ValueError("Judicial JDoc full text is invalid")
        if not (jfull.get("JFULLCONTENT") or jfull.get("JFULLPDF")):
            raise ValueError("Judicial JDoc returned no content or PDF")
        yield _versioned_evidence(make_evidence(
            source_type="judicial",
            source_name="judicial_court_records",
            source_record_id=document_jid,
            entity_id="judgment:{}".format(document_jid),
            entity_type="judgment",
            fact_type="court_record",
            title=doc.get("JTITLE"),
            summary=jfull.get("JFULLCONTENT"),
            source_url=judgment_url(document_jid),
            source_published_at=date,
            confidence=1.0,
            raw_payload=doc,
        ), doc)
