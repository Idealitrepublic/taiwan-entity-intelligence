import unittest

from scripts.publish_reviewed_asset_lines_dev import parse_numeric_lines, prepare


class ReviewedAssetRefreshTests(unittest.TestCase):
    def setUp(self):
        self.crosswalk = {"source_kind": "asset", "status": "approved", "source_subject_name": "黃珊珊",
                          "official_legislator_number": "00082", "politician_entity_id": "11111111-1111-4111-8111-111111111111"}
        self.rows = [{"asset_type": "STOCK", "asset_name": "來源股票", "company_name": "來源股票",
                      "amount": "10000", "quantity": "1000.50", "quantity_unit": "股", "pdf_page": 42}]

    def test_exact_filing_crosswalk_preserves_locator_and_never_name_links_issuer(self):
        bundle, crosswalks = prepare(self.rows, self.crosswalk, retrieved_at="2026-10-28T00:00:00+00:00")
        item = bundle["asset_declarations"][0]
        proof = bundle["evidence"][0]
        self.assertEqual(bundle["relationships"], [])
        self.assertIsNone(item["company_entity_id"])
        self.assertEqual(item["quantity"], "1000.50")
        self.assertEqual(proof["source_locator"]["printed_page"], 38)
        self.assertEqual(proof["source_locator"]["politician_crosswalk_id"], crosswalks[0]["id"])
        self.assertNotIn("保單號碼", proof["source_locator"])

    def test_same_name_without_approved_official_id_is_rejected(self):
        for updates in ({"official_legislator_number": "99999"}, {"status": "withdrawn"}, {"source_kind": "contribution"}):
            with self.assertRaises(ValueError):
                prepare(self.rows, {**self.crosswalk, **updates}, retrieved_at="2026-10-28T00:00:00+00:00")

    def test_rerun_is_stable_and_repeated_fund_names_are_separate_rows(self):
        rows = self.rows * 2
        first, _ = prepare(rows, self.crosswalk, retrieved_at="2026-10-28T00:00:00+00:00")
        second, _ = prepare(rows, self.crosswalk, retrieved_at="2026-10-28T01:00:00+00:00")
        self.assertEqual([r["id"] for r in first["asset_declarations"]], [r["id"] for r in second["asset_declarations"]])
        self.assertEqual(len({r["declaration_key"] for r in first["asset_declarations"]}), 2)

    def test_missing_source_section_is_not_an_empty_success(self):
        with self.assertRaises((KeyError, IndexError, ValueError)):
            parse_numeric_lines({41: "unexpected PDF", 42: "", 43: "", 44: ""})

    def test_unknown_price_is_null_and_never_zero_or_inferred_company_link(self):
        row = {**self.rows[0], "asset_type": "INSURANCE", "amount": None, "quantity": None, "quantity_unit": None}
        bundle, _ = prepare([row], self.crosswalk, retrieved_at="2026-10-28T00:00:00+00:00")
        item, proof = bundle["asset_declarations"][0], bundle["evidence"][0]
        self.assertIsNone(item["amount"])
        self.assertIsNone(item["currency"])
        self.assertIn("不得當作零元", proof["summary"])


if __name__ == "__main__":
    unittest.main()
