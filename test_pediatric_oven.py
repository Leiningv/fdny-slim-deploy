import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main
PED='Do you have any CHNs available for a Harbor Medical on Kingston Avenue for a pediatric emergency?'
OVEN='Phone alarm Brooklyn Box 6272, 838 Myrtle Avenue off of Marcy and Tompkins Avenue for an oven fire on the first floor.'
class ExactComplaints(unittest.TestCase):
    def test_pediatric(self):
        h=detect.analyze(PED,'zello-hatzalah')
        self.assertEqual(h['nature'],'Pediatric Emergency')
        self.assertEqual(h['address'],'Kingston Avenue, Brooklyn, NY')
    def test_oven_floor(self):
        h=detect.analyze(OVEN,'fdny')
        self.assertEqual(h['nature'],'Oven Fire, First Floor')
        self.assertEqual(h['address'],'838 Myrtle Avenue, Brooklyn, NY')
        self.assertEqual(h['box_heard'],'6272')
    def test_negative_and_training(self):
        for phrase,profile in [('pediatric emergency','hatzolah'),('oven fire','fdny')]:
            for p in ['no ','negative ','training ','test ','drill ']:
                self.assertFalse(detect.get_nature('for '+p+phrase,profile))
    def test_label_without_dispatch_not_promoted(self):
        self.assertFalse(detect.get_nature('Pediatric emergency unit available','hatzolah'))
        self.assertNotEqual(detect.get_nature('oven fire department training','fdny'),'Oven Fire')
    def test_exact_phrase_no_expansion(self):
        self.assertFalse(detect.get_nature('for a pediatric situation','hatzolah'))
        self.assertNotEqual(detect.get_nature('for an oven problem','fdny'),'Oven Fire')
    def test_other_feeds_unchanged(self):
        self.assertFalse(detect.get_nature('for a pediatric emergency','sullivan'))
        self.assertNotEqual(detect.get_nature('for an oven fire','hatzolah'),'Oven Fire')
class MapsRemain(unittest.IsolatedAsyncioTestCase):
    async def test_pediatric_unverified_maps_unsent(self):
        h=detect.analyze(PED,'zello-hatzalah')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'suppressed')
        send.assert_not_awaited()
