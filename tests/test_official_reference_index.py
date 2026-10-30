import json
import sqlite3
import unittest
import tempfile
import hashlib
import subprocess
import sys
from pathlib import Path

from scripts.build_official_reference_index import AGENCY_URL, BILL_URL, agency_rows, bill_rows, build, build_supplementary_sources


class OfficialReferenceIndexTests(unittest.TestCase):
    def test_agency_identifier_is_unique_and_contact_data_is_not_projected(self):
        raw = "OrgName,OID,OrgCode,TEL,Address\n測試機關,2.16.886.1,123,not-retained,not-retained\n".encode()
        rows = agency_rows(raw)
        self.assertEqual(rows, [(2, "2.16.886.1", "測試機關", "123")])
        with self.assertRaises(ValueError):
            agency_rows(raw + raw.splitlines()[1] + b"\n")

    def test_bill_stages_are_preserved_without_guessing_the_latest_status(self):
        raw = json.dumps({"dataList": [{"term": 11, "billNo": "official-1", "billName": "同一議案", "billStatus": status}
                                       for status in ["一讀", "交付審查"]]}).encode()
        rows = bill_rows(raw)
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0][-1], rows[1][-1])
        db = sqlite3.connect(":memory:")
        sources = [("bills", raw, BILL_URL, "2026-10-29T00:00:00+08:00")]
        first, repeated = build(db, sources), build(db, sources)
        self.assertEqual(first, repeated)
        self.assertEqual(first["distinct_official_bill_ids"], 1)
        self.assertEqual(first["canonical_entities_published"], 0)

    def test_bad_term_empty_data_and_unreviewed_source_fail(self):
        for payload in ({"dataList": []}, {"dataList": [{"term": 10, "billNo": "1", "billName": "不在範圍"}]}):
            with self.assertRaises(ValueError):
                bill_rows(json.dumps(payload).encode())
        with self.assertRaises(ValueError):
            build(sqlite3.connect(":memory:"), [("agencies", b"x", AGENCY_URL + "?wrong", "2026-10-29T00:00:00+08:00")])

    def test_officer_source_rows_keep_same_names_separate_and_are_idempotent(self):
        from scripts.sync_moea_officers_dev import RESOURCE
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            raw=('統一編號,公司名稱,職稱,姓名,所代表法人,持有股份數\n'
                 '96979933,甲公司,董事,同名人物,,0\n'
                 '22099131,乙公司,董事,同名人物,,123\n'
                 '22099131,乙公司,董事,,,0\n').encode()
            (folder/'official.csv').write_bytes(raw)
            metadata=[{'complete_download':True,'source_url':RESOURCE,'file':'official.csv',
                       'sha256':hashlib.sha256(raw).hexdigest(),'source_rows':3,
                       'retrieved_at':'2026-10-30T00:00:00+08:00'}]
            (folder/'full_acquisition.json').write_text(json.dumps(metadata))
            db=sqlite3.connect(':memory:')
            first=build_supplementary_sources(db,folder)
            self.assertEqual(first,build_supplementary_sources(db,folder))
            self.assertEqual(db.execute('select count(*) from officer_observations').fetchone()[0],2)
            self.assertEqual(first['sources'][0]['indexed_observations'],2)
            self.assertEqual(first['sources'][0]['excluded_from_index_retained_in_original'],1)
            self.assertEqual(first['canonical_entities_published'],0)
            self.assertEqual(db.execute('select count(distinct company_id) from officer_observations').fetchone()[0],2)
            cli=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1] /
                                'scripts/build_official_reference_index.py'),str(folder),
                                '--supplementary-only','--output',str(folder/'index.sqlite3')],
                               capture_output=True,text=True,timeout=20)
            self.assertEqual(cli.returncode,0,cli.stderr)
            self.assertEqual(json.loads(cli.stdout)['cloud_writes'],0)
            metadata[0]['sha256']='0'*64
            (folder/'full_acquisition.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                build_supplementary_sources(db,folder)


if __name__ == "__main__":
    unittest.main()
