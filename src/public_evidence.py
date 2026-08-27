"""Live public-record evidence connectors.

A match means only that an official source record contains the searched
observable. It is not a legal or criminal conclusion.
"""
import csv
import io
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

# Government open-data datasets currently used by T.E.I.
DATASET_IDS = {
    "labor_penalties": "109896",          # 勞動法令違反
    "labor_gender_penalties": "109897",  # 性別平等工作法
    "employment_service_penalties": "110908",  # 就業服務法
    "scam_domains": "176455",            # 165 遭停止解析涉詐網站
    "fake_investment_sites": "160055",   # 165 假投資／博弈網站
    "scam_refutations": "38262",         # 165 詐騙闢謠
    "digital_scam_domains": "165027",    # 數位產業署詐騙網域停止解析
    # Representative procurement datasets published by government agencies.
    "procurement_armor": "23838",        # 役政署採購決標
    "procurement_cpc": "30136",          # 中油探採事業部採購
    "procurement_hakka": "164996",       # 客委會採購案件
    "procurement_ntb": "25622",          # 財政部臺北國稅局採購
    "procurement_moda": "161985",         # 數位發展部歷年採購
    "procurement_highway": "91516",       # 高速公路局採購標案
}

DIRECT_RESOURCES = {
    "109896": "https://apiservice.mol.gov.tw/OdService/download/A17000000J-020050-MUA",
}

DATASET_LABELS = {
    "109896": "勞動部／違反勞動法令事業單位",
    "109897": "勞動部／性別平等工作法違法事業單位",
    "110908": "勞動部／就業服務法違法事業單位",
    "176455": "165反詐騙／遭停止解析涉詐網站",
    "160055": "165反詐騙／假投資(博弈)網站",
    "38262": "165反詐騙／詐騙闢謠專區",
    "165027": "數位產業署／詐騙網域停止解析網址清單",
    "23838": "役政署／政府採購決標案件",
    "30136": "台灣中油／探採事業部採購公告",
    "164996": "客家委員會／年度採購案件",
    "25622": "財政部臺北國稅局／採購案",
    "161985": "數位發展部／歷年採購案件",
    "91516": "交通部高速公路局／採購標案",
}


def _get(url, timeout=30, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "TaiwanEntityIntelligence/0.6"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url):
    try:
        return json.loads(_get(url).decode("utf-8-sig", "ignore"))
    except Exception:
        return {}


def _dataset_resources(dataset_id):
    urls = []
    meta = _json("https://data.gov.tw/api/v2/rest/dataset/{}".format(dataset_id))
    distributions = meta.get("distribution") or meta.get("distributions") or []
    if isinstance(distributions, dict):
        distributions = list(distributions.values())
    for item in distributions:
        if isinstance(item, dict):
            url = item.get("resourceDownloadURL") or item.get("downloadURL") or item.get("url")
            if url:
                urls.append(url)
    if dataset_id in DIRECT_RESOURCES:
        urls.append(DIRECT_RESOURCES[dataset_id])
    return list(dict.fromkeys(urls))


def _read_rows(url, limit=20000):
    raw = _get(url)
    text = raw.decode("utf-8-sig", "replace")
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                for key in ("data", "records", "result", "results", "payload"):
                    if isinstance(obj.get(key), list):
                        return [x for x in obj[key] if isinstance(x, dict)][:limit]
                    if isinstance(obj.get(key), dict):
                        for subkey in ("data", "records", "result", "results", "search_result"):
                            if isinstance(obj[key].get(subkey), list):
                                return [x for x in obj[key][subkey] if isinstance(x, dict)][:limit]
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)][:limit]
        except Exception:
            pass
    try:
        dialect = csv.Sniffer().sniff(text[:8192])
    except csv.Error:
        dialect = csv.excel
    return [dict(row) for _, row in zip(range(limit), csv.DictReader(io.StringIO(text), dialect=dialect))]


def _norm(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _match_row(row, needles):
    hay = _norm(" ".join(str(v) for v in row.values()))
    return any(n and n in hay for n in needles)


def _evidence(source, record_id, title, summary, url, raw, fact_type, matched_terms=None):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "evidence_id": "{}:{}".format(source, record_id),
        "schema_version": "1.0",
        "observed_at": now,
        "retrieved_at": now,
        "source": {"type": "government_open_data", "name": source, "record_id": str(record_id), "url": url},
        "fact": {"type": fact_type, "title": title, "summary": summary, "matched_terms": matched_terms or []},
        "confidence": 1.0,
        "status": "active",
        "raw": raw,
    }


def _collect_dataset(dataset_key, needles, source_name, fact_type, max_rows=100):
    out = []
    dataset_id = DATASET_IDS[dataset_key]
    resources = _dataset_resources(dataset_id)
    if not resources:
        return out, {"status": "source_unavailable", "dataset_id": dataset_id, "label": DATASET_LABELS.get(dataset_id, source_name), "matched": 0}
    for url in resources:
        try:
            rows = _read_rows(url)
        except Exception:
            continue
        for idx, row in enumerate(rows):
            if not _match_row(row, needles):
                continue
            hay = _norm(" ".join(str(v) for v in row.values()))
            matched = [n for n in needles if n in hay]
            record_id = (
                row.get("處分字號") or row.get("處分書文號") or row.get("網域") or row.get("網址")
                or row.get("編號") or row.get("案件編號") or row.get("採購編號") or row.get("案號") or idx
            )
            title = (
                row.get("事業單位名稱") or row.get("事業單位名稱或負責人") or row.get("網域")
                or row.get("網站名稱") or row.get("標題") or row.get("標案名稱") or row.get("標案案名")
                or row.get("案名") or row.get("tender_name") or row.get("得標者") or row.get("得標廠商")
                or row.get("successful_bidder") or source_name
            )
            out.append(_evidence(
                source_name,
                record_id,
                title,
                "官方公開資料命中查詢實體；這是來源紀錄，不等於法律上的違法、涉詐或其他結論。",
                "https://data.gov.tw/dataset/{}".format(dataset_id),
                row,
                fact_type,
                matched,
            ))
            if len(out) >= max_rows:
                break
        if len(out) >= max_rows:
            break
    return out, {"status": "ok", "dataset_id": dataset_id, "label": DATASET_LABELS.get(dataset_id, source_name), "matched": len(out)}


