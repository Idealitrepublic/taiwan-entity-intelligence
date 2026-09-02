from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "api" / "company-sources.py"
spec = importlib.util.spec_from_file_location("company_sources", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_family_website_domain():
    website = module.resolve_website("全家便利商店股份有限公司", "23060248")
    assert website["url"].startswith("https://www.family.com.tw")
    assert website["confidence"] == "verified_government_source"
    assert module.clean_host(website["url"]) == "family.com.tw"


def test_family_labor_records():
    result = module.company_labor("全家便利商店股份有限公司")
    assert result["status"] == "ok"
    # Current official MOL page has five Labor Standards Act records for the company.
    assert result["matched"] >= 5
    assert any("勞動基準法" in str(row) for row in result["records"])


def test_family_fraud_cross_check():
    result = module.company_fraud("family.com.tw")
    assert result["status"] in {"ok", "partial"}
    # The verified current test case should not falsely match unrelated domains.
    assert result["matched"] == 0
    assert result["rule"].startswith("exact registrable domain")
