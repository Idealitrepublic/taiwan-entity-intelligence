"""Offline guards: public news inventory must not imply identity or publication."""
import unittest

from scripts.audit_public_news_people import article, match_event, regional_events, party_events, cabinet_events


class PublicNewsPeopleAuditTests(unittest.TestCase):
    def setUp(self):
        self.person = {"name": "範例委員", "entity_id": "one", "entity_type": "Politician"}
        self.term = {"entity_id": "one", "term": 11, "constituency": "臺北市第1選舉區", "party": "範例政黨"}
        self.event = {"name": "範例委員", "term": 11, "constituency": "臺北市第1選舉區"}

    def test_name_alone_never_matches(self):
        self.assertEqual(match_event({"name": "範例委員"}, [self.person], [self.term]), [])

    def test_other_term_or_district_does_not_match(self):
        for change in ({"term": 10}, {"constituency": "臺北市第2選舉區"}, {"party": "另一政黨"}):
            self.assertEqual(match_event(dict(self.event, **change), [self.person], [self.term]), [])

    def test_context_matches_candidate_without_mutating_inputs(self):
        before = dict(self.person)
        self.assertEqual(match_event(self.event, [self.person], [self.term]), ["one"])
        self.assertEqual(before, self.person)
        self.assertNotIn("relationship", self.person)

    def test_similar_character_or_romanization_not_an_alias(self):
        self.assertEqual(match_event(dict(self.event, name="範例委員Saidhai"), [self.person], [self.term]), [])

    def test_duplicate_context_stays_ambiguous(self):
        other = dict(self.person, entity_id="two")
        terms = [self.term, dict(self.term, entity_id="two")]
        self.assertEqual(match_event(self.event, [self.person, other], terms), ["one", "two"])

    def test_official_requires_agency_and_role(self):
        person = {"name": "範例官員", "entity_id": "three", "entity_type": "GovernmentOfficial",
                  "official_observations": [{"agency": "範例部", "role": "部長"}]}
        event = {"name": "範例官員", "agency": "範例部", "role": "部長"}
        self.assertEqual(match_event(event, [person], []), ["three"])
        self.assertEqual(match_event(dict(event, role="副部長"), [person], []), [])
        self.assertEqual(match_event(dict(event, agency="另一部"), [person], []), [])

    def test_changed_or_partial_article_stops_instead_of_assuming_coverage(self):
        for parser in (regional_events, party_events):
            with self.assertRaises(ValueError):
                parser('<div class="paragraph"><p>部分名單</p></div>')
        with self.assertRaises(ValueError):
            article('<script>name="範例委員"</script>')

    def test_cabinet_requires_official_corrobation(self):
        with self.assertRaises(ValueError):
            cabinet_events('<div class="paragraph">【內閣改組名單】<p>經濟部長：範例官員</p></div>', "無此官方記錄")


if __name__ == "__main__":
    unittest.main()
