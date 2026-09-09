import unittest
from unittest.mock import Mock
from pathlib import Path

from src.entities.api import dispatch_entity_api
from src.entities.repository import EntityRepository, EntityStoreUnavailable
from src.entities.search import parse_search_request


class EntitySearchTests(unittest.TestCase):
    def test_request_validation(self):
        request = parse_search_request({"q": [" 台積電 "], "entity_type": ["Company"], "limit": ["8"]})
        self.assertEqual((request.term, request.entity_type, request.limit), ("台積電", "Company", 8))
        for query in ({}, {"q": ["王"]}, {"q": ["a\n"]}, {"q": ["台積電"], "limit": ["21"]},
                      {"q": ["台積電"], "entity_type": ["Unknown"]}):
            with self.assertRaises(ValueError):
                parse_search_request(query)

    def test_api_returns_classified_results_without_merging_names(self):
        repo = Mock()
        repo.search.return_value = {
            "query": "王小明",
            "items": [
                {"entity_id": "1", "entity_type": "Person", "display_name": "王小明"},
                {"entity_id": "2", "entity_type": "Person", "display_name": "王小明"},
            ],
            "groups": {"Person": 2},
            "result_count": 2,
            "limit": 20,
        }
        code, body, _ = dispatch_entity_api("/api/v1/search", {"q": ["王小明"]}, repo)
        self.assertEqual(code, 200)
        self.assertEqual([item["entity_id"] for item in body["data"]["items"]], ["1", "2"])
        repo.search.assert_called_once_with("王小明", entity_type=None, limit=20)

    def test_api_rejects_bad_input_and_masks_store_errors(self):
        self.assertEqual(dispatch_entity_api("/api/v1/search", {"q": ["x"]})[0], 400)
        repo = Mock()
        repo.search.side_effect = EntityStoreUnavailable("private detail")
        code, body, _ = dispatch_entity_api("/api/v1/search", {"q": ["測試"]}, repo)
        self.assertEqual(code, 503)
        self.assertNotIn("private", str(body))

    def test_repository_uses_bounded_safe_rpc(self):
        calls = []

        def get(table, params):
            calls.append((table, params))
            return [{"entity_id": "1", "entity_type": "Company"},
                    {"entity_id": "2", "entity_type": "Person"}]

        result = EntityRepository(transport=get).search("測試", entity_type="Company", limit=7)
        self.assertEqual(calls, [("rpc/search_entities", {
            "search_query": "測試", "result_limit": 7, "entity_type_filter": "Company"})])
        self.assertEqual(result["groups"], {"Company": 1, "Person": 1})

    def test_homepage_exposes_global_search_and_legacy_company_path(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        self.assertIn('id="entityTypeFilter"', html)
        self.assertIn("/api/v1/search?", html)
        self.assertIn("async function searchCompany", html)
        self.assertIn("同名人物會分開顯示", html)
        self.assertNotIn('maxlength="8" inputmode="numeric"', html)


if __name__ == "__main__":
    unittest.main()
