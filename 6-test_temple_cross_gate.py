import unittest
from unittest.mock import AsyncMock,Mock,patch
import main,detect
class CrossGate(unittest.IsolatedAsyncioTestCase):
 async def run_case(self,valid):
  t='Phone alarm Box1597,15 Temple Court,Terrace Place to Seeley Street,for manhole 0246.'
  h=detect.analyze(t,'fdny')
  with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'15 Temple Court, Brooklyn, NY',40.65,-73.97,'Brooklyn')),
        patch('spoken_cross.verify',new_callable=AsyncMock,return_value=valid),
        patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
        patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),
        patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'_save_recent'),patch.object(main,'ops_log'),
        patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send):
   out=await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':t})
  return out,h,send
 async def test_failed_cross_holds(self):
  out,h,send=await self.run_case(False);self.assertEqual(out,'suppressed');send.assert_not_awaited();self.assertIn('cross pair',h['hold_reason'])
 async def test_verified_crosses_preserved(self):
  out,h,send=await self.run_case(True);self.assertEqual(out,'sent');self.assertIn('Terrace Place',send.await_args.args[0]);self.assertIn('Seeley Street',send.await_args.args[0]);self.assertIn('MANHOLE',send.await_args.args[0])
