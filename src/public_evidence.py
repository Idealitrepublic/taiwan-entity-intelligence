"""Bounded public-record evidence connectors.

The connectors deliberately return source-backed records only. A match is not
an allegation of wrongdoing; it means the source record contains the entity
name (or a related observable such as a domain).
"""
import csv
import io
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

DATASET_PAGES = {
    "labor_penalties": "https://data.gov.tw/dataset/109896",
    "scam_domains": "https://data.gov.tw/dataset/176455",
    "fake_investment_sites": "https://data.gov.tw/dataset/160055",
    "scam_refutations": "https://data.gov.tw/dataset/38262",
}


def _get(url, timeout=12, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "TaiwanEntityIntelligence/0.3"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _dataset_csv_urls(page_url):
    html = _get(page_url).decode("utf-8", "ignore")
    # data.gov.tw resource links currently point to opdadm.moi.gov.tw for
    # these CSV resources. Keep the resolver generic so resource IDs can move.
    urls = re.findall(r'https?://opdadm\.moi\.gov\.tw/[^"<> ]+', html)
    return list(dict.fromkeys(urls))


def _read_csv_url(url, limit=5000):
    raw = _get(url)
    text = raw.decode("utf-8-sig", "ignore")
    try:
        dialect = csv.Sniffer().sniff(text[:4096])
    except csv.Error:
        dialect = csv.excel
    rows = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [dict(row) for _, row in zip(range(limit), rows)]


def _norm(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _match_row(row, needles):
    hay = _norm(" ".join(str(v) for v in row.values()))
    return any(n and n in hay for n in needles)


def _evidence(source, record_id, title, summary, url, raw, fact_type="public_record", confidence=1.0):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "evidence_id": "{}:{}".format(source, record_id),
        "schema_version": "1.0",
        "observed_at": now,
        "retrieved_at": now,
        "source": {"type": "government_open_data", "name": source, "record_id": str(record_id), "url": url},
        "fact": {"type": fact_type, "title": title, "summary": summary},
        "confidence": confidence,
        "status": "active",
        "raw": raw,
    }


def _collect_dataset(dataset_key, needles, source_name, fact_type, max_rows=100):
    out = []
    page = DATASET_PAGES[dataset_key]
    try:
        urls = _dataset_csv_urls(page)
        for url in urls[:5]:
            try:
                rows = _read_csv_url(url)
            except Exception:
                continue
            for idx, row in enumerate(rows):
                if not _match_row(row, needles):
                    continue
                record_id = row.get("處分字號") or row.get("處分書文號") or row.get("網域") or row.get("網址") or row.get("編號") or idx
                title = row.get("事業單位名稱") or row.get("事業單位名稱或負責人") or row.get("網域") or row.get("網站名稱") or row.get("標題") or source_name
                summary = "來源資料含有與目前查詢實體名稱相符的公開紀錄；請回看原始資料確認脈絡。"
                out.append(_evidence(source_name, record_id, title, summary, url, row, fact_type))
                if len(out) >= max_rows:
                    return out
    except Exception:
        pass
    return out


def _judicial_recent(needles, max_docs=20):
    """Use the official Judicial Yuan API only when credentials are configured.

    The API requires an account/token and is available during its published
    service window. Without credentials we return a transparent unavailable
    status rather than scraping the public judgment UI.
    """
    user = os.getenv("JUDICIAL_API_USER")
    password = os.getenv("JUDICIAL_API_PASSWORD")
    if not user or not password:
        return [], {"status": "not_configured", "message": "司法院裁判書 API 需要資料開放平台帳密。"}
    try:
        body = json.dumps({"user": user, "password": password}).encode("utf-8")
        req = urllib.request.Request("https://data.judicial.gov.tw/jdg/api/Auth", data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": "TaiwanEntityIntelligence/0.3"})
        auth = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8"))
        token = auth.get("token")
        if not token:
            return [], {"status": "auth_failed"}
        req = urllib.request.Request("https://data.judicial.gov.tw/jdg/api/JList", data=json.dumps({"token": token}).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "User-Agent": "TaiwanEntityIntelligence/0.3"})
        listing = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8"))
        ids = []
        def walk(x):
            if isinstance(x, str) and ("," in x or x.startswith("J")):
                ids.append(x)
            elif isinstance(x, dict):
                for v in x.values(): walk(v)
            elif isinstance(x, list):
                for v in x: walk(v)
        walk(listing)
        ids = list(dict.fromkeys(ids))[:max_docs]
        out = []
        for jid in ids:
            try:
                req = urllib.request.Request("https://data.judicial.gov.tw/jdg/api/JDoc", data=json.dumps({"token": token, "j": jid}).encode("utf-8"),
                                             headers={"Content-Type": "application/json", "User-Agent": "TaiwanEntityIntelligence/0.3"})
                doc = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8"))
                content = json.dumps(doc, ensure_ascii=False)
                if not any(n in _norm(content) for n in needles):
                    continue
                out.append(_evidence("司法院裁判書開放 API", jid,
                                     doc.get("JTITLE") or jid,
                                     "近期裁判書全文包含查詢實體名稱；需人工確認當事人身分與案件脈絡。",
                                     "https://data.judicial.gov.tw/jdg/api/JDoc", doc, "judgment"))
            except Exception:
                continue
        return out, {"status": "ok", "checked": len(ids)}
    except Exception as exc:
        return [], {"status": "error", "message": str(exc)}


def collect_public_evidence(company_name, people=None):
    needles = [_norm(company_name)] + [_norm(p) for p in (people or []) if p]
    needles = [n for n in needles if len(n) >= 2]
    evidence = []
    statuses = {}

    evidence += _collect_dataset("labor_penalties", needles, "勞動部／違反勞動法令事業單位", "administrative_penalty")
    statuses["裁罰"] = "checked"
    evidence += _collect_dataset("scam_domains", needles, "165反詐騙諮詢專線_遭停止解析涉詐網站", "anti_fraud_domain")
    evidence += _collect_dataset("fake_investment_sites", needles, "165反詐騙諮詢專線_假投資(博弈)網站", "anti_fraud_site")
    evidence += _collect_dataset("scam_refutations", needles, "165反詐騙諮詢專線－詐騙闢謠專區", "anti_fraud_refutation")
    statuses["165"] = "checked"

    judicial, judicial_status = _judicial_recent(needles)
    evidence += judicial
    statuses["裁判書"] = judicial_status

    return {"evidence": evidence, "statuses": statuses,
            "note": "公開紀錄命中僅表示來源資料存在名稱／觀測值相符，不代表該實體已被認定違法或涉詐。"}
