import unittest
from unittest.mock import patch,AsyncMock,Mock
import detect,main
TEXT='Box three, Box 2274, terminal 1001 Avenue K, Kings and Remsen Avenue, automatic alarm. Box three, Box 2274, terminal 1001 Avenue K, Kings and Remsen Avenue, automatic alarm. 0535, Brooklyn.'
class Sender(unittest.IsolatedAsyncioTestCase):
 async def test_actual_terminal_candidate_cannot_send(self):
  # Keep terminal hold coverage independent of the new nature exclusion.
  h=detect.analyze(TEXT.replace('automatic alarm','manual alarm'),'fdny')
  with patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'ATLANTIC TERMINAL, Brooklyn, NY, USA',40.684918,-73.977602,'Brooklyn')) as geo,patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
   self.assertEqual(await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':TEXT}),'suppressed')
   geo.assert_not_awaited();send.assert_not_awaited();self.assertIn('terminal',h['hold_reason'])
 async def test_ambiguous_digits_not_forced_to_house(self):
  h={'nature':'Automatic Alarm','address':'1001 Avenue K, Brooklyn, NY','excerpt':TEXT}
  with patch.object(main,'geocode_verify',new_callable=AsyncMock) as geo:
   self.assertEqual(await main.verify_and_send('fdny',h,Mock(),prepare_only=True),'suppressed');geo.assert_not_awaited()
 def test_unrelated_house_retained(self):
  h=detect.analyze('Box 2274, 1111 Avenue U automatic alarm','fdny');self.assertEqual(h['address'],'1111 Avenue U, Brooklyn, NY')