def _judicial_recent(needles, max_docs=50):
    user = os.getenv("JUDICIAL_API_USER") or os.getenv("JUDICIAL_USER")
    password = os.getenv("JUDICIAL_API_PASSWORD") or os.getenv("JUDICIAL_PASSWORD")
    if not user or not password:
        return [], {"status": "not_configured", "message": "司法院 API 尚未設定帳密。", "matched": 0}
    try:
        def post(path, payload, timeout=30):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                "https://data.judicial.gov.tw/jdg/api" + path,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "TaiwanEntityIntelligence/0.6"},
            )
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))

        auth = post("/Auth", {"user": user, "password": password})
        token = auth.get("Token") or auth.get("token")
        if not token:
            return [], {"status": "auth_failed", "message": "司法院 API 驗證失敗。", "matched": 0}
        listing = post("/JList", {"token": token})
        ids = []
        for day in listing if isinstance(listing, list) else []:
            if isinstance(day, dict):
                ids.extend(day.get("list", []))
        ids = list(dict.fromkeys(ids))[:max_docs]
        out = []
        for jid in ids:
            try:
                doc = post("/JDoc", {"token": token, "j": jid})
                content = _norm(json.dumps(doc, ensure_ascii=False))
                if any(n in content for n in needles):
                    out.append(_evidence(
                        "司法院裁判書開放 API",
                        jid,
                        doc.get("JTITLE") or jid,
                        "近期裁判書全文包含查詢實體名稱；仍需人工確認當事人、案件關係與判決主文。",
                        "https://data.judicial.gov.tw/",
                        doc,
                        "judgment",
                        [n for n in needles if n in content],
                    ))
            except Exception:
                continue
        return out, {"status": "ok", "checked": len(ids), "matched": len(out)}
    except Exception as exc:
        return [], {"status": "error", "message": str(exc), "matched": 0}


def collect_public_evidence(company_name, people=None):
    needles = [_norm(company_name)] + [_norm(p) for p in (people or []) if p]
    needles = [n for n in needles if len(n) >= 2]
    evidence = []
    statuses = {}

    items = [
        ("labor_penalties", "勞動部／違反勞動法令事業單位", "administrative_penalty", "裁罰"),
        ("labor_gender_penalties", "勞動部／性別平等工作法違法事業單位", "administrative_penalty", "裁罰"),
        ("employment_service_penalties", "勞動部／就業服務法違法事業單位", "administrative_penalty", "裁罰"),
        ("scam_domains", "165反詐騙／遭停止解析涉詐網站", "anti_fraud_domain", "165"),
        ("fake_investment_sites", "165反詐騙／假投資(博弈)網站", "anti_fraud_site", "165"),
        ("scam_refutations", "165反詐騙／詐騙闢謠專區", "anti_fraud_refutation", "165"),
        ("digital_scam_domains", "數位產業署／詐騙網域停止解析網址清單", "anti_fraud_domain", "詐騙網域"),
        ("procurement_armor", "役政署／政府採購決標案件", "government_tender", "標案"),
        ("procurement_cpc", "台灣中油／探採事業部採購公告", "government_tender", "標案"),
        ("procurement_hakka", "客家委員會／年度採購案件", "government_tender", "標案"),
        ("procurement_ntb", "財政部臺北國稅局／採購案", "government_tender", "標案"),
        ("procurement_modа", "數位發展部／歷年採購案件", "government_tender", "標案"),
        ("procurement_highway", "交通部高速公路局／採購標案", "government_tender", "標案"),
    ]
    # Typo-safe normalization for the key added above.
    items = [("procurement_moda" if key == "procurement_modа" else key, source, fact, sk) for key, source, fact, sk in items]

    for key, source, fact_type, status_key in items:
        rows, status = _collect_dataset(key, needles, source, fact_type)
        evidence.extend(rows)
        bucket = statuses.setdefault(status_key, {"status": "ok", "matched": 0})
        bucket["matched"] = int(bucket.get("matched", 0)) + int(status.get("matched", 0))
        bucket.setdefault("datasets", []).append(status)

    judicial, jstatus = _judicial_recent(needles)
    evidence.extend(judicial)
    statuses["裁判書"] = jstatus

    return {
        "evidence": evidence,
        "statuses": statuses,
        "summary": {
            "total": len(evidence),
            "by_type": {
                "裁判書": sum(1 for x in evidence if x["fact"]["type"] == "judgment"),
                "裁罰": sum(1 for x in evidence if x["fact"]["type"] == "administrative_penalty"),
                "165": sum(1 for x in evidence if x["fact"]["type"].startswith("anti_fraud")),
                "標案": sum(1 for x in evidence if x["fact"]["type"] == "government_tender"),
            },
        },
        "note": "公開紀錄命中只表示來源資料存在名稱／觀測值相符；不代表該實體已被認定違法或涉詐。同名人物與關聯關係仍需核對原始資料。",
    }
