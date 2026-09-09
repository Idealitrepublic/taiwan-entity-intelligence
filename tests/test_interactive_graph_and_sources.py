import unittest
from unittest.mock import patch

from app import dispatch
from src.cloud_company import penalty_source_info


class InteractiveGraphAndSourceTests(unittest.TestCase):
    def test_penalty_dataset_page_is_not_claimed_as_direct_record(self):
        info = penalty_source_info({
            "source_url": "https://announcement.mol.gov.tw/",
            "title": "違反勞動法令事業單位",
            "raw": {"違法法規法條": "勞動基準法第24條"},
        })
        self.assertIsNone(info["record_url"])
        self.assertEqual(info["link_status"], "dataset_only")
        self.assertIn("無法直接定位", info["message"])

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
        self.assertIn("政府網站無法直接連到此筆紀錄", html)
        self.assertIn("開啟政府查詢入口（不會定位本筆）", html)

    def test_ui_uses_progressive_category_graph(self):
        _, html, _ = dispatch("/", {})
        self.assertIn("hubDefinitions", html)
        self.assertIn("groupedLawNodes", html)
        self.assertIn("groupedProcurementCityNodes", html)
        self.assertIn("groupedProcurementYearNodes", html)
        self.assertIn("expandedProcurementCounty", html)
        self.assertIn("dataset.hub", html)
        self.assertIn("全部收合 / Collapse", html)
        self.assertIn("同一筆紀錄涉及多條法規時", html)
        self.assertIn("由左向右分層", html)
        self.assertIn("x:620", html)
        self.assertIn("x:860", html)
        self.assertNotIn("Math.PI*2*slot/count", html)

    def test_right_panel_has_requested_filters_and_grouping(self):
        _, html, _ = dispatch("/", {})
        for key in (
            "judicialType", "judicialDate", "procurementType",
            "procurementCounty", "procurementAgency", "procurementYear",
            "penaltyLaw", "penaltyYear",
        ):
            with self.subTest(key=key):
                self.assertIn(f"filterSelect('{key}'", html)
        for label in ("案件種類 / Case type", "招標單位 / Agency", "法條 / Article"):
            with self.subTest(label=label):
                self.assertIn(label, html)
        self.assertIn("record-group", html)
        self.assertIn("相同法條集中顯示", html)

    def test_right_panel_has_requested_sections_without_evidence_tab(self):
        _, html, _ = dispatch("/", {})
        for label in ("企業總覽", "司法院判決", "獲得標案", "違反勞基法"):
            with self.subTest(label=label):
                self.assertIn(label, html)
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
