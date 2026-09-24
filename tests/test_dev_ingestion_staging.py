"""Guardrails for the isolated political-source staging adapters."""

import unittest

from scripts.stage_contribution_evidence_dev import normalize_row


class DevelopmentStagingTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "序號": "886", "收支科目": "營利事業捐贈收入",
            "擬參選人／政黨": "王鴻薇", "捐贈者／支出對象": "都一處有限公司",
            "身分證／統一編號": "29072066", "交易日期": "1120801",
            "收入金額": "50000.00", "選舉名稱": "113年立法委員選舉",
            "申報序號／年度": "首次申報",
        }

    def test_corporate_record_is_unresolved_draft_with_source(self):
        evidence = normalize_row(self.row, "2026-09-23T00:00:00+00:00")
        self.assertEqual(evidence["publication_status"], "draft")
        self.assertEqual(evidence["source_locator"]["resolution_status"], "UNRESOLVED")
        self.assertEqual(evidence["source_locator"]["donor_uniform_number"], "29072066")
        self.assertEqual(evidence["source_record_id"], "168061:taipei:incomes:886")
        self.assertEqual(evidence["observed_at"], "2023-08-01T00:00:00+08:00")
        self.assertIn("ardata.cy.gov.tw", evidence["source_url"])

    def test_personal_or_malformed_donor_is_never_staged(self):
        for donor_id in ("A12*******", "1234567", "", "123456789"):
            self.assertIsNone(normalize_row({**self.row, "身分證／統一編號": donor_id},
                                            "2026-09-23T00:00:00+00:00"))

    def test_non_donation_and_invalid_amount_are_rejected(self):
        self.assertIsNone(normalize_row({**self.row, "收支科目": "其他收入"},
                                        "2026-09-23T00:00:00+00:00"))
        self.assertIsNone(normalize_row({**self.row, "收入金額": "0"},
                                        "2026-09-23T00:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()
