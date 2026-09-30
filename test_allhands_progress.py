import unittest
from unittest.mock import AsyncMock,Mock,patch
import main,fdny_audio_gate as gate
ACTUAL='Progress report your all hands box533,191ClintonStreet. Division11DeputyChief reports going to be dropping down to three engines,two trucks with the fast truck.'
class Progress(unittest.TestCase):
    def test_reduce_resources(self):
        self.assertTrue(gate.generic_nature_invariant(ACTUAL,'All Hands'))
    def test_new_activation_unchanged(self):
        self.assertFalse(gate.generic_nature_invariant('All hands going to work box533191ClintonStreet','All Hands'))
    def test_specific_complaint_unchanged(self):
        self.assertFalse(gate.generic_nature_invariant(ACTUAL,'Electrical Fire'))
class Final(unittest.IsolatedAsyncioTestCase):
    async def test_final_gate(self):
        h={'source':'fdny','nature':'All Hands','address':'191 Clinton Street, Brooklyn, NY','excerpt':'All Hands'}
        with patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
            self.assertEqual(await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':ACTUAL}),'suppressed')
        send.assert_not_awaited()
