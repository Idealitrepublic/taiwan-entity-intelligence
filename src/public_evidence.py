"""Live government public-record evidence connectors used by T.E.I."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

DATASET_IDS = {
    "labor_penalties": "109896", "labor_gender_penalties": "109897", "employment_service_penalties": "110908",
    "scam_domains": "176455", "fake_investment_sites": "160055", "scam_refutations": "38262", "digital_scam_domains": "165027",
    "procurement_armor": "23838", "procurement_cpc": "30136", "procurement_hakka": "164996", "procurement_ntb": "25622",
    "procurement_moda": "161985", "procurement_highway": "91516",
}

DATASET_LABELS = {
    "109896": "勞動部／違反勞動法令事業單位", "109897": "勞動部／性別平等工作法違法事業單位", "110908": "勞動部／就業服務法違法事業單位",
    "176455": "165反詐騙／遭停止解析涉詐網站", "160055": "165反詐騙／假投資(博弈)網站", "38262": "165反詐騙／詐騙闢謠專區", "165027": "數位產業署／詐騙網域停止解析網址清單",
    "23838": "役政署／政府採購決標案件", "30136": "台灣中油／探採事業部採購公告", "164996": "客家委員會／年度採購案件", "25622": "財政部臺北國稅局／採購案",
    "161985": "數位發展部／歷年採購案件", "91516": "交通部高速公路局／採購標案",
}

# Verified current official resource URLs. Direct resources are preferred because
# serverless runtimes may fail on data.gov.tw metadata endpoints even when the
# actual resource is healthy.
DIRECT_RESOURCES = {
    "109896": "https://apiservice.mol.gov.tw/OdService/download/A17000000J-020050-MUA",
    "109897": "https://apiservice.mol.gov.tw/OdService/download/A17000000J-030226-sop",
    "110908": "https://apiservice.mol.gov.tw/OdService/download/A17000000J-030228-p2G",
    "176455": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/29E8E643-88ED-4952-B21E-BD42A3B7108C/resource/EF3880BD-4C86-4D5E-9C3E-1CBF70919743/download",
    "160055": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/033197D4-70F4-45EB-9FB8-6D83532B999A/resource/A00B1802-6A4A-42B4-B842-B66A2D937DAE/download",
    "38262": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/4F4DF9A5-DF4C-4EE8-A50D-869347D38D9E/resource/59234DED-9AC0-4237-AE21-5EF9938EE938/download",
    "165027": "https://www-api.moda.gov.tw/OpenData/Files/16352",
    "23838": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/79F74B1C-C1D0-4204-B0B7-D415F2F9A550/resource/F3C78E84-836B-4385-BC81-C74FBA05D4DF/download",
    "164996": "https://cloud.hakka.gov.tw/Pub/Opendata/DTST20230800004.csv",
    "91516": "https://www.freeway.gov.tw/Download_File_Direct.ashx?FileConditionsID=1&id=295",
}

# Provider has explicitly stopped CSV distribution for dataset 30136.
RETIRED_DATASETS = {
    "30136": "提供機關已停止此資料集下載；請改由政府電子採購網查詢。",
}


def _get(url: str, timeout: int = 35) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "TaiwanEntityIntelligence/4.2", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url: str):
    try:
        return json.loads(_get(url).decode("utf-8-sig", "ignore"))
    except Exception:
        return {}


def _dataset_resources(dataset_id: str) -> list[str]:
    if dataset_id in RETIRED_DATASETS:
        return []
    urls: list[str] = []
    direct = DIRECT_RESOURCES.get(dataset_id)
    if direct:
        urls.append(direct)
    meta = _json(f"https://data.gov.tw/api/v2/rest/dataset/{dataset_id}")
    distributions = meta.get("distribution") or meta.get("distributions") or []
    if isinstance(distributions, dict):
        distributions = list(distributions.values())
    for item in distributions:
        if isinstance(item, dict):
            u = item.get("resourceDownloadURL") or item.get("downloadURL") or item.get("url")
            if u:
                urls.append(u)
    return list(dict.fromkeys(urls))


def _read_rows(url: str, limit: int = 20000):
    text = _get(url).decode("utf-8-sig", "replace")
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)][:limit]
            if isinstance(obj, dict):
                for key in ("data", "records", "result", "results", "payload", "items"):
                    value = obj.get(key)
                    if isinstance(value, list):
                        return [x for x in value if isinstance(x, dict)][:limit]
                    if isinstance(value, dict):
                        for subkey in ("data", "records", "result", "results", "items"):
                            if isinstance(value.get(subkey), list):
                                return [x for x in value[subkey] if isinstance(x, dict)][:limit]
        except Exception:
            pass
    try:
        dialect = csv.Sniffer().sniff(text[:8192])
    except csv.Error:
        dialect = csv.excel
    return [dict(row) for _, row in zip(range(limit), csv.DictReader(io.StringIO(text), dialect=dialect))]


def _norm(v: object) -> str:
    return re.sub(r"\s+", "", str(v or "")).casefold()


def _match_row(row: dict, needles: list[str]) -> bool:
    hay = _norm(" ".join(str(v) for v in row.values()))
    return any(n and n in hay for n in needles)


def _evidence(source: str, dataset_id: str, row: dict, idx: int, fact_type: str, matched_terms: list[str]):
    now = datetime.now(timezone.utc).isoformat()
    record_id = row.get("處分字號") or row.get("處分書文號") or row.get("網域") or row.get("網址") or row.get("編號") or row.get("採購編號") or row.get("案件編號") or row.get("案號") or idx
    title = row.get("事業單位名稱") or row.get("事業單位名稱或負責人") or row.get("網域") or row.get("網址") or row.get("標案名稱") or row.get("標案案名") or row.get("案名") or row.get("tender_name") or row.get("得標者") or row.get("得標廠商") or source
    return {"evidence_id": f"{source}:{record_id}", "schema_version": "1.0", "observed_at": now, "retrieved_at": now,
            "source": {"type": "government_open_data", "name": source, "record_id": str(record_id), "url": f"https://data.gov.tw/dataset/{dataset_id}"},
            "fact": {"type": fact_type, "title": str(title), "summary": "官方公開資料命中查詢實體；這是來源紀錄，不等於法律結論。", "matched_terms": matched_terms},
            "confidence": 1.0, "status": "active", "raw": row}


def _collect_dataset(dataset_key: str, needles: list[str], source_name: str, fact_type: str, max_rows: int = 100):
    dataset_id = DATASET_IDS[dataset_key]
    if dataset_id in RETIRED_DATASETS:
        return [], {"status": "retired", "dataset_id": dataset_id, "label": DATASET_LABELS[dataset_id], "matched": 0, "rows_read": 0, "message": RETIRED_DATASETS[dataset_id]}
    resources = _dataset_resources(dataset_id)
    if not resources:
        return [], {"status": "source_unavailable", "dataset_id": dataset_id, "label": DATASET_LABELS[dataset_id], "matched": 0, "rows_read": 0}
    out, rows_read, last_error = [], 0, None
    for url in resources:
        try:
            rows = _read_rows(url); rows_read += len(rows)
        except Exception as exc:
            last_error = str(exc); continue
        for idx, row in enumerate(rows):
            if _match_row(row, needles):
                terms = [n for n in needles if n in _norm(" ".join(str(v) for v in row.values()))]
                out.append(_evidence(source_name, dataset_id, row, idx, fact_type, terms))
                if len(out) >= max_rows: break
        if len(out) >= max_rows: break
    result = {"status": "ok" if rows_read > 0 else "source_unavailable", "dataset_id": dataset_id, "label": DATASET_LABELS[dataset_id], "matched": len(out), "rows_read": rows_read}
    if last_error and rows_read == 0: result["message"] = last_error
    return out, result


def _judicial_recent(needles, max_docs=50):
    user = os.getenv("JUDICIAL_API_USER") or os.getenv("JUDICIAL_USER")
    password = os.getenv("JUDICIAL_API_PASSWORD") or os.getenv("JUDICIAL_PASSWORD")
    if not user or not password:
        return [], {"status": "not_configured", "message": "司法院 API 尚未設定帳密。", "matched": 0}
    return [], {"status": "not_implemented_in_public_runtime", "message": "司法院保留為官方查詢入口。", "matched": 0}


def collect_public_evidence(company_name: str, people=None):
    needles = [_norm(company_name)] + [_norm(p) for p in (people or []) if p]
    needles = [n for n in needles if len(n) >= 2]
    evidence, statuses = [], {}
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
        ("procurement_moda", "數位發展部／歷年採購案件", "government_tender", "標案"),
        ("procurement_highway", "交通部高速公路局／採購標案", "government_tender", "標案"),
    ]
    group_meta = {}
    for key, source, fact_type, group in items:
        rows, st = _collect_dataset(key, needles, source, fact_type)
        evidence.extend(rows)
        meta = group_meta.setdefault(group, {"status": "ok", "matched": 0, "rows_read": 0, "datasets": []})
        meta["matched"] += int(st.get("matched") or 0); meta["rows_read"] += int(st.get("rows_read") or 0); meta["datasets"].append(st)
        if st.get("status") == "source_unavailable": meta["status"] = "partial"
    statuses.update(group_meta)
    judicial, jstatus = _judicial_recent(needles); evidence.extend(judicial); statuses["裁判書"] = jstatus
    statuses["資料源總數"] = {"status": "ok", "matched": len(items), "configured_datasets": len(items), "live_categories": ["裁罰", "165", "詐騙網域", "標案"]}
    return evidence, statuses
