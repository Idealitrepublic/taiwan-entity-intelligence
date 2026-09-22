import unittest
from pathlib import Path
from unittest.mock import Mock

from src.asset_declarations import (
    ASSET_TYPES,
    build_asset_declaration_batches,
    build_asset_declaration_bundle,
)
from src.entities.api import dispatch_entity_api
from src.entities.repository import EntityFeatureUnavailable, EntityRepository

POLITICIAN = "11111111-1111-4111-8111-111111111111"
COMPANY = "22222222-2222-4222-8222-222222222222"
CURSOR = "33333333-3333-4333-8333-333333333333"


def entities():
    return ({"id": POLITICIAN, "entity_type": "Politician", "display_name": "林立委"},
            {"id": COMPANY, "entity_type": "Company", "display_name": "測試公司"})


def asset_row(**updates):
    row = {
        "source_record_id": "302-lin-stock-001",
        "politician_source_id": "legislator-001",
        "declaration_year": 2026,
        "asset_type": "股票",
        "asset_name": "測試公司普通股",
        "amount": "1,200,000",
        "quantity": "30,000",
        "quantity_unit": "股",
        "company_name": "測試公司",
        "company_uniform_number": "１２３４５６７８",
        "observed_at": "2026-03-31T00:00:00+08:00",
        "publication": "廉政專刊第302期",
        "source_url": "https://sunshine.cy.gov.tw/News_Content.aspx?n=16&s=37045",
    }
    row.update(updates)
    return row


