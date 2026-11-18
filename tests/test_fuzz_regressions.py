"""Minimal failures discovered by the seeded offline campaign."""

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from pypdf import PdfReader
from src.reports import render_report_html
from src.report_pdf import render_report_pdf
from src.sources.procurement import lookup_awards

CORPUS = json.loads((Path(__file__).parent / "fuzz/repros.json").read_text())


class FuzzRegressions(unittest.TestCase):
    def test_malformed_notice_does_not_erase_a_different_valid_award(self):
        case = next(f["input"] for f in CORPUS if f["target"] == "procurement")
        before = deepcopy(case)
        with patch("src.sources.procurement._json_get", return_value=case):
            result = lookup_awards("22659295")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["records"][0]["job_number"], "0630800011")
        self.assertEqual(result["invalid_record_count"], 1)
        self.assertTrue(result["limited"])
        self.assertEqual(case, before)

    def test_bad_later_correction_cannot_resurrect_an_old_winner(self):
        case = deepcopy(
            next(f["input"] for f in CORPUS if f["target"] == "procurement")
        )
        good = next(r for r in case["records"] if r["job_number"] == "0630800011")
        bad = next(r for r in case["records"] if r is not good)
        bad.update(unit_id=good["unit_id"], job_number=good["job_number"])
        with patch("src.sources.procurement._json_get", return_value=case):
            result = lookup_awards("22659295")
        self.assertEqual(result["records"], [])
        self.assertEqual(result["unresolved_count"], 1)
        self.assertEqual(result["invalid_record_count"], 1)
        self.assertTrue(result["limited"])

    def test_malformed_total_does_not_erase_valid_notices(self):
        case = deepcopy(
            next(f["input"] for f in CORPUS if f["target"] == "procurement")
        )
        case["records"] = [
            r for r in case["records"] if r["job_number"] == "0630800011"
        ]
        for total in ([], {}, "NaN", "-100"):
            case["total_records"] = total
            with (
                self.subTest(total=total),
                patch("src.sources.procurement._json_get", return_value=case),
            ):
                result = lookup_awards("22659295")
                self.assertEqual(result["matched"], 1)
                self.assertGreaterEqual(result["available_notices"], 1)

    def test_malformed_urls_are_text_not_export_failures_or_active_links(self):
        case = deepcopy(next(f["input"] for f in CORPUS if f["target"] == "pdf"))
        for url in (
            "https://[",
            "https://user:password@example.invalid/",
            "javascript:alert(1)",
        ):
            case["sources"][0]["source_url"] = url
            with self.subTest(url=url):
                html = render_report_html(case)
                self.assertIn("FUZZCASE00002", html)
                self.assertNotIn('href="' + url, html)
                reader = PdfReader(BytesIO(render_report_pdf(case)))
                self.assertIn(
                    "FUZZCASE00002", "".join(p.extract_text() for p in reader.pages)
                )
                for page in reader.pages:
                    self.assertFalse(page.get("/Annots"))
