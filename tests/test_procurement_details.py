"""Notice detail tests: source paths, exact version, missingness and no name joins."""
import unittest
from unittest.mock import patch
from src.sources import procurement
import app


def notice():
    return {'unit_id': '3.13.31', 'job_number': '0630800011', 'filename': 'BDM-1-53131415',
            'detail': {'已公告資料:預算金額': '0元\n原因：屬收入性質採購',
                       '決標資料:總決標金額': '228,900,001元',
                       '已公告資料:招標方式': '公開招標', '已公告資料:決標方式': '最高標',
                       '決標資料:決標日期': '109/06/03', '決標資料:決標公告日期': '109/07/03',
                       '投標廠商:投標廠商家數': '2',
                       '投標廠商:投標廠商1:廠商名稱': '同名公司',
                       '投標廠商:投標廠商1:廠商代碼': '01234567',
                       '投標廠商:投標廠商1:是否得標': '是',
                       '投標廠商:投標廠商1:決標金額': '0元',
                       '投標廠商:投標廠商2:廠商名稱': '同名公司',
                       '投標廠商:投標廠商2:廠商代碼': '87654321',
                       '投標廠商:投標廠商2:是否得標': '否',
                       '決標品項:第1品項:品項名稱': '測試品項',
                       '決標品項:第1品項:未得標廠商1:未得標廠商': '同名公司',
                       '決標品項:第1品項:未得標廠商1:標價金額': '12美元',
                       'url': 'https://web.pcc.gov.tw/prkms/tender/common/noticeDate/redirectPublic?ds=20200703'}}


class ProcurementDetails(unittest.TestCase):
    def test_zero_reasons_roles_and_dates_preserved_without_name_join(self):
        result = procurement.normalize_notice_detail(notice())
        values = {r['label']: r['value'] for r in result['summary']}
        self.assertEqual(values['預算金額 / Budget'], '0元 原因：屬收入性質採購')
        self.assertNotEqual(values['決標日期 / Award date'], values['公告日期 / Notice date'])
        self.assertEqual(len(result['bidders']), 2)
        self.assertIn('01234567', [r['value'] for r in result['bidders'][0]])
        self.assertIn('否', [r['value'] for r in result['bidders'][1]])
        self.assertIn('12美元', [r['value'] for r in result['items'][0]])
        self.assertEqual(result['lifecycle'], [])
        self.assertNotIn('聯絡電話', str(result))

    def test_only_exact_version_returned_and_invalid_locators_never_fetched(self):
        row = notice()
        with patch.object(procurement, '_json_get', return_value={'records': [row]}) as get:
            result = procurement.lookup_notice_detail('3.13.31', '0630800011', row['filename'])
            self.assertEqual(result['status'], 'ok')
            self.assertIn('job_number=0630800011', get.call_args[0][0])
            self.assertIn('retrieved_at', result)
            self.assertEqual(procurement.lookup_notice_detail('3.13.31', '0630800011', 'other')['status'], 'unavailable')
        with patch.object(procurement, '_json_get') as get:
            with self.assertRaises(ValueError):
                procurement.lookup_notice_detail('https://evil.example', 'x', 'x')
            get.assert_not_called()

    def test_duplicates_errors_and_nonofficial_links_not_reported_as_empty_success(self):
        row = notice()
        with patch.object(procurement, '_json_get', return_value={'records': [row, row]}):
            self.assertEqual(procurement.lookup_notice_detail('3.13.31', '0630800011', row['filename'])['status'], 'unavailable')
        with patch.object(procurement, '_json_get', side_effect=TimeoutError('private error')):
            result = procurement.lookup_notice_detail('3.13.31', '0630800011', row['filename'])
            self.assertEqual(result['status'], 'unavailable')
            self.assertNotIn('private error', str(result))
        row['detail']['已公告資料:標案案號'] = 'other-case'
        with patch.object(procurement, '_json_get', return_value={'records': [row]}):
            self.assertEqual(procurement.lookup_notice_detail('3.13.31', '0630800011', row['filename'])['status'], 'unavailable')
        row['detail']['url'] = 'https://web.pcc.gov.tw.evil.example/'
        self.assertIsNone(procurement.normalize_notice_detail(row)['official_notice_url'])

    def test_api_validation_and_status(self):
        self.assertEqual(app.dispatch('/api/procurement-detail', {})[0], 400)
        with patch('app.lookup_notice_detail', return_value={'status': 'unavailable'}):
            self.assertEqual(app.dispatch('/api/procurement-detail', {})[0], 503)
