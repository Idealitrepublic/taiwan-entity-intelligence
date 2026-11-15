import unittest
from pathlib import Path
from unittest.mock import Mock

from src.election_2026 import EXPECTED_BY_OFFICE, EXPECTED_COUNT, parse_page
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

    def test_registration_endpoint_and_search_option_are_withdrawn(self):
        repo = Mock()
        self.assertEqual(dispatch_entity_api("/api/v1/elections/2026/registrations",
                                             {"q": ["臺北市"]}, repo)[0], 404)
        self.assertEqual(repo.mock_calls, [])
        page = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        self.assertNotIn('value="Election2026"', page)
        self.assertNotIn("/api/v1/elections/2026/registrations", page)
