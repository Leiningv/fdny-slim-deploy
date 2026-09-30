import unittest,time
from unittest.mock import AsyncMock,Mock,patch
import main,detect
class AutomaticHold(unittest.IsolatedAsyncioTestCase):
    async def test_final_all_feeds_with_details(self):
        for p in ['fdny','zello-hatzalah','zello-sullivan']:
            for n in ['Automatic Alarm','automatic alarm','Automatic Alarm, First Floor','Automatic Alarm, Apartment 2H']:
                h={'nature':n,'address':'501 New Lots Avenue, Brooklyn, NY','excerpt':'automatic alarm'}
                with (patch.object(main,'geocode_verify',new_callable=AsyncMock) as geo,patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
                    self.assertEqual(await main.verify_and_send(p,h,Mock()),'suppressed')
                self.assertEqual(h['nature'],n)
                self.assertEqual(h['hold_reason'],'Automatic Alarm excluded by owner')
                geo.assert_not_awaited();send.assert_not_awaited()
    async def test_wrapper_does_not_try_second_listen(self):
        h={'nature':'Automatic Alarm','address':'501 New Lots Avenue, Brooklyn, NY','excerpt':'for automatic alarm'}
        with patch.object(main,'_bounded_second_listen',new_callable=AsyncMock) as listen:
            outcome,h=await main.verify_zello_with_second_listen('zello-hatzalah',h,Mock(),'unused.wav',fresh_ts=time.time())
        self.assertEqual(outcome,'suppressed');listen.assert_not_awaited()
    async def test_other_natures_unchanged(self):
        for n in ['Fire, Apartment 2H','Oven Fire, First Floor','Manual Alarm','Activated Fire Alarm','Automatic Fire Alarm']:
            h={'nature':n,'address':'501 New Lots Avenue, Brooklyn, NY','excerpt':'test'}
            with patch.object(main.control,'muted_feeds',return_value={'fdny'}):
                self.assertEqual(await main.verify_and_send('fdny',h,Mock()),'suppressed')
            self.assertEqual(h['hold_reason'],'feed muted')
    def test_parser_keeps_label_and_specific_fire(self):
        self.assertEqual(detect.get_nature('for automatic alarm','fdny'),'Automatic Alarm')
        self.assertEqual(detect.get_nature('for an oven fire on the first floor','fdny'),'Oven Fire')
