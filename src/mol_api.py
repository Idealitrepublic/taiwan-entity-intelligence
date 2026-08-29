"""Official Ministry of Labor open-data API adapter for live penalties."""
import json
import urllib.parse
import urllib.request

BASE = "https://apiservice.mol.gov.tw/OdService/rest/datastore"
DATASETS = {
    "labor_standards": "A17000000J-030225-gB0",
    # Additional datasets are resolved through the MOL metadata API when needed.
}


def _get(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": "TaiwanEntityIntelligence/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig", "ignore"))


def search_labor_standards(company_name: str, limit: int = 50, offset: int = 0):
    name = str(company_name or "").strip()
    if not name:
        return [], {"status": "empty_query", "matched": 0}
    limit = min(max(int(limit), 1), 100)
    offset = max(int(offset), 0)
    filters = json.dumps({"事業單位名稱或負責人": name}, ensure_ascii=False, separators=(",", ":"))
    params = urllib.parse.urlencode({"filters": filters, "limit": limit, "offset": offset})
    data = _get(f"{BASE}/{DATASETS['labor_standards']}?{params}")
    rows = data.get("result", {}).get("data", []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        rows = []
    return rows, {"status": "ok", "dataset_id": "109896", "matched": len(rows), "offset": offset, "limit": limit}
