import json
import unittest

from scripts.ingest_official_position_observations_dev import build


class OfficialPositionObservationTests(unittest.TestCase):
    def page(self, name="測試部長", url="https://ministry.gov.tw/profile"):
        return (f'<li class="member_img"><a href="{url}"><img src="do-not-copy.jpg">'
                f'<span>測試部</span><span>{name}</span></a></li>').encode()

    def test_office_name_remains_source_scoped_and_never_copies_photo(self):
        bundle = build(self.page(), retrieved_at="2026-10-29T00:00:00+08:00", expected_rows=1)
        self.assertEqual(bundle["entities"][0]["entity_type"], "GovernmentOfficial")
        self.assertEqual(bundle["entities"][0]["identity_status"], "SOURCE_SCOPED")
        self.assertEqual(bundle["identifiers"], [])
        self.assertEqual(bundle["relationships"], [])
        self.assertNotIn("do-not-copy.jpg", json.dumps(bundle))

    def test_same_name_different_snapshot_does_not_merge_person_identity(self):
        first = build(self.page(), retrieved_at="2026-10-29T00:00:00+08:00", expected_rows=1)
        other = build(b"\n" + self.page(), retrieved_at="2026-10-29T00:00:00+08:00", expected_rows=1)
        self.assertNotEqual(first["entities"][0]["id"], other["entities"][0]["id"])

    def test_official_education_ministry_domain_is_accepted(self):
        bundle = build(self.page(url="https://www.edu.tw/official"), retrieved_at="2026-10-29T00:00:00+08:00", expected_rows=1)
        self.assertEqual(len(bundle["entities"]), 1)

    def test_ambiguous_count_role_and_unofficial_url_stop(self):
        for payload, count in [(self.page(), 31), (self.page(name="不知道職稱"), 1),
                               (self.page(url="https://example.org/"), 1), (self.page() * 2, 2)]:
            with self.assertRaises(ValueError):
                build(payload, retrieved_at="2026-10-29T00:00:00+08:00", expected_rows=count)


if __name__ == "__main__":
    unittest.main()
