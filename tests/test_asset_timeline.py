import unittest
from pathlib import Path
from unittest.mock import Mock

from src.asset_timeline import MAX_TIMELINE_ROWS, build_asset_timeline
from src.entities.api import dispatch_entity_api
from src.entities.repository import EntityFeatureUnavailable, EntityRepository

POLITICIAN = "11111111-1111-4111-8111-111111111111"
COMPANY = "22222222-2222-4222-8222-222222222222"


def declaration(identifier, year, name, *, amount=None, quantity=None,
                company_entity_id=None, company_name=None):
    return {
        "id": identifier,
        "politician_id": POLITICIAN,
        "declaration_year": year,
        "asset_type": "STOCK",
        "asset_name": name,
        "amount": amount,
        "currency": "TWD" if amount is not None else None,
        "quantity": quantity,
        "quantity_unit": "股" if quantity is not None else None,
        "company_name": company_name,
        "company_entity_id": company_entity_id,
        "primary_evidence": {
            "id": identifier,
            "source_name": "監察院廉政專刊財產申報資料",
            "source_record_id": f"record-{identifier}",
            "source_url": "https://sunshine.cy.gov.tw/",
        },
    }


class AssetTimelineTests(unittest.TestCase):
    def test_adjacent_year_changes_are_objective_and_evidence_backed(self):
        rows = [
            declaration("a", 2024, "測試公司股票", amount="100", quantity="10",
                        company_entity_id=COMPANY, company_name="測試公司"),
            declaration("b", 2024, "持續股票", amount="50", quantity="5"),
            declaration("c", 2024, "不再申報股票", amount="20"),
            declaration("d", 2025, "測試公司股票", amount="130", quantity="12",
                        company_entity_id=COMPANY, company_name="測試公司"),
            declaration("e", 2025, "持續股票", amount="50", quantity="5"),
            declaration("f", 2025, "新增股票", amount="30"),
        ]
        result = build_asset_timeline(rows, max_years=10)
        latest = result["years"][1]
        statuses = {change["asset_name"]: change["status"] for change in latest["changes"]}
        self.assertEqual(statuses["測試公司股票"], "INCREASED")
        self.assertEqual(statuses["持續股票"], "CONTINUED")
        self.assertEqual(statuses["新增股票"], "NEW")
        self.assertEqual(statuses["不再申報股票"], "NO_LONGER_DECLARED")
        self.assertEqual(latest["status_counts"], {
            "CONTINUED": 1, "INCREASED": 1, "NEW": 1, "NO_LONGER_DECLARED": 1})
        evidence = latest["changes"][0]["current_records"] or latest["changes"][0]["previous_records"]
        self.assertIn("primary_evidence", evidence[0])
        self.assertIn("do not establish illegality", result["disclaimer"])

    def test_decrease_and_mixed_change_are_not_interpreted(self):
        rows = [
            declaration("a", 2024, "減少", amount="100", quantity="10"),
            declaration("b", 2025, "減少", amount="80", quantity="8"),
            declaration("c", 2024, "混合", amount="100", quantity="10"),
            declaration("d", 2025, "混合", amount="80", quantity="12"),
        ]
        changes = {item["asset_name"]: item for item in
                   build_asset_timeline(rows, max_years=2)["years"][1]["changes"]}
        self.assertEqual(changes["減少"]["status"], "DECREASED")
        self.assertEqual(changes["混合"]["status"], "CHANGED")

    def test_missing_metric_is_changed_not_a_numeric_decrease(self):
        rows = [declaration("a", 2024, "資料缺口", amount="100"),
                declaration("b", 2025, "資料缺口", amount=None)]
        change = build_asset_timeline(rows, max_years=2)["years"][1]["changes"][0]
        self.assertEqual(change["status"], "CHANGED")

    def test_identity_is_exact_normalized_not_fuzzy(self):
        rows = [declaration("a", 2024, "ＡＢＣ股票", amount="100"),
                declaration("b", 2025, "ABC股票", amount="100"),
                declaration("c", 2025, "ABC 股票", amount="100")]
        changes = build_asset_timeline(rows, max_years=2)["years"][1]["changes"]
        statuses = sorted((item["asset_name"], item["status"]) for item in changes)
        self.assertIn(("ABC股票", "CONTINUED"), statuses)
        self.assertIn(("ABC 股票", "NEW"), statuses)

    def test_totals_never_mix_currency_or_quantity_units(self):
        rows = [declaration("a", 2025, "甲", amount="100", quantity="2"),
                {**declaration("b", 2025, "乙", amount="10", quantity=None),
                 "currency": "USD"},
                {**declaration("c", 2025, "丙", amount=None, quantity="3"),
                 "quantity_unit": "單位"}]
        summary = build_asset_timeline(rows, max_years=2)["years"][0]["asset_types"][0]
        self.assertEqual(summary["amounts"], {"TWD": "100", "USD": "10"})
        self.assertEqual(summary["quantities"], {"單位": "3", "股": "2"})

    def test_truncated_oldest_year_is_explicitly_partial(self):
        result = build_asset_timeline(
            [declaration("a", 2024, "甲"), declaration("b", 2025, "乙")],
            max_years=2,
            truncated=True,
        )
        self.assertEqual(result["partial_years"], [2024])
        self.assertTrue(result["years"][0]["partial"])
        self.assertFalse(result["years"][1]["partial"])

        complete_recent = build_asset_timeline(
            [declaration("a", 2023, "甲"), declaration("b", 2024, "乙"),
             declaration("c", 2025, "丙")],
            max_years=2,
            truncated=True,
        )
        self.assertEqual(complete_recent["partial_years"], [])

    def test_repository_is_one_bounded_batched_read(self):
        calls = []

        def get(table, params):
            calls.append((table, params))
            if table == "entities":
                return [{"id": POLITICIAN, "entity_type": "Politician"}]
            return [declaration("a", 2025, "股票", amount="100")]

        result = EntityRepository(transport=get).asset_timeline(POLITICIAN, max_years=5)
        self.assertEqual(result["year_count"], 1)
        self.assertEqual(calls[-1][0], "asset_declarations")
        self.assertEqual(calls[-1][1]["limit"], MAX_TIMELINE_ROWS + 1)
        self.assertEqual(calls[-1][1]["order"], "declaration_year.desc,id.asc")
        self.assertIn("primary_evidence:evidence_records", calls[-1][1]["select"])
        self.assertNotIn("relationship:", calls[-1][1]["select"])

    def test_repository_keeps_old_schema_compatible(self):
        def get(table, _params):
            if table == "entities":
                return [{"id": POLITICIAN, "entity_type": "Politician"}]
            raise EntityFeatureUnavailable("old schema")

        result = EntityRepository(transport=get).asset_timeline(POLITICIAN)
        self.assertFalse(result["schema_available"])
        self.assertEqual(result["years"], [])

    def test_api_is_bounded_and_keeps_v1_envelope(self):
        repo = Mock()
        repo.asset_timeline.return_value = {"years": [], "truncated": False}
        path = f"/api/v1/politicians/{POLITICIAN}/asset-timeline"
        code, body, _ = dispatch_entity_api(path, {"years": ["8"]}, repo)
        self.assertEqual((code, body["api_version"]), (200, "1"))
        repo.asset_timeline.assert_called_once_with(POLITICIAN, max_years=8)
        for value in ("1", "21", "bad"):
            self.assertEqual(dispatch_entity_api(path, {"years": [value]}, repo)[0], 400)

    def test_ui_exposes_timeline_changes_and_sources(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        for token in ("/asset-timeline", "assetTimelineCards", "年度財產時間序列",
                      "NO_LONGER_DECLARED", "客觀差異", "原始來源 / Original source"):
            self.assertIn(token, html)


if __name__ == "__main__":
    unittest.main()
