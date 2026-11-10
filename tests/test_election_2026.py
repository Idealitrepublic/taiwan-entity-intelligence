import unittest
from unittest.mock import Mock

from src.election_2026 import DATASET, EXPECTED_BY_OFFICE, EXPECTED_COUNT, parse_page
from src.entities.api import dispatch_entity_api


def fragment(text, x, y):
    return {"text": text, "tx": x - 5, "displaced_tx": x + 5, "ty": y}


class Election2026Tests(unittest.TestCase):
    def test_wrapped_cells_and_image_only_name_keep_source_rows(self):
        headers = [fragment(text, index * 100, 700) for index, text in
                   enumerate(("選舉區", "登記日期", "姓名", "推薦之政黨", "備註"))]
        entries = [
            fragment("臺東縣蘭嶼鄉", 0, 680), fragment("選舉區", 0, 666),
            fragment("115/09/02", 100, 673), fragment("林明明 Ayo", 200, 680),
            fragment("Nabu", 200, 666), fragment("無", 300, 673),
            fragment("臺東縣蘭嶼鄉", 0, 650), fragment("選舉區", 0, 636),
            fragment("115/09/03", 100, 643), fragment("無", 300, 643),
            fragment("arbitrary unindexed remark", 400, 643),
        ]
        first, second = list(parse_page(headers + entries, 7, 156))
        self.assertEqual((first.district, first.name), ("臺東縣蘭嶼鄉選舉區", "林明明 Ayo Nabu"))
        self.assertEqual((second.name, second.registered_on, second.row), (None, "2026-09-03", 2))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(sum(EXPECTED_BY_OFFICE), EXPECTED_COUNT)

    def test_election_api_paginates_without_merging_same_name(self):
        repo = Mock()
        base = {"name": "林明明", "district": "臺北市", "office": 0,
                "registered_on": "2026-09-02", "recommending_party": None, "page": 1}
        repo.transport.return_value = [{"raw": {"snapshot_date": "2026-09-07",
            "rows": [{**base, "row": 1}, {**base, "row": 2, "district": "新北市"}]}}]
        route = "/api/v1/elections/2026/registrations"
        status, body, _ = dispatch_entity_api(route, {"q": ["林明明"], "limit": ["1"]}, repo)
        self.assertEqual(status, 200)
        self.assertEqual((body["data"]["total"], body["data"]["next_offset"]), (2, 1))
        first = body["data"]["items"][0]
        self.assertEqual((first["status"], first["source_page"], first["source_row"]),
                         ("registered_snapshot", 1, 1))
        _, body, _ = dispatch_entity_api(route, {"q": ["林明明"], "limit": ["1"], "offset": ["1"]}, repo)
        self.assertEqual(body["data"]["items"][0]["source_row"], 2)
        self.assertIsNone(body["data"]["next_offset"])
        self.assertEqual(repo.transport.call_args.args[1]["dataset"], f"eq.{DATASET}")
        self.assertEqual(dispatch_entity_api(route, {"q": ["林"], "limit": ["1000"]}, repo)[0], 400)

    def test_missing_catalog_reports_unavailable(self):
        repo = Mock()
        repo.transport.return_value = []
        self.assertEqual(dispatch_entity_api("/api/v1/elections/2026/registrations",
                                             {"q": ["臺北市"]}, repo)[0], 503)
