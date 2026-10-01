import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main,fdny_audio_gate as gate
FIXTURE='Phone Alarm Box 1597, 15 Temple Court, Terrace Place to Seeley Street, for manhole 0246.'
class Clock(unittest.TestCase):
 def test_terminal_clock_preserves_specific(self):
  h=detect.analyze(FIXTURE,'fdny');self.assertEqual(h['nature'],'Manhole');self.assertEqual(h['address'],'15 Temple Court, Brooklyn, NY');self.assertEqual(h['cross'],'Terrace Place & Seeley Street')
 def test_unit_chatter_still_skipped(self):
  for tail in ['Manhole 246','for manhole 9999','for manhole 0246 Engine246','for manhole 246']:
   self.assertEqual(detect.get_nature('Phone alarm box1597 15 Temple Court '+tail,'fdny'),'',tail)
 def test_clock_requires_fdny_job_local(self):
  self.assertEqual(detect.get_nature('Phone alarm Manhole 0246','fdny'),'')
 def test_generic_specific_veto(self):
  for phrase in ['manhole','elevator','water leak','wires down','transformer','carbon monoxide','gas odor','unstable facade']:
   self.assertTrue(gate.generic_nature_invariant('Phone alarm box1597 15 Temple Court for '+phrase,'Phone Alarm'),phrase)
 def test_negated_not_promoted(self):
  self.assertFalse(gate.generic_nature_invariant('Phone alarm for no manhole','Phone Alarm'))
class Sender(unittest.IsolatedAsyncioTestCase):
 async def test_upstream_failure_cannot_send(self):
  h={'nature':'Phone Alarm','address':'15 Temple Court, Brooklyn, NY','excerpt':'phone alarm'}
  with patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
   out=await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':FIXTURE})
  self.assertEqual(out,'suppressed');send.assert_not_awaited()
