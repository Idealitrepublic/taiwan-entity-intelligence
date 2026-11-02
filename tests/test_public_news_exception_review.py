import copy
import unittest
from scripts.review_public_news_exceptions import review, full_name_tokens


class ExceptionReviewTests(unittest.TestCase):
    def setUp(self):
        self.row = {'姓名': '伍麗華 Saidhai．Tahovecahe', '事件日期': '2024-01-13',
                    '屆別': '11', '選區或機關': '山地原住民選舉區'}
        self.person = {'name': '伍麗華Saidhai‧Tahovecahe', 'entity_id': 'unchanged-id',
                       'entity_type': 'Politician',
                       'terms': [{'term': 11, 'constituency': '山地原住民選舉區'}]}
        self.member = {'name': self.person['name'], 'term': 11, 'areaName': '山地原住民選舉區'}

    def test_scoped_approval_preserves_id_and_inputs(self):
        before = copy.deepcopy(self.person)
        result = review(self.row, [self.person], [self.member], '')
        self.assertEqual(result[1], 'unchanged-id')
        self.assertEqual(self.person, before)

    def test_different_term_district_date_rejected(self):
        for key, value in [('屆別', '10'), ('選區或機關', '平地原住民選舉區'), ('事件日期', '2025-01-13')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                review(dict(self.row, **{key: value}), [self.person], [self.member], '')

    def test_duplicate_or_missing_official_identity_rejected(self):
        for official in [[], [self.member, self.member]]:
            with self.assertRaises(ValueError):
                review(self.row, [self.person], official, '')
        with self.assertRaises(ValueError):
            review(self.row, [self.person, self.person], [self.member], '')

    def test_indigenous_name_not_discarded(self):
        self.assertNotEqual(full_name_tokens('伍麗華'), full_name_tokens(self.row['姓名']))
        self.assertNotEqual(full_name_tokens('伍麗華 Other'), full_name_tokens(self.row['姓名']))

    def test_historical_office_not_rewritten(self):
        row = {'姓名': '李妍慧', '事件日期': '2025-08-27', '選區或機關': '僑務委員會', '政黨或職務': '副委員長'}
        person = {'name': '李姸慧', 'entity_type': 'GovernmentOfficial', 'entity_id': 'existing',
                  'official_observations': [{'agency': '僑務委員會', 'role': '代理委員長'}]}
        text = '李姸慧出席緬甸歸僑協會新春團拜；僑務委員會副委員長李妍慧'
        self.assertEqual(review(row, [person], [], text)[1], 'existing')
        self.assertEqual(person['official_observations'][0]['role'], '代理委員長')
        with self.assertRaises(ValueError):
            review(row, [person], [], '')
        with self.assertRaises(ValueError):
            review(dict(row, 政黨或職務='代理委員長'), [person], [], text)

    def test_historical_draft_and_outside_cohort_not_approved(self):
        for name in ['游錫堃', '張惇涵']:
            self.assertEqual(review({'姓名': name}, [], [], '')[1], '')
