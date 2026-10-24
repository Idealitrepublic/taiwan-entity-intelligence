import tempfile
import unittest
from pathlib import Path

from src.civil_organizations import roster_bundles
from scripts.ingest_civil_organizations_dev import ensure_same_snapshot


HEADER = "SeqNo,Name,Date_of_Establishment,address,Chairman,session\n"
SUBHEADER = "序號,協會名稱,成立日期,地址,理事長,屆次\n"
NOW = "2026-10-24T00:00:00+00:00"


class CivilOrganizationIngestionTests(unittest.TestCase):
    def roster(self, body):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "roster.csv"
        path.write_text(HEADER + SUBHEADER + body, encoding="utf-8-sig")
        return path

    def test_historical_rows_are_source_scoped_and_have_evidence(self):
        path = self.roster("1,同名協會,131010,私有地址,甲某,1\n"
                           "2,同名協會,191010,另一地址,乙某,2\n")
        bundles = list(roster_bundles(path, retrieved_at=NOW, batch_size=1,
                                      publication_status="published"))
        self.assertEqual(len(bundles), 2)
        left, right = bundles
        self.assertNotEqual(left["entities"][0]["id"], right["entities"][0]["id"])
        for bundle in bundles:
            entity, evidence = bundle["entities"][0], bundle["evidence"][0]
            self.assertEqual(entity["entity_type"], "CivilOrganization")
            self.assertEqual(entity["identity_status"], "SOURCE_SCOPED")
            self.assertEqual(bundle["entity_evidence"][0]["entity_id"], entity["id"])
            self.assertEqual(bundle["entity_evidence"][0]["evidence_id"], evidence["id"])
            self.assertIn("historical_roster", evidence["source_locator"]["scope"])
            self.assertNotIn("私有地址", str(bundle))
            self.assertNotIn("乙某", str(bundle))
        again = list(roster_bundles(path, retrieved_at=NOW, batch_size=2))
        self.assertEqual(again[0]["entities"][0]["id"], left["entities"][0]["id"])

    def test_duplicate_sequence_is_rejected_not_name_merged(self):
        path = self.roster("1,協會甲,131010,,,\n1,協會乙,131010,,,\n")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            list(roster_bundles(path, retrieved_at=NOW))

    def test_bad_columns_and_bad_rows_fail_closed(self):
        path = self.roster("not-an-id,協會甲,131010,,,\n")
        with self.assertRaisesRegex(ValueError, "Invalid MOI roster row"):
            list(roster_bundles(path, retrieved_at=NOW))
        path.write_text("Name\n協會甲\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unexpected MOI"):
            list(roster_bundles(path, retrieved_at=NOW))

    def test_search_and_profile_disclose_historical_scope(self):
        html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text()
        self.assertIn('<option value="CivilOrganization">民間團體', html)
        self.assertIn("CivilOrganization:'民間團體 / Civil organization'", html)
        self.assertIn('Historical MOI roster; current registration is unverified.', html)
        self.assertIn('current status and cross-source identity are unverified.', html)

    def test_changed_snapshot_requires_explicit_review(self):
        ensure_same_snapshot("hash-a", [])
        ensure_same_snapshot("hash-a", ["hash-a"])
        with self.assertRaisesRegex(ValueError, "different MOI snapshot"):
            ensure_same_snapshot("hash-b", ["hash-a"])


if __name__ == "__main__":
    unittest.main()
