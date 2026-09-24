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
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List

from ..evidence import make_evidence
from .judicial_index import judgment_url

BASE = "https://data.judicial.gov.tw/jdg/api"
USER_AGENT = "Taiwan-Entity-Intelligence/0.1"
# JList includes both five-part IDs and IDs with a final check/sequence number.
JID = re.compile(r"^[A-Z]{4},\d{2,3},[^,\s]+,\d+,\d{8}(?:,\d+)?$")


class JudicialRequestError(RuntimeError):
    """Sanitized diagnostic: never retain a token or request body."""

    def __init__(self, error_type: str, *, path: str, http_status=None,
                 attempts=1, elapsed_ms=0, response_error_hash=None):
        super().__init__(error_type)
        self.diagnostic = {"error_type": error_type, "http_status": http_status,
                           "request": {"method": "POST", "endpoint": path},
                           "attempts": attempts, "elapsed_ms": elapsed_ms}
        if response_error_hash:
            self.diagnostic["response_error_hash"] = response_error_hash


def _backoff(attempt: int, retry_after=None) -> None:
    delay = min(8, 2 ** attempt)
    if retry_after is not None:
        try:
            delay = min(10, max(delay, int(retry_after)))
        except (TypeError, ValueError):
            pass
    time.sleep(delay)


def normalize_jid(value: str) -> str:
    jid = str(value or "").strip()
    if not JID.fullmatch(jid):
        # Official case IDs are public; preserve a bounded escaped sample so a
        # failed sync can distinguish source format drift from malformed data.
        raise ValueError(f"Invalid judicial JID: {ascii(jid)[:120]}")
    return jid


def normalize_jdate(value: str) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) != 8:
        raise ValueError("Invalid judicial date")
    from datetime import date
    return date.fromisoformat(f"{digits[:4]}-{digits[4:6]}-{digits[6:]}").isoformat()


def post(path: str, payload: Dict[str, Any], *, with_meta=False) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    started = time.monotonic()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
                meta = {"http_status": response.status, "attempts": attempt + 1,
                        "elapsed_ms": int((time.monotonic() - started) * 1000)}
                return (result, meta) if with_meta else result
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                error_type = "rate_limit" if exc.code == 429 else "http_error"
                raise JudicialRequestError(error_type, path=path, http_status=exc.code,
                                           attempts=attempt + 1,
                                           elapsed_ms=int((time.monotonic() - started) * 1000)) from None
            _backoff(attempt, exc.headers.get("Retry-After"))
        except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
            if attempt == 3:
                error_type = ("timeout" if isinstance(exc, TimeoutError) or
                              isinstance(getattr(exc, "reason", None), TimeoutError)
                              else "transport_error")
                raise JudicialRequestError(error_type, path=path, attempts=attempt + 1,
                                           elapsed_ms=int((time.monotonic() - started) * 1000)) from None
            _backoff(attempt)


def get_token() -> str:
    user = os.environ.get("JUDICIAL_USER")
    password = os.environ.get("JUDICIAL_PASSWORD")
    if not user or not password:
        raise RuntimeError("缺少 JUDICIAL_USER / JUDICIAL_PASSWORD 環境變數")
    result, meta = post("/Auth", {"user": user, "password": password}, with_meta=True)
    if not isinstance(result, dict):
        raise RuntimeError("司法院 API 驗證回應格式錯誤")
    token = result.get("Token") or result.get("token")
    if not token:
        if "目前非本 API 服務時間" in str(result.get("error") or ""):
            raise JudicialRequestError("service_closed", path="/Auth",
                                       http_status=meta["http_status"],
                                       attempts=meta["attempts"],
                                       elapsed_ms=meta["elapsed_ms"])
        raise RuntimeError("司法院 API 驗證失敗")
    return token


def changed_jids(token: str, on_metadata=None) -> List[str]:
    result = post("/JList", {"token": token})
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError("Judicial JList rejected the request")
    if not isinstance(result, list):
        raise ValueError("Judicial JList returned an invalid response")
    jids: List[str] = []
    metadata = {}
    for day in result:
        if not isinstance(day, dict):
            raise ValueError("Judicial JList day is invalid")
        entries = day.get("list", day.get("LIST"))
        if not isinstance(entries, list):
            raise ValueError("Judicial JList day has no JID list")
        for item in entries:
            jid = normalize_jid(item)
            metadata.setdefault(jid, {"list_date": str(day.get("DATE") or day.get("date") or ""),
                                      "source_url": BASE + "/JList",
                                      "position": len(jids)})
            jids.append(jid)
    if on_metadata is not None:
        on_metadata(metadata)
    return list(dict.fromkeys(jids))


