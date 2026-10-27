"""Readable report output must retain facts and provenance without duplicating JSON."""
import unittest
from copy import deepcopy

from src.report_presentation import LABELS, format_date, format_money, present_report, source_locator_text
from src.reports import render_report_html


class ReportPresentationTests(unittest.TestCase):
    def test_supported_entity_relationship_asset_and_confidence_types_have_bilingual_labels(self):
        from src.asset_declarations import ASSET_TYPES
        from src.entities.models import CONFIDENCES, ENTITY_TYPES
        from src.relationships.models import RELATIONSHIP_TYPES
        for value in (*ASSET_TYPES, *CONFIDENCES, *ENTITY_TYPES, *RELATIONSHIP_TYPES, 'SOURCE_SCOPED'):
            self.assertIn(value, LABELS)
            self.assertIn(' / ', LABELS[value])
            self.assertNotIn('_', LABELS[value])

    def test_relationship_evidence_and_source_remain_visible(self):
        source_url = "https://data.gov.tw/dataset/109896"
        report = {
            "title": "Evidence report", "methodology": "Facts only", "report_type": "ENTITY",
            "generated_at": "2026-10-19T00:00:00Z", "coverage": {},
            "entity_profiles": [{"display_name": "中華電信", "entity_type": "Company",
                                 "public_identifier": "96979933"}],
            "key_relationships": [{"relationship": {"relationship_type": "RELATED_TO_PENALTY",
                                                   "start_date": "2025-01-03", "amount": 10000},
                                   "source_entity": {"display_name": "中華電信"},
                                   "target_entity": {"display_name": "裁罰機關"},
                                   "evidence": {"title": "官方裁罰紀錄", "source_name": "勞動部",
                                                "source_url": source_url,
                                                "retrieved_at": "2026-10-19T00:00:00Z"}}],
            "sources": [{"source_name": "勞動部", "source_url": source_url,
                         "retrieved_at": "2026-10-19T00:00:00Z"}],
            "relationship_graph": {"nodes": [{"display_name": "中華電信"}], "edges": []},
        }
        view = present_report(report)
        relation = next(section for section in view["sections"]
                        if section["key"] == "key_relationships")["items"][0]
        self.assertIn(("原始連結 / Source URL", source_url), relation["facts"])
        self.assertIn(("取得時間 / Retrieved at", "2026-10-19 08:00:00 (UTC+08:00)"), relation["facts"])
        html = render_report_html(report)
        self.assertIn(f'href="{source_url}"', html)
        self.assertIn("中華電信", html)
        self.assertNotIn("relationship_type", html)

    def test_dates_keep_precision_and_currency_is_never_invented(self):
        self.assertEqual(format_date("0850615"), "1996-06-15")
        self.assertEqual(format_date("20261019"), "2026-10-19")
        self.assertEqual(format_date("113/2/3"), "2024-02-03")
        self.assertEqual(format_date("2026/10/19"), "2026-10-19")
        self.assertEqual(format_date("2026-10-19"), "2026-10-19")
        self.assertEqual(format_date("2026-10-18T20:15:30Z"), "2026-10-19 04:15:30 (UTC+08:00)")
        self.assertIn("時區未註明", format_date("2026-10-19T12:00:00"))
        self.assertEqual(format_date("unknown-date"), "unknown-date")
        self.assertEqual(format_money("1234567.89", "TWD"), "NT$ 1,234,567.89")
        self.assertEqual(format_money(0, "USD"), "US$ 0")
        self.assertIn("幣別未註明", format_money(50000))
        self.assertEqual(format_money("約五萬元"), "約五萬元")
        locator = source_locator_text({'source_record_id': 'opaque-hash', 'source_locator':
                  {'source_record_id': 'opaque-hash', 'source_file_id': 'private-ingest-id',
                   'disposition_number': '府勞字第1130001號', 'disposition_date': '113/2/3'}})
        self.assertIn('府勞字第1130001號', locator)
        self.assertIn('2024-02-03', locator)
        self.assertNotIn('opaque-hash', locator)
        self.assertNotIn('private-ingest-id', locator)

    def test_display_deduplicates_identical_rows_but_preserves_provenance_and_json(self):
        relation = {"relationship": {"id": "r1", "relationship_type": "RELATED_TO_PENALTY",
                                    "amount": "10000.50", "currency": "TWD"}}
        source = {"source_url": "https://example.gov.tw/records", "source_record_id": "one",
                  "retrieved_at": "2026-10-19T00:00:00Z"}
        report = {"report_type": "WORKSPACE", "generated_at": "2026-10-19T00:00:00Z",
                  "entity_profiles": [{"display_name": "公司", "entity_type": "Company",
                                       "identity_status": "SOURCE_SCOPED"}],
                  "key_relationships": [relation, relation], "penalties": [relation],
                  "sources": [source, source, {**source, "source_record_id": "two"}]}
        original = deepcopy(report)
        view = present_report(report)
        self.assertEqual(report, original)
        self.assertEqual(view["summary"]["關係 / Relationships"], 1)
        self.assertEqual(view["summary"]["證據來源 / Sources"], 2)
        sections = {section["key"]: section for section in view["sections"]}
        self.assertEqual(len(sections["key_relationships"]["items"]), 1)
        self.assertIn(("識別狀態 / Identity", "僅限來源範圍的身分 / Source-scoped identity"),
                      sections["entity_profiles"]["items"][0]["facts"])
        self.assertIn(("金額 / Amount", "NT$ 10,000.50"),
                      sections["penalties"]["items"][0]["facts"])
        self.assertIn(("詳細資料 / Details", "裁罰 / Penalties"),
                      sections["key_relationships"]["items"][0]["facts"])

    def test_unavailable_saved_references_are_flagged_without_fake_records(self):
        report = {"report_type": "WORKSPACE", "coverage": {"unavailable_saved_references":
                  [{"entity_id": "missing"}]}, "workspace_items": [{"title": "研究筆記",
                  "item_type": "NOTE", "note_text": "待查證"}]}
        view = present_report(report)
        self.assertEqual(len(view["warnings"]), 2)
        self.assertTrue(any("單獨收藏來源" in warning for warning in view["warnings"]))
        self.assertEqual(len(view["sections"]), 1)
        self.assertEqual(view["sections"][0]["items"][0]["title"], "研究筆記")
        self.assertIn("實體概況 / Entity Profile", view["empty"])


if __name__ == "__main__":
    unittest.main()
