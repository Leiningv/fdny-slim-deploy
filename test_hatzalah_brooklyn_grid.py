"""No-spoken-borough Hatzalah grid exception, fail closed outside its scope."""
import unittest
from unittest.mock import AsyncMock, Mock, patch

import detect
import main


class _Response:
    status = 200
    async def json(self):
        return {'address': {'county': 'Kings County', 'state': 'New York'}}
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False


class _Session:
    def get(self, *args, **kwargs):
        return _Response()
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False


class BrooklynGrid(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.phrase = '70 units to 12 between 45 and 46 for an infant difficulty breathing.'
        self.hit = detect.analyze(self.phrase, 'zello-hatzalah')
        self.assertEqual(self.hit['address'], '12th Ave between 45th & 46th St, Brooklyn, NY')
        self.assertEqual(self.hit['nature'], 'Difficulty Breathing')
        self.assertTrue(self.hit['area_defaulted'])

    async def test_grid_requires_two_distinct_junctions_and_kings(self):
        with (patch.object(main, '_intersection_point', new_callable=AsyncMock,
                           side_effect=[(40.6387, -73.9927), (40.6382, -73.9931)]) as intersects,
              patch.object(main.aiohttp, 'ClientSession', return_value=_Session())):
            point = await main._hatzalah_brooklyn_grid_corridor(self.hit)
        self.assertIsNotNone(point)
        self.assertEqual(intersects.await_count, 2)
        self.assertEqual(intersects.await_args_list[0].args,
                         ('12th Avenue, Brooklyn, NY', '45th Street'))
        self.assertEqual(intersects.await_args_list[1].args,
                         ('12th Avenue, Brooklyn, NY', '46th Street'))

    async def test_actual_hit_can_post_after_full_verification(self):
        with (patch.object(main, '_hatzalah_brooklyn_grid_corridor', new_callable=AsyncMock,
                           return_value=(40.6384, -73.9929)),
              patch.object(main, 'geocode_verify', new_callable=AsyncMock,
                           return_value=(False, False, '', None, None, '')),
              patch.object(main, '_cross_streets', new_callable=AsyncMock, return_value=(None, False)),
              patch.object(main, '_map_street_names', new_callable=AsyncMock, return_value=set()),
              patch.object(main.control, 'muted_feeds', return_value=set()),
              patch.object(main, '_load_recent', return_value=[]),
              patch.object(main, '_save_recent'),
              patch.object(main, 'ops_log'),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock, return_value=True) as send):
            result = await main.verify_and_send('zello-hatzalah', self.hit, Mock())
        self.assertEqual(result, 'sent')
        self.assertIn('12th Ave between 45th & 46th St, Brooklyn, NY', send.await_args.args[0])
        self.assertNotIn('(not confirmed)', send.await_args.args[0])

    async def test_wrong_area_or_profile_never_uses_exception(self):
        for profile, address, excerpt in [
            ('fdny', self.hit['address'], self.phrase),
            ('zello-sullivan', self.hit['address'], self.phrase),
            ('zello-hatzalah', '12th Ave between 45th & 46th St, Queens, NY', self.phrase),
            ('zello-hatzalah', self.hit['address'], self.phrase + ' Queens dispatch'),
            ('zello-hatzalah', '12th Ave between 45th & 47th St, Brooklyn, NY', self.phrase),
            ('zello-hatzalah', '12th Avenue, Brooklyn, NY', self.phrase),
        ]:
            with self.subTest(profile=profile, address=address, excerpt=excerpt):
                hit = dict(self.hit, source=profile, address=address, excerpt=excerpt)
                with patch.object(main, '_intersection_point', new_callable=AsyncMock) as intersection:
                    self.assertIsNone(await main._hatzalah_brooklyn_grid_corridor(hit))
                    intersection.assert_not_awaited()

    async def test_map_failure_or_wrong_county_stays_held(self):
        for points in [((None, None), (40.6382, -73.9931)),
                       ((40.6387, -73.9927), (40.6700, -73.9900))]:
            with (patch.object(main, '_intersection_point', new_callable=AsyncMock,
                               side_effect=points),
                  patch.object(main.aiohttp, 'ClientSession', return_value=_Session())):
                self.assertIsNone(await main._hatzalah_brooklyn_grid_corridor(self.hit))
        class WrongCounty(_Response):
            async def json(self):
                return {'address': {'county': 'Queens County', 'state': 'New York'}}
        class WrongSession(_Session):
            def get(self, *args, **kwargs):
                return WrongCounty()
        with (patch.object(main, '_intersection_point', new_callable=AsyncMock,
                           side_effect=[(40.6387, -73.9927), (40.6382, -73.9931)]),
              patch.object(main.aiohttp, 'ClientSession', return_value=WrongSession())):
            self.assertIsNone(await main._hatzalah_brooklyn_grid_corridor(self.hit))


if __name__ == '__main__':
    unittest.main()
