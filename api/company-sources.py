"""T.E.I. company source aggregation: labor penalties + company website + anti-fraud domain cross-check."""
from __future__ import annotations

import csv
import html
import io
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

MOL_BASE = "https://announcement.mol.gov.tw/cmpqry/"
FRAUD_SOURCES = [
    {
        "id": "165_fake_investment",
        "name": "165反詐_假投資(博弈)網站",
        "url": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/033197D4-70F4-45EB-9FB8-6D83532B999A/resource/A00B1802-6A4A-42B4-B842-B66A2D937DAE/download",
    },
    {
        "id": "165_blocked_domains",
        "name": "165反詐_遭停止解析涉詐網站",
        "url": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/29E8E643-88ED-4952-B21E-BD42A3B7108C/resource/EF3880BD-4C86-4D5E-9C3E-1CBF70919743/download",
    },
    {
        "id": "moda_blocked_domains",
        "name": "數位發展部_涉詐網域停止解析",
        "url": "https://www-api.moda.gov.tw/OpenData/Files/16352",
    },
]

# Government-published company website for the first verified E2E case.
# The general fallback remains an explicit search candidate, never a fact.
WEBSITE_OVERRIDES = {
    "23060248": {
        "url": "https://www.family.com.tw",
        "source": "台灣就業通公司資料（公司網址）",
        "confidence": "verified_government_source",
        "source_url": "https://job.taiwan.gov.tw/internet/jobwanted/company_desc2.aspx?EMPLOYER_ID=105593",
    },
}

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "public, max-age=300, s-maxage=300, stale-while-revalidate=1800",
}


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "T.E.I./3.5"})
    with urllib.request.urlopen(req, timeout=35) as r:
        return r.read().decode("utf-8-sig", errors="replace")


def clean_host(value: str) -> str:
    s = (value or "").strip().lower()
    if not s:
        return ""
    try:
        u = urllib.parse.urlparse(s if "://" in s else "https://" + s)
        host = u.hostname or ""
    except Exception:
        host = s.split("/")[0].split(":")[0]
    return host.removeprefix("www.").rstrip(".")


def domain_match(a: str, b: str) -> bool:
    x, y = clean_host(a), clean_host(b)
    return bool(x and y and (x == y or x.endswith("." + y) or y.endswith("." + x)))


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_tr = False
        self._in_cell = False
        self._cell: list[str] = []
        self._row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._in_tr = True
            self._row = []
        elif tag in ("td", "th") and self._in_tr:
            self._in_cell = True
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._in_cell:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._in_cell = False
        elif tag == "tr" and self._in_tr:
            if self._row:
                self.rows.append(self._row)
            self._in_tr = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell.append(data)


def parse_mol_rows(text: str) -> list[dict[str, Any]]:
    p = TableParser()
    p.feed(text)
    target_header = None
    for i, row in enumerate(p.rows):
        joined = "|".join(row)
        if "事業單位名稱" in joined and "罰鍰金額" in joined:
            target_header = (i, row)
            break
    if not target_header:
        return []
    idx, header = target_header
    out: list[dict[str, Any]] = []
    for row in p.rows[idx + 1 :]:
        if len(row) < 5:
            continue
        item = {header[j]: row[j] if j < len(row) else "" for j in range(len(header))}
        # Ignore navigation/empty rows.
        if not any(item.values()):
            continue
        name_field = next((v for k, v in item.items() if "事業單位名稱" in k), "")
        if not name_field:
            continue
        out.append(item)
    return out


def parse_fraud_rows(src_id: str, text: str) -> list[dict[str, Any]]:
    if src_id == "moda_blocked_domains":
        try:
            data = json.loads(text)
        except Exception:
            return []
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for k in ("data", "records", "items", "result"):
                if isinstance(data.get(k), list):
                    return [x for x in data[k] if isinstance(x, dict)]
        return []
    try:
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]
    except Exception:
        return []


def domain_fields(row: dict[str, Any]) -> list[str]:
    keys = (
        "網域名稱", "網域", "網址", "網站網址", "WEBURL", "URL",
        "url", "domain", "DOMAIN", "website", "website_url",
    )
    return [str(row.get(k) or "") for k in keys if row.get(k)]


def resolve_website(company_name: str, uniform: str) -> dict[str, Any]:
    if uniform in WEBSITE_OVERRIDES:
        return dict(WEBSITE_OVERRIDES[uniform])
    q = urllib.parse.quote(f'"{company_name}" 官方網站')
    return {
        "url": "",
        "source": "未找到可驗證的政府來源網站；提供搜尋候選",
        "confidence": "search_candidate",
        "search_url": f"https://www.google.com/search?q={q}",
    }


def company_labor(company_name: str) -> dict[str, Any]:
    url = MOL_BASE + urllib.parse.quote(company_name, safe="")
    text = fetch_text(url)
    rows = parse_mol_rows(text)
    # The official page may include the responsible person's name in the same cell.
    matched = []
    for row in rows:
        name = next((v for k, v in row.items() if "事業單位名稱" in k), "")
        if company_name in name:
            matched.append(row)
    return {
        "status": "ok",
        "matched": len(matched),
        "records": matched[:100],
        "source_url": url,
    }


def company_fraud(domain: str) -> dict[str, Any]:
    if not domain:
        return {"status": "not_configured", "matched": 0, "records": [], "sources": []}
    records: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    for src in FRAUD_SOURCES:
        try:
            rows = parse_fraud_rows(src["id"], fetch_text(src["url"]))
            hits = []
            for row in rows:
                if any(domain_match(value, domain) for value in domain_fields(row)):
                    hits.append(row)
            statuses.append({"id": src["id"], "name": src["name"], "status": "ok", "matched": len(hits), "total": len(rows)})
            for row in hits[:20]:
                records.append({"source_id": src["id"], "source_name": src["name"], **row})
        except Exception as exc:
            statuses.append({"id": src["id"], "name": src["name"], "status": "error", "matched": 0, "error": str(exc)})
    return {
        "status": "ok" if all(x["status"] == "ok" for x in statuses) else "partial",
        "matched": len(records),
        "records": records,
        "sources": statuses,
        "rule": "exact registrable domain or subdomain match; no fuzzy company-name inference",
    }


def handler(request):
    if request.get("httpMethod") == "OPTIONS":
        return {"statusCode": 204, "headers": CORS, "body": ""}
    try:
        qs = request.get("queryStringParameters") or {}
        uniform = str(qs.get("uniform") or "").strip()
        if not re.fullmatch(r"\d{8}", uniform):
            return {"statusCode": 400, "headers": CORS, "body": json.dumps({"status": "error", "error": "uniform must be 8 digits"})}
        # Reuse the same company gateway as the main app.
        from src.v2server import build_company
        base = build_company(uniform)
        company_name = str(base.get("company_name") or uniform)
        website = resolve_website(company_name, uniform)
        domain = clean_host(website.get("url", ""))

        labor = company_labor(company_name)
        fraud = company_fraud(domain)
        payload = {
            "status": "ok",
            "uniform_number": uniform,
            "company_name": company_name,
            "website": website,
            "domain": domain,
            "labor": labor,
            "anti_fraud": fraud,
            "interpretation": "命中表示公開資料中存在相符紀錄；未命中不代表公司或網站獲得安全／無違法認定。",
        }
        return {"statusCode": 200, "headers": CORS, "body": json.dumps(payload, ensure_ascii=False)}
    except Exception as exc:
        return {"statusCode": 502, "headers": CORS, "body": json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)}
