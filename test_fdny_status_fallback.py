import unittest
from unittest.mock import AsyncMock,Mock,patch
import main,fdny_audio_gate as gate
ACTUAL='Division1,okay.PhoneAlarmBox0533,191ClintonStreet.191ClintonStreet is completely evacuated. Primary is a negative throughout. Also164Atlantic is completely evacuated. NationalGrid is on scene and has the leak under control.'
class Status(unittest.TestCase):
    def test_actual(self):
        self.assertTrue(gate.generic_nature_invariant(ACTUAL,'Phone Alarm'))
    def test_each_status(self):
        for status in ['completely evacuated','primary negative','primary search is negative','leak under control','leak is under control']:
            self.assertTrue(gate.generic_nature_invariant('Phone alarm Box0533 '+status,'Phone Alarm'))
    def test_new_dispatch_not_status_alone(self):
        self.assertFalse(gate.generic_nature_invariant('Phone alarm, oldjob completely evacuated. New job reporting an automatic alarm.','Phone Alarm'))
    def test_specific_and_plain_unaffected(self):
        self.assertFalse(gate.generic_nature_invariant(ACTUAL,'Gas Leak'))
        self.assertFalse(gate.generic_nature_invariant('Phone alarm Box0533 at191ClintonStreet','Phone Alarm'))
class Final(unittest.IsolatedAsyncioTestCase):
    async def test_final_send_gate(self):
        h={'source':'fdny','nature':'Phone Alarm','address':'191 Clinton Street, Brooklyn, NY','excerpt':'Phone alarm'}
        with patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
            self.assertEqual(await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':ACTUAL}),'suppressed')
        send.assert_not_awaited()