class AssetDeclarationTests(unittest.TestCase):
    def test_adapter_supports_every_required_asset_type(self):
        politician, _ = entities()
        labels = ("不動產", "現金", "存款", "股票", "債券", "基金", "有價證券", "債權",
                  "債務", "事業投資", "保險", "車輛", "其他資產")
        rows = [asset_row(source_record_id=f"record-{index}", asset_type=label,
                          asset_name=f"資產-{index}", company_name=None,
                          company_uniform_number=None, amount=None, quantity=None,
                          quantity_unit=None) for index, label in enumerate(labels)]
        bundle, report = build_asset_declaration_bundle(
            rows, politicians_by_source_id={"legislator-001": politician},
            companies_by_uniform={}, retrieved_at="2026-09-16T12:00:00+08:00")
        self.assertEqual({item["asset_type"] for item in bundle["asset_declarations"]},
                         set(ASSET_TYPES))
        self.assertEqual(report["counts"]["asset_declarations"], 13)
        self.assertTrue(all(item["publication_status"] == "draft"
                            for item in bundle["asset_declarations"]))

    def test_exact_uniform_number_creates_evidence_backed_ownership(self):
        politician, company = entities()
        bundle, report = build_asset_declaration_bundle(
            [asset_row()], politicians_by_source_id={"legislator-001": politician},
            companies_by_uniform={"12345678": company},
            retrieved_at="2026-09-16T12:00:00+08:00")
        item, relationship, evidence = (bundle["asset_declarations"][0],
                                        bundle["relationships"][0], bundle["evidence"][0])
        self.assertEqual((item["politician_id"], item["declaration_year"]),
                         (POLITICIAN, 2026))
        self.assertEqual((item["amount"], item["quantity"]), ("1200000", "30000"))
        self.assertEqual((item["company_name"], item["company_entity_id"]),
                         ("測試公司", COMPANY))
        self.assertEqual(relationship["relationship_type"], "ASSET_OWNERSHIP")
        self.assertEqual((relationship["source_entity_id"], relationship["target_entity_id"]),
                         (POLITICIAN, COMPANY))
        self.assertEqual(relationship["primary_evidence_id"], evidence["id"])
        self.assertEqual(evidence["source_record_id"], "302-lin-stock-001")
        self.assertEqual(evidence["source_locator"]["company_match_method"],
                         "exact_uniform_number")
        self.assertEqual(report["unresolved_companies"], [])

    def test_business_investment_uses_business_edge(self):
        politician, company = entities()
        bundle, _ = build_asset_declaration_bundle(
            [asset_row(asset_type="事業投資")],
            politicians_by_source_id={"legislator-001": politician},
            companies_by_uniform={"12345678": company},
            retrieved_at="2026-09-16T12:00:00+08:00")
        self.assertEqual(bundle["relationships"][0]["relationship_type"],
                         "BUSINESS_INVESTMENT")

    def test_company_name_never_forces_resolution_or_relationship(self):
        politician, company = entities()
        bundle, report = build_asset_declaration_bundle(
            [asset_row(company_uniform_number=None)],
            politicians_by_source_id={"legislator-001": politician},
            companies_by_uniform={"12345678": company},
            retrieved_at="2026-09-16T12:00:00+08:00")
        item = bundle["asset_declarations"][0]
        self.assertEqual(item["company_name"], "測試公司")
        self.assertIsNone(item["company_entity_id"])
        self.assertIsNone(item["relationship_id"])
        self.assertEqual(bundle["relationships"], [])
        self.assertEqual(report["unresolved_companies"][0]["reason"], "no_exact_identifier")

    def test_non_ownership_company_asset_does_not_create_edge(self):
        politician, company = entities()
        bundle, _ = build_asset_declaration_bundle(
            [asset_row(asset_type="債務")],
            politicians_by_source_id={"legislator-001": politician},
            companies_by_uniform={"12345678": company},
            retrieved_at="2026-09-16T12:00:00+08:00")
        self.assertEqual(bundle["asset_declarations"][0]["company_entity_id"], COMPANY)
        self.assertEqual(bundle["relationships"], [])

    def test_official_headers_roc_year_and_version_provenance_are_normalized(self):
        politician, company = entities()
        row = {"資料編號": "302-110777-stock-1-v2", "申報編號": "302-110777",
               "項次": "1", "lgno": "110777", "申報人姓名": "林立委",
               "申報年度": "115年", "更正次數": "2", "財產類別": "股票",
               "財產名稱": "測試公司普通股", "金額": "1,200,000元",
               "數量": "30,000股", "單位": "股", "公司名稱": "測試公司",
               "統一編號": "１２３４５６７８", "申報日期": "2026-03-31T00:00:00+08:00",
               "刊期": "廉政專刊第302期"}
        bundle, report = build_asset_declaration_bundle(
            [row], politicians_by_official_id={
                ("tw:legislative_yuan:legislator_number", "110777"): politician},
            companies_by_uniform={"12345678": company},
            retrieved_at="2026-09-16T12:00:00+08:00")
        item, locator = (bundle["asset_declarations"][0],
                         bundle["evidence"][0]["source_locator"])
        self.assertEqual((item["declaration_year"], item["declaration_version"]),
                         (2026, 2))
        self.assertRegex(item["declaration_key"], r"^[0-9a-f]{64}$")
        self.assertEqual(locator["politician_match_method"],
                         "exact_official_identifier")
        self.assertEqual(report["quality"]["company_exact_match_rate"], 1.0)

    def test_name_only_politician_never_resolves_and_invalid_uniform_is_rejected(self):
        politician, company = entities()
        rows = [asset_row(politician_source_id="", politician_name="林立委"),
                asset_row(source_record_id="bad-uniform", company_uniform_number="測試公司")]
        bundle, report = build_asset_declaration_bundle(
            rows, politicians_by_official_id={"legislator-001": politician},
            companies_by_uniform={"12345678": company},
            retrieved_at="2026-09-16T12:00:00+08:00")
        self.assertEqual(bundle["asset_declarations"], [])
        self.assertEqual({item["reason"] for item in report["skipped"]},
                         {"missing_politician_identifier", "invalid_company_uniform_number"})

    def test_duplicate_versions_are_rejected_and_batches_are_bounded(self):
        politician, _ = entities()
        duplicate = [asset_row(line_number="1", company_name=None, company_uniform_number=None),
                     asset_row(source_record_id="another", line_number="1", company_name=None,
                               company_uniform_number=None)]
        _, report = build_asset_declaration_bundle(
            duplicate, politicians_by_source_id={"legislator-001": politician},
            companies_by_uniform={}, retrieved_at="2026-09-16T12:00:00+08:00")
        self.assertIn("duplicate_declaration_version",
                      {item["reason"] for item in report["skipped"]})
        rows = [asset_row(source_record_id=f"record-{index}", filing_id=f"filing-{index}",
                          company_name=None, company_uniform_number=None)
                for index in range(205)]
        batches, batch_report = build_asset_declaration_batches(
            rows, politicians_by_source_id={"legislator-001": politician},
            companies_by_uniform={}, retrieved_at="2026-09-16T12:00:00+08:00")
        self.assertEqual([len(batch["asset_declarations"]) for batch in batches], [200, 5])
        self.assertEqual(batch_report["batch_count"], 2)

    def test_quality_report_covers_all_required_asset_types(self):
        politician, _ = entities()
        rows = [asset_row(source_record_id=f"coverage-{index}", filing_id=f"filing-{index}",
                          asset_type=asset_type, asset_name=f"asset-{index}",
                          company_name=None, company_uniform_number=None,
                          amount=None, quantity=None, quantity_unit=None)
                for index, asset_type in enumerate(ASSET_TYPES)]
        _, report = build_asset_declaration_bundle(
            rows, politicians_by_source_id={"legislator-001": politician},
            companies_by_uniform={}, retrieved_at="2026-09-16T12:00:00+08:00")
        self.assertEqual(report["quality"]["row_acceptance_rate"], 1.0)
        self.assertEqual(report["quality"]["asset_type_coverage"], 1.0)
        self.assertEqual(report["quality"]["high_severity_issue_count"], 0)

    def test_repository_is_bounded_filtered_and_batched(self):
        politician, company = entities()
        calls = []

        def get(table, params):
            calls.append((table, params))
            if table == "entities":
                return [politician]
            return [{"id": CURSOR, "politician_id": POLITICIAN, "asset_type": "STOCK",
                     "company": company, "relationship": {"id": CURSOR},
                     "primary_evidence": {"id": CURSOR}},
                    {"id": "44444444-4444-4444-8444-444444444444"}]

        page = EntityRepository(transport=get).asset_declarations(
            POLITICIAN, limit=1, after=CURSOR, declaration_year=2026, asset_type="STOCK")
        self.assertTrue(page["has_more"])
        self.assertEqual(page["next_cursor"], CURSOR)
        self.assertEqual(calls[-1][0], "asset_declarations")
        self.assertEqual(calls[-1][1]["limit"], 2)
        self.assertEqual(calls[-1][1]["id"], f"gt.{CURSOR}")
        self.assertEqual(calls[-1][1]["declaration_year"], "eq.2026")
        self.assertEqual(calls[-1][1]["asset_type"], "eq.STOCK")
        self.assertIn("primary_evidence:evidence_records", calls[-1][1]["select"])

    def test_missing_table_is_backward_compatible(self):
        politician, _ = entities()

        def get(table, _params):
            if table == "entities":
                return [politician]
            raise EntityFeatureUnavailable("old schema")

        page = EntityRepository(transport=get).asset_declarations(POLITICIAN)
        self.assertFalse(page["schema_available"])
        self.assertEqual(page["items"], [])

    def test_api_validates_filters_and_keeps_v1_envelope(self):
        repo = Mock()
        repo.asset_declarations.return_value = {"items": [], "has_more": False}
        path = f"/api/v1/politicians/{POLITICIAN}/asset-declarations"
        query = {"limit": ["25"], "declaration_year": ["2026"],
                 "asset_type": ["STOCK"]}
        code, body, _ = dispatch_entity_api(path, query, repo)
        self.assertEqual((code, body["api_version"]), (200, "1"))
        repo.asset_declarations.assert_called_once_with(
            POLITICIAN, limit=25, after=None, declaration_year=2026, asset_type="STOCK")
        for bad in ({"limit": ["26"]}, {"after": ["bad"]},
                    {"declaration_year": ["1900"]}, {"asset_type": ["NAME_MATCH"]}):
            self.assertEqual(dispatch_entity_api(path, bad, repo)[0], 400)

    def test_politician_page_renders_asset_fields_and_source(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        for token in ("/asset-declarations", "assetDeclarationCards",
                      "財產申報 / Asset declarations", "declaration_year",
                      "company_entity_id", "原始來源 / Original source"):
            self.assertIn(token, html)


if __name__ == "__main__":
    unittest.main()
