"""Reports may include registry facts only with exact official identifiers."""
import unittest
from unittest.mock import Mock, patch

from src.entities.repository import EntityRepository
from src.report_presentation import present_report
from src.reports import ReportService

ENTITY = "11111111-1111-4111-8111-111111111111"


class ReportRegistryTests(unittest.TestCase):
    def test_live_registry_requires_identical_uniform_number(self):
        def transport(table, params):
            return ([{"value": "96979933"}] if table == "entity_public_identifiers"
                    else [] if table == "companies" else None)
        repository = EntityRepository(transport=transport)
        with patch("src.entities.repository._moea_company_rows", return_value=[{
                "Business_Accounting_NO": "96979933", "Company_Name": "中華電信",
                "Company_Location": "臺北市", "Capital_Stock_Amount": 1000}]):
            record = repository.company_registry_for_entity(ENTITY)
        self.assertEqual(record["uniform_number"], "96979933")
        self.assertEqual(record["data_status"], "live_official_exact_id")
        self.assertIn("data.gcis.nat.gov.tw", record["source_url"])
        with patch("src.entities.repository._moea_company_rows", return_value=[{
                "Business_Accounting_NO": "12345678", "Company_Name": "同名公司"}]):
            self.assertIsNone(repository.company_registry_for_entity(ENTITY))

    def test_report_displays_registry_bilingually_with_source(self):
        repository = Mock()
        repository.entity.return_value = {"id": ENTITY, "entity_type": "Company",
                                          "display_name": "中華電信", "evidence": []}
        repository.graph_neighbors.return_value = None
        repository.company_registry_for_entity.return_value = {
            "uniform_number": "96979933", "name": "中華電信", "address": "臺北市",
            "source": "經濟部", "source_url": "https://data.gcis.nat.gov.tw/record",
            "fetched_at": "2026-10-21T00:00:00Z", "data_status": "live_official_exact_id"}
        report = ReportService(repository).entity_report(ENTITY)
        self.assertEqual(report["company_registry"][0]["uniform_number"], "96979933")
        self.assertTrue(any(row["source_url"].startswith("https://data.gcis")
                            for row in report["sources"]))
        section = next(item for item in present_report(report)["sections"]
                       if item["key"] == "company_registry")
        self.assertIn(("地址 / Address", "臺北市"), section["items"][0]["facts"])


if __name__ == "__main__":
    unittest.main()
