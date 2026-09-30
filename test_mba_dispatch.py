import unittest
import detect
class MBADispatch(unittest.TestCase):
    def test_actual_readouts(self):
        for t in ['Units in Queens load up a bus at the Springfield and 56th Avenue in Oakland Gardens for an MBA.',
                  'Units load a Queens bus at Springfield Boulevard and 56th Avenue Oakland Gardens for the MBA.']:
            self.assertEqual(detect.get_nature(t,'hatzolah'),'Mva')
    def test_not_blanket_acronym_swap(self):
        for t in ['MBA','for an MBA','patient has an MBA degree','units at Springfield for an MBA',
                  'training units load a bus at Springfield for an MBA','units load a bus at Springfield for no MBA']:
            self.assertFalse(detect.get_nature(t,'hatzolah'))
    def test_other_feeds_unchanged(self):
        self.assertFalse(detect.get_nature('Units load a bus at Springfield for an MBA','sullivan'))
from unittest.mock import AsyncMock, Mock, patch
import main
class MBAMap(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_does_not_exempt_map(self):
        t='Units in Queens load up a bus at Springfield Boulevard and 56th Avenue in Oakland Gardens for an MBA.'
        h=detect.analyze(t,'zello-hatzalah')
        self.assertEqual(h['nature'],'Mva')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),
              patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'suppressed')
        send.assert_not_awaited()