def fetch_judgment(token: str, jid: str) -> Dict[str, Any]:
    normalized = normalize_jid(jid)
    started = time.monotonic()
    # Two attempts per run; the persisted retry queue supplies a second,
    # independent run before a stable official document error is isolated.
    for attempt in range(2):
        result, meta = post("/JDoc", {"token": token, "j": normalized}, with_meta=True)
        if not isinstance(result, dict):
            raise JudicialRequestError("invalid_payload", path="/JDoc",
                                       http_status=meta["http_status"], attempts=attempt + 1,
                                       elapsed_ms=int((time.monotonic() - started) * 1000))
        error = str(result.get("error") or "")
        if "目前非本 API 服務時間" in error:
            raise JudicialRequestError("service_closed", path="/JDoc",
                                       http_status=meta["http_status"], attempts=attempt + 1,
                                       elapsed_ms=int((time.monotonic() - started) * 1000))
        transient = any(marker in error for marker in ("物件參考", "NullReference", "暫時"))
        if transient and attempt == 1:
            raise JudicialRequestError("upstream_document_error", path="/JDoc",
                                       http_status=meta["http_status"], attempts=attempt + 1,
                                       elapsed_ms=int((time.monotonic() - started) * 1000),
                                       response_error_hash=hashlib.sha256(error.encode()).hexdigest())
        if not transient:
            return result
        _backoff(attempt)


def _versioned_evidence(row: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Keep corrections/removals as separate immutable Evidence versions."""
    content_hash = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    row["evidence_id"] = hashlib.sha256(
        f"judicial_court_records|{row['source']['record_id']}|{content_hash}|{row['fact']['type']}"
        .encode("utf-8")).hexdigest()
    row["source"]["content_hash"] = content_hash
    return row


def _document_evidence(jid: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    error = str(doc.get("error") or "")
    if error:
        if not any(marker in error for marker in ("移除", "不存在", "不公開", "已刪除")):
            raise JudicialRequestError("upstream_document_error", path="/JDoc",
                                       http_status=200,
                                       response_error_hash=hashlib.sha256(error.encode()).hexdigest())
        return _versioned_evidence(make_evidence(
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
    return _versioned_evidence(make_evidence(
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


def evidence_rows(on_error=None, *, batch_index=0, batch_size=200,
                  on_window=None, on_success=None, retry_jids=None,
                  retry_window=None, snapshot_jids=None, workers=1,
                  snapshot_window=None) -> Iterable[Dict[str, Any]]:
    if batch_index < 0 or not 1 <= batch_size <= 500 or not 1 <= workers <= 3:
        raise ValueError("Invalid judicial batch bounds")
    token = get_token()
    if snapshot_jids is not None:
        selected = [normalize_jid(jid) for jid in snapshot_jids]
        window = {**(snapshot_window or {}), "selected": len(selected),
                  "snapshot": True}
    elif retry_jids is None:
        metadata = {}
        jids = changed_jids(token, on_metadata=metadata.update)
        start = batch_index * batch_size
        selected = jids[start:start + batch_size]
        window = {"total": len(jids), "batch_index": batch_index,
                  "batch_size": batch_size, "selected": len(selected),
                  "window_id": hashlib.sha256("\n".join(jids).encode("utf-8")).hexdigest(),
                  "remaining": max(0, len(jids) - start - len(selected)),
                  "selected_metadata": {jid: metadata.get(jid) for jid in selected}}
    else:
        selected = [normalize_jid(jid) for jid in retry_jids]
        if retry_window and retry_window.get("snapshot"):
            window = {**retry_window, "selected": len(selected), "retry_only": True}
        else:
            metadata = {}
            jids = changed_jids(token, on_metadata=metadata.update)
            window = {**(retry_window or {}), "total": len(jids),
                      "current_window_id": hashlib.sha256("\n".join(jids).encode("utf-8")).hexdigest(),
                      "selected": len(selected), "retry_only": True,
                      "selected_metadata": {jid: metadata.get(jid) for jid in selected}}
    if on_window is not None:
        on_window(window)
    def fetch_one(jid):
        try:
            doc = fetch_judgment(token, jid)
            row = _document_evidence(jid, doc)
        except Exception as exc:
            return jid, None, exc
        return jid, row, None

    def yield_results(results):
        for jid, row, exc in results:
            if exc is not None:
                if on_error is None:
                    raise exc
                on_error(jid, exc)
                continue
            if on_success is not None:
                on_success(jid)
            yield row

    if workers == 1:
        yield from yield_results(map(fetch_one, selected))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            yield from yield_results(pool.map(fetch_one, selected))
