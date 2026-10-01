import unittest
from unittest.mock import AsyncMock,Mock,patch
import main,fdny_audio_gate as gate,detect

ACTUAL="Phone Alarm's going to work, Box 3047, tentative address of 1878 New York Avenue, Avenue K, King, Avenue J, John, tentative private dwelling."
class Invariant(unittest.TestCase):
    def test_actual_degraded_fixture(self):
        h=detect.analyze(ACTUAL,'fdny')
        self.assertEqual(h['nature'],'');self.assertTrue(gate.generic_nature_invariant(ACTUAL,'Phone Alarm'))
    def test_every_class_and_fallback(self):
        for phrase in ['all hands','all-hands','going to work','working fire','10-75','10 75','1075','private dwelling','multiple dwelling','fire in rear']:
            for nature in ['Phone Alarm','Automatic Alarm','Fire Alarm','Alarm Activation','Class 3','Fire']:
                self.assertTrue(gate.generic_nature_invariant(phrase,nature),(phrase,nature))
    def test_specific_nature_retained(self):
        self.assertFalse(gate.generic_nature_invariant('fire in rear multiple dwelling','Fire in the Rear, Multiple Dwelling'))
    def test_plain_phone_alarm_not_escalation(self):
        self.assertFalse(gate.generic_nature_invariant('Phone alarm box3047 address1878 New York Avenue','Phone Alarm'))
class FinalSenderGate(unittest.IsolatedAsyncioTestCase):
    async def test_no_send_even_if_upstream_missed(self):
        h=detect.analyze(ACTUAL,'fdny')
        with patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
            out=await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':ACTUAL})
        self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_full_source_not_truncated_excerpt(self):
        h={'source':'fdny','nature':'Phone Alarm','address':'1878 New York Avenue, Brooklyn, NY','excerpt':'Phone alarm'}
        with patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
            out=await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':'x '*300+'all hands'})
        self.assertEqual(out,'suppressed');send.assert_not_awaited()
