"""Resolve a company's verified website candidate and compare its domain with public anti-fraud domain lists."""
from __future__ import annotations

import csv
import io
import json
import urllib.parse
import urllib.request
from typing import Any

WEBSITE_OVERRIDES = {
    "23060248": {
        "url": "https://www.family.com.tw/Marketing/zh",
        "source": "台灣就業通公司資料（公司網址）",
        "confidence": "verified_government_source",
    },
}

FRAUD_SOURCES = [
    {"id": "165_fake_investment", "name": "165反詐騙諮詢專線_假投資(博弈)網站", "url": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/033197D4-70F4-45EB-9FB8-6D83532B999A/resource/A00B1802-6A4A-42B4-B842-B66A2D937DAE/download"},
    {"id": "165_blocked_domains", "name": "165反詐騙諮詢專線_遭停止解析涉詐網站", "url": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/29E8E643-88ED-4952-B21E-BD42A3B7108C/resource/EF3880BD-4C86-4D5E-9C3E-1CBF70919743/download"},
    {"id": "moda_blocked_domains", "name": "數位發展部數位產業署聲請詐騙網域名稱停止解析網址清單", "url": "https://www-api.moda.gov.tw/OpenData/Files/16352"},
]


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


def domain_match(candidate: str, target: str) -> bool:
    a, b = clean_host(candidate), clean_host(target)
    return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "T.E.I./3.4"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8-sig", errors="replace")


def parse_csv(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    return [{str(k or "").strip(): str(v or "").strip() for k, v in row.items()} for row in reader]


def source_rows(src: dict[str, str]) -> list[dict[str, Any]]:
    text = fetch_text(src["url"])
    if src["id"] == "moda_blocked_domains":
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "records", "items", "result"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []
    return parse_csv(text)


def find_domain_fields(row: dict[str, Any]) -> list[str]:
    keys = ("網域名稱", "網域", "網址", "網站網址", "WEBURL", "URL", "url", "domain", "DOMAIN", "website", "website_url")
    return [str(row.get(k, "")) for k in keys if row.get(k)]


def main(company_name: str, uniform: str) -> dict[str, Any]:
    website = WEBSITE_OVERRIDES.get(uniform)
    if not website:
        q = urllib.parse.quote(f'"{company_name}" 官方網站')
        website = {
            "url": "",
            "source": "未找到可驗證的政府來源網站；提供搜尋候選",
            "confidence": "search_candidate",
            "search_url": f"https://www.google.com/search?q={q}",
        }
    domain = clean_host(website.get("url", ""))
    matches: list[dict[str, Any]] = []
    source_status: list[dict[str, Any]] = []

    if domain:
        for src in FRAUD_SOURCES:
            try:
                rows = source_rows(src)
                hit_rows = [row for row in rows if any(domain_match(v, domain) for v in find_domain_fields(row))]
                source_status.append({"id": src["id"], "name": src["name"], "status": "ok", "total": len(rows), "matched": len(hit_rows)})
                matches.extend({"source_id": src["id"], "source_name": src["name"], **row} for row in hit_rows[:20])
            except Exception as exc:
                source_status.append({"id": src["id"], "name": src["name"], "status": "error", "matched": 0, "error": str(exc)})

    return {
        "status": "ok",
        "uniform_number": uniform,
        "company_name": company_name,
        "website": website,
        "domain": domain,
        "anti_fraud": {"status": "ok", "matched": len(matches), "records": matches[:50], "sources": source_status, "rule": "exact domain or subdomain; no fuzzy company-name inference"},
        "interpretation": "未命中僅表示該網域在本次檢查的政府公開詐騙網域資料集中沒有相符紀錄；不代表公司或網站因此獲得安全或無違法認定。",
    }


def handler(request):
    try:
        raw = request.get("queryStringParameters") or {}
        uniform = str(raw.get("uniform") or "").strip()
        if not (uniform.isdigit() and len(uniform) == 8):
            return {"statusCode": 400, "body": json.dumps({"error": "uniform must be 8 digits"}, ensure_ascii=False)}
        from src.v2server import build_company
        data = build_company(uniform)
        payload = main(str(data.get("company_name") or uniform), uniform)
        return {"statusCode": 200, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps(payload, ensure_ascii=False)}
    except Exception as exc:
        return {"statusCode": 502, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)}
