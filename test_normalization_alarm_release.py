import unittest
from spoken_cross import normalize_pair

class TestNumberedCrossPair(unittest.TestCase):
    def test_explicit_plural_type(self):
        self.assertEqual(normalize_pair(['5th','6th Avenues']), ['5th Avenue','6th Avenue'])
    def test_named_existing_abbreviation(self):
        self.assertEqual(normalize_pair(['Foster','Newkirk Avenue']), ['Foster Avenue','Newkirk Avenue'])
    def test_no_invented_type(self):
        self.assertEqual(normalize_pair(['5th','6th']), ['5th','6th'])
    def test_different_explicit_types_preserved(self):
        self.assertEqual(normalize_pair(['5th Street','6th Avenues']), ['5th Street','6th Avenue'])
    def test_multiname_not_inherited(self):
        self.assertEqual(normalize_pair(['Old Mill','Newkirk Avenue']), ['Old Mill','Newkirk Avenue'])

from unittest.mock import AsyncMock, Mock, patch
import detect, main

class Test298SendGate(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, verdicts, expected):
        hit=detect.analyze('Phone Alarm Box 1274, 298 12th Street, off of 5th and 6th Avenues for a gas odor in front of the building.','fdny')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'298 12 STREET, Brooklyn, NY, USA',40.66693,-73.987329,'Brooklyn')),
              patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),
              patch('spoken_cross.verify',new_callable=AsyncMock,side_effect=verdicts) as verify,
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),patch.object(main,'_save_recent'),patch.object(main,'ops_log'),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send):
            self.assertEqual(await main.verify_and_send('fdny',hit,Mock(),None),expected)
            self.assertEqual([c.args[1] for c in verify.await_args_list],['5th Avenue','6th Avenue'])
            if expected=='sent':
                text=send.await_args.args[0]
                self.assertIn('298 12th Street',text)
                self.assertIn('5th Avenue & 6th Avenue',text)
                self.assertIn('GAS ODOR',text)
            else:
                send.assert_not_awaited()
    async def test_both_verified_carry(self):
        await self.run_case([True,True],'sent')
    async def test_one_false_retains_hold(self):
        await self.run_case([True,False],'suppressed')
import unittest,time
from unittest.mock import AsyncMock,Mock,patch
import main,detect
class AlarmActivationHold(unittest.IsolatedAsyncioTestCase):
    async def test_all_feeds_no_geocode_or_send(self):
        for p in ['fdny','zello-hatzalah','zello-sullivan']:
            for n in ['Alarm Activation','alarm activation','Alarm Activation, First Floor','Alarm Activation, Apartment 2H']:
                h={'nature':n,'address':'878 Park Avenue, Brooklyn, NY','excerpt':'for alarm activation'}
                with (patch.object(main,'geocode_verify',new_callable=AsyncMock) as geo,
                      patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send,
                      patch.object(main.alert_waha,'send_voice',new_callable=AsyncMock) as voice):
                    self.assertEqual(await main.verify_and_send(p,h,Mock()),'suppressed')
                geo.assert_not_awaited();send.assert_not_awaited();voice.assert_not_awaited()
                self.assertEqual(h['nature'],n)
                self.assertEqual(h['hold_reason'],'Alarm Activation excluded by owner')
    async def test_zello_no_second_listen(self):
        h={'nature':'Alarm Activation','address':'878 Park Avenue, Brooklyn, NY','excerpt':'for alarm activation'}
        with patch.object(main,'_bounded_second_listen',new_callable=AsyncMock) as listen:
            outcome,h=await main.verify_zello_with_second_listen('zello-hatzalah',h,Mock(),'unused.wav',fresh_ts=time.time())
        self.assertEqual(outcome,'suppressed');listen.assert_not_awaited()
    def test_specific_fire_not_removed(self):
        self.assertEqual(detect.get_nature('Phone alarm box 356, 878 Park Avenue, for an oven fire','fdny'),'Oven Fire')
        self.assertEqual(detect.get_nature('Phone alarm box 356, 878 Park Avenue, for alarm activation','fdny'),'Alarm Activation')
