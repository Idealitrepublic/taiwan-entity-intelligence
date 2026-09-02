import json
import urllib.parse
import urllib.request

from src.public_evidence import collect_public_evidence
from src.v2server import COMPANY_API, DIRECTOR_API, _company_filter

COMPANIES = {
    "23060248": "全家便利商店股份有限公司",
    "22099131": "台灣積體電路製造股份有限公司",
    "22555003": "統一超商股份有限公司",
}


def test_multiple_companies_company_and_director_apis_and_public_sources():
    for uniform, expected_name in COMPANIES.items():
        company_rows = _company_filter(COMPANY_API, "Business_Accounting_NO", uniform, 1)
        assert company_rows, f"MOEA company API returned no rows: {uniform}"
        assert company_rows[0].get("Company_Name") == expected_name, company_rows[0]

        director_rows = _company_filter(DIRECTOR_API, "Business_Accounting_NO", uniform, 20)
        assert director_rows, f"MOEA director API returned no rows: {uniform}"

        public = collect_public_evidence(expected_name, [])
        statuses = public.get("statuses", {})

        # Every non-judicial category must be callable and backed by readable rows.
        for category in ("裁罰", "165", "標案"):
            item = statuses.get(category)
            assert isinstance(item, dict), (uniform, category, statuses)
            assert item.get("status") in {"ok", "partial"}, (uniform, category, item)
            datasets = item.get("datasets") or []
            assert datasets, (uniform, category, item)
            for dataset in datasets:
                assert dataset.get("status") == "ok", (uniform, category, dataset)
                assert int(dataset.get("rows_read") or 0) > 0, (uniform, category, dataset)

        total = statuses.get("資料源總數")
        assert isinstance(total, dict), statuses
        assert int(total.get("configured_datasets") or 0) >= 13, total

        # Judicial is intentionally excluded from the live-source requirement.
        assert "裁判書" in statuses, statuses
