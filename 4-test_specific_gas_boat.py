import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main,fdny_audio_gate as gate

class Specific(unittest.TestCase):
    def test_exact_natures(self):
        for phrase in ['gas detector activation','gas alarm','boat in distress']:
            self.assertEqual(detect.get_nature('Phone Alarm Box 3630 Shore Boulevard for '+phrase,'fdny'),phrase.title().replace(' In ',' in '))
            self.assertTrue(gate.generic_nature_invariant('Phone Alarm for '+phrase,'Phone Alarm'))
            self.assertTrue(gate.generic_nature_invariant('Phone Alarm '+phrase,'Phone Alarm'))
    def test_negative_not_promoted(self):
        for phrase in ['gas detector activation','gas alarm','boat in distress']:
            for lead in ['no ','not ','test ','training ','drill ']:
                self.assertNotEqual(detect.get_nature('Phone Alarm '+lead+phrase,'fdny'),phrase.title().replace(' In ',' in '))
            self.assertFalse(gate.generic_nature_invariant('not for '+phrase,'Phone Alarm'))
    def test_full_typed_three_digit_corner(self):
        self.assertEqual(detect.extract_cross_street('138th Street and 82nd Avenue'),'138th St & 82nd Ave')
        self.assertIsNone(detect.extract_cross_street('1138th Street and 82nd Avenue'))
        self.assertIsNone(detect.extract_cross_street('138 and 82'))
class FinalGate(unittest.IsolatedAsyncioTestCase):
    async def test_lost_specific_still_held(self):
        for complaint in ['gas alarm','gas detector activation','boat in distress']:
            h={'nature':'Phone Alarm','address':'Shore Boulevard, Brooklyn, NY','source':'fdny','excerpt':'Phone Alarm'}
            with patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
                out=await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':'Phone Alarm for '+complaint})
            self.assertEqual(out,'suppressed');send.assert_not_awaited()
