"""Official PCC row checks must not accept a page-level name mention."""
import unittest

from scripts.audit_official_procurement_dev import official_row_matches


LOCATOR = {"bidder_uniform_number": "04690983", "bidder_name": "大魯閣實業股份有限公司",
           "title": "運動科技館案", "agency": "桃園市政府", "job_number": "115034", "amount": 450000}


def page(*, winner="是", uniform="04690983", name="大魯閣實業股份有限公司"):
    return ("<html><script>04690983 大魯閣實業股份有限公司</script>"
            "<span>桃園市政府</span><span>運動科技館案</span><span>115034</span>"
            f"<span>廠商代碼</span><span>{uniform}</span><span>廠商名稱</span><span>{name}</span>"
            f"<span>是否得標</span><span>{winner}</span><span>450,000元</span></html>")


class OfficialProcurementAuditTests(unittest.TestCase):
    def test_same_bidder_block_and_award_fields_required(self):
        self.assertTrue(official_row_matches(page(), LOCATOR))
        for html in (page(winner="否"), page(uniform="99999999"), page(name="另一家公司"),
                     page().replace("450,000元", "400,000元"),
                     "<html><script>04690983 大魯閣實業股份有限公司 115034 450,000元</script></html>"):
            with self.subTest(html=html[:60]):
                self.assertFalse(official_row_matches(html, LOCATOR))


if __name__ == "__main__":
    unittest.main()
