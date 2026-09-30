import unittest
import detect
TEXT='Brooklyn EMS Box 8460 on the Gowanus Expressway near Exit 17, 92 Street, auto accident, westbound. Brooklyn EMS Box 8460 on the Gowanus Expressway between 65 Street and 92 Street, auto accident, westbound direction.'
class ExpresswayTests(unittest.TestCase):
 def test_candidate(self):
  hit=detect.analyze(TEXT,'fdny')
  self.assertIsNotNone(hit)
  self.assertEqual(hit['address'],'Gowanus Expressway near Exit 17, 92 Street westbound, Brooklyn, NY')
  self.assertIn('westbound',hit['address'])
  self.assertEqual(hit['cross'],'')
 def test_chatter_not_candidate(self):
  self.assertIsNone(detect.analyze('Engine17 responding westbound on the Gowanus Expressway','fdny'))

class SenderTests(unittest.IsolatedAsyncioTestCase):
 async def test_spoken_exit_owner_no_map_rule(self):
  from unittest.mock import patch,AsyncMock,Mock
  import main
  hit=detect.analyze(TEXT,'fdny')
  with patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),patch.object(main,'ops_log'),patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
   result=await main.verify_and_send('fdny',hit,Mock())
   self.assertEqual(result,'sent');send.assert_awaited_once()
 async def test_rejected_incident_visible(self):
  from unittest.mock import patch,Mock
  from pathlib import Path
  import tempfile,main
  stats=Mock()
  with tempfile.TemporaryDirectory() as d,patch.object(main.detect,'analyze',return_value=None),patch.object(main,'_fdny_clip_sanity',return_value=''),patch.object(main,'_fdny_call_record') as record:
   await main._fdny_handle_call({'id':'candidate-test','transcription':TEXT},stats,{},Path(d))
   stats.mark_alert.assert_called_once()
   self.assertIn('rejected by parser',stats.mark_alert.call_args.kwargs['reason'])
