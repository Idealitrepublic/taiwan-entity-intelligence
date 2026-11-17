import unittest
from unittest.mock import patch

from app import dispatch


class InteractiveGraphAndSourceTests(unittest.TestCase):
    def test_public_company_response_omits_case_datasets(self):
        with patch("src.cloud_company._moea_rows", side_effect=[
            [{"Company_Name": "測試公司"}], [{"Person_Name": "測試董事"}],
        ]), patch("src.cloud_company.SUPABASE_KEY", ""):
            status, payload, _ = dispatch("/api/company/12345678", {})
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["people"]), 1)
        self.assertNotIn("judicial_records", payload)
        self.assertNotIn("labor_penalties", payload)
        self.assertNotIn("司法院", payload["evidence_status"])
        self.assertNotIn("裁罰", payload["evidence_status"])

    def test_procurement_route_validates_and_returns_lookup(self):
        expected = {"status": "ok", "matched": 2, "records": []}
        with patch("app.lookup_awards", return_value=expected):
            status, payload, _ = dispatch("/api/procurement/96979933", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload, expected)

    def test_ui_contains_graph_interactions_and_source_fallback(self):
        status, html, content_type = dispatch("/", {})
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/html; charset=utf-8")
        self.assertIn("@keyframes node-pop", html)
        self.assertIn("addEventListener('pointerdown'", html)
        self.assertIn("Math.min(3", html)
        self.assertIn("nodeInfoTitle", html)

    def test_ui_uses_progressive_category_graph(self):
        _, html, _ = dispatch("/", {})
        self.assertIn("hubDefinitions", html)
        self.assertIn("groupedProcurementCityNodes", html)
        self.assertIn("groupedProcurementYearNodes", html)
        self.assertIn("expandedProcurementCounty", html)
        self.assertIn("dataset.hub", html)
        self.assertIn("全部收合 / Collapse", html)
        self.assertIn("由左向右分層", html)
        self.assertIn("x:620", html)
        self.assertIn("x:860", html)
        self.assertNotIn("Math.PI*2*slot/count", html)

    def test_right_panel_has_requested_filters_and_grouping(self):
        _, html, _ = dispatch("/", {})
        for key in (
            "procurementType",
            "procurementCounty", "procurementAgency", "procurementYear",
        ):
            with self.subTest(key=key):
                self.assertIn(f"filterSelect('{key}'", html)
        for label in ("招標單位 / Agency",):
            with self.subTest(label=label):
                self.assertIn(label, html)
        self.assertIn("record-group", html)

    def test_right_panel_has_requested_sections_without_evidence_tab(self):
        _, html, _ = dispatch("/", {})
        for label in ("企業總覽", "獲得標案"):
            with self.subTest(label=label):
                self.assertIn(label, html)
        for kind in ("judicial", "penalty"):
            self.assertNotIn(f'data-tab="{kind}"', html)
            self.assertNotIn(f'id="{kind}Count"', html)
        for kind in ("Judgment", "Penalty", "RELATED_TO_JUDGMENT", "RELATED_TO_PENALTY"):
            self.assertNotIn(f'<option value="{kind}">', html)
        self.assertNotIn('data-tab="evidence"', html)
        self.assertNotIn('id="evidencePane"', html)

    def test_left_panel_identifies_public_data_providers(self):
        _, html, _ = dispatch("/", {})
        for provider in ("經濟部商業發展署", "勞動部及各地方主管機關", "司法院", "行政院公共工程委員會", "刑事警察局 165"):
            with self.subTest(provider=provider):
                self.assertIn(provider, html)
        self.assertIn("T.E.I. 為民間整合工具，不代表任何政府機關", html)


if __name__ == "__main__":
    unittest.main()
