import unittest

from src.server import _decorate_evidence, _judicial_link


class ServerHelperTests(unittest.TestCase):
    def test_judicial_link_contains_search_term(self):
        url = _judicial_link("御首服務事業有限公司")
        self.assertIn("judgment.judicial.gov.tw", url)
        self.assertIn("kw=", url)

    def test_evidence_is_attached_to_company_when_name_matches(self):
        rows = [{
            "source": {"name": "勞動部／違反勞動法令事業單位"},
            "raw": {"事業單位名稱或負責人": "御首服務事業有限公司"},
        }]
        result = _decorate_evidence(rows, "御首服務事業有限公司", [], "82876417")
        self.assertEqual(result[0]["entity_id"], "company:82876417")
        self.assertEqual(result[0]["entity_type"], "company")


if __name__ == "__main__":
    unittest.main()
