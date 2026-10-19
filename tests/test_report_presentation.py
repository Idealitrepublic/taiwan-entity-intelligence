"""Readable report output must retain facts and provenance without duplicating JSON."""
import unittest

from src.report_presentation import present_report
from src.reports import render_report_html


class ReportPresentationTests(unittest.TestCase):
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
        self.assertIn(("取得時間 / Retrieved at", "2026-10-19T00:00:00Z"), relation["facts"])
        html = render_report_html(report)
        self.assertIn(f'href="{source_url}"', html)
        self.assertIn("中華電信", html)
        self.assertNotIn("relationship_type", html)

    def test_unavailable_saved_references_are_flagged_without_fake_records(self):
        report = {"report_type": "WORKSPACE", "coverage": {"unavailable_saved_references":
                  [{"entity_id": "missing"}]}, "workspace_items": [{"title": "研究筆記",
                  "item_type": "NOTE", "note_text": "待查證"}]}
        view = present_report(report)
        self.assertEqual(len(view["warnings"]), 1)
        self.assertEqual(len(view["sections"]), 1)
        self.assertEqual(view["sections"][0]["items"][0]["title"], "研究筆記")
        self.assertIn("Entity Profile / 實體概況", view["empty"])


if __name__ == "__main__":
    unittest.main()
