from datetime import datetime, timezone
import unittest
from scripts.public_release_health import SQL, markdown, report

class PublicReleaseHealthTests(unittest.TestCase):
    def counts(self):
        return {'entities':dict.fromkeys(('Company','Politician','GovernmentOfficial','GovernmentAgency','PoliticalParty','CivilOrganization','Contract'),1), 'relationships':1,'evidence':1,'invalid_edges':0,'missing_provenance':0,'duplicate_edges':0,'missing_glyph_names':0,'freshness':[{'source_name':'官方名冊','records':1,'oldest_retrieved_at':'2026-10-01T00:00:00Z','latest_retrieved_at':'2026-11-01T00:00:00Z'}]}

    def test_read_only_public_scope_retains_actual_age_and_unknown_coverage(self):
        self.assertIn('begin read only',SQL)
        self.assertIn('set local role anon',SQL)
        value=report(self.counts(),datetime(2026,11,20,tzinfo=timezone.utc))
        self.assertEqual(value['high_count'],0)
        self.assertEqual(value['counts']['freshness'][0]['latest_retrieval_age_hours'],456)
        self.assertIsNone(value['population_coverage'])
        self.assertFalse(value['freshness_certified'])
        self.assertIn('不等於上線總驗收通過',markdown(value))

    def test_missing_integrity_counts_and_withheld_types_fail_closed(self):
        for key in ('invalid_edges','missing_provenance','duplicate_edges','missing_glyph_names'):
            counts=self.counts()
            counts[key]=1
            self.assertIn(key,report(counts)['failures'])
            del counts[key]
            self.assertIn(key,report(counts)['failures'])
        counts=self.counts()
        counts['entities']['Judgment']=1
        self.assertIn('public_entity_scope',report(counts)['failures'])
