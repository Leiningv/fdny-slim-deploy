"""Do not turn a Class 3 Broadway house into its Linden cross street."""
import unittest
from unittest.mock import AsyncMock, Mock, patch
import detect
import main

DISPATCH = ('Class 3 Box 773 Terminal 15, 1333 Broadway, Linden Street to '
            'Grove Street, automatic alarm. Class 3 Box 773 Terminal 15, '
            '1333 Broadway, Linden Street to Grove Street, automatic alarm.')

class BroadwayHouse(unittest.IsolatedAsyncioTestCase):
    def test_extracts_spoken_house_not_cross(self):
        h=detect.analyze(DISPATCH,'fdny')
        self.assertEqual(h['address'],'1333 Broadway, Brooklyn, NY')
        self.assertEqual(h['box_heard'],'0773')
        self.assertEqual(h['nature'],'Automatic Alarm')
        self.assertTrue(h['class3_house_address'])
        self.assertEqual(h['cross'],'Linden Street & Grove Street')

    def test_never_promotes_terminal_id_or_unanchored_broadway(self):
        for t in ('Class 3 Box 773 Terminal 15, Linden Street to Grove Street, automatic alarm.',
                  'Terminal 15 1333 Broadway, Linden Street to Grove Street, automatic alarm.'):
            h=detect.analyze(t,'fdny')
            self.assertFalse(h and h['address'].startswith('1333 Broadway'))

    async def test_verified_house_posts_without_invented_cross(self):
        h=detect.analyze(DISPATCH,'fdny')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,
                           return_value=(True,False,'1333 BROADWAY, Brooklyn, NY',40.690258,-73.922899,'Brooklyn')),
              patch.object(main,'_box_lookup',new_callable=AsyncMock,
                           return_value=[('BROADWAY OPP LINDEN ST','Brooklyn')]),
              patch.object(main,'_load_box_cache',return_value={}),
              patch.object(main,'_nearest_box',new_callable=AsyncMock,
                           return_value=('0773','BROADWAY OPP LINDEN ST',30)),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),
              patch.object(main,'_save_recent'),
              patch.object(main,'_ensure_ogg',return_value=None),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send,
              patch.object(main,'ops_log'),patch.object(main,'_uguu_upload',new_callable=AsyncMock)):
            await main.verify_and_send('fdny',h,Mock(),'',fresh_ts=None)
        self.assertEqual(send.await_count,1,h.get('hold_reason'))
        text=send.await_args.args[0]
        self.assertIn('1333 Broadway',text)
        self.assertNotIn('Linden Street, Brooklyn',text)
        self.assertNotIn('Grove Street & Bushwick',text)
