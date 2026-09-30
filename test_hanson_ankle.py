import unittest
from unittest.mock import AsyncMock, Mock, patch
import detect, main
H='On a sign class three box 60962, Hanson Place, off of South Elliott Place, for automatic alarm.'
class HansonAnkle(unittest.TestCase):
    def test_punctuation_glue_keeps_house_and_ambiguity(self):
        for sep in [', ','; ',' ']:
            h=detect.analyze(H.replace('60962, ','60962'+sep),'fdny')
            self.assertEqual(h['address'],'62 Hanson Place, Brooklyn, NY')
            self.assertEqual(h['box_heard'],'0609')
            self.assertEqual(h['raw_box_run'],'60962')
            self.assertTrue(h['box_glue_ambiguous'])
            self.assertEqual(h['cross'],'South Elliott Place')
    def test_standalone_box_not_house(self):
        self.assertEqual(detect._split_box_glue('box 60962, dispatch 278'),'box 60962, dispatch 278')
    def test_ankle_spoken_retained(self):
        h=detect.analyze('Central Dispatch Rock Hill Mutual Aid to Woodridge 15 Old Falls Road 10-year-old male ankle injury BLS response','zello-sullivan')
        self.assertEqual(h['nature'],'Ankle Injury')
        self.assertEqual(h['address'],'15 Old Falls Road, Woodridge, NY')
    def test_negated_ankle_not_promoted(self):
        for prefix in ['no ','training ','negative ']:
            self.assertFalse(detect.get_nature(prefix+'ankle injury','sullivan'))
    def test_other_feed_and_bare_ankle_not_promoted(self):
        self.assertFalse(detect.get_nature('ankle equipment','sullivan'))
        self.assertFalse(detect.get_nature('ankle injury','fdny'))
class Guard(unittest.IsolatedAsyncioTestCase):
    async def test_glue_cannot_bypass_map(self):
        h=detect.analyze(H,'fdny')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),
              patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),
              patch.object(main,'_load_box_cache',return_value={}),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),
              patch.object(main,'ops_log'),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('fdny',h,Mock()),'suppressed')
        send.assert_not_awaited()
