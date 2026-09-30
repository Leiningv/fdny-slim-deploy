import unittest
from unittest.mock import AsyncMock, patch
import detect
import main

TEXT = ("15 in Brooklyn. Box 1636. We're using all hands for a fire on the second "
        "floor of a two-story building 20 by 40 non-fireproof. "
        "The address is 284 Grafton. Exposures are as follows: one street two alley.")

class Suffixless(unittest.IsolatedAsyncioTestCase):
    def test_explicit_house_beats_box_and_exposure_chatter(self):
        hit = detect.analyze(TEXT, 'fdny')
        self.assertEqual(hit['address'], '284 Grafton, Brooklyn, NY')
        self.assertFalse(hit['box_only'])
        self.assertEqual(hit['suffixless_spoken_address'], '284 Grafton')
        self.assertEqual(hit['nature'], 'All Hands, Second Floor')

    def test_no_bare_chatter_or_mixed_inference(self):
        for text in ['Box 1636 all hands, 284 Grafton.',
                     TEXT + ' Box 3907, car fire.',
                     TEXT + ' The address is 285 Grafton.']:
            self.assertEqual(detect.fdny_suffixless_address(text), '')

    async def resolve(self, labels):
        from unittest.mock import Mock
        response = Mock(status=200)
        response.json = AsyncMock(return_value={"features": [
            {"properties": {"label": label, "borough": borough},
             "geometry": {"coordinates": [-73.9, 40.6]}} for label, borough in labels]})
        context = AsyncMock()
        context.__aenter__.return_value = response
        session = Mock()
        session.get.return_value = context
        outer = AsyncMock()
        outer.__aenter__.return_value = session
        with patch.object(main.aiohttp, 'ClientSession', return_value=outer):
            return await main._resolve_fdny_suffixless('284 Grafton, Brooklyn, NY')

    async def test_only_exact_house_name_supplies_type(self):
        self.assertEqual(await self.resolve([('284 Grafton Street, Brownsville, NY', 'Brooklyn')]),
                         '284 Grafton Street, Brooklyn, NY')
        for label in ['285 Grafton Street, Brooklyn, NY',
                      '284 Grafton Avenue West, Brooklyn, NY',
                      '284 Grattan Street, Brooklyn, NY', '', 'Grafton Street, Brooklyn, NY']:
            self.assertIsNone(await self.resolve([(label, 'Brooklyn')]))
        self.assertIsNone(await self.resolve([('284 Grafton Street, Queens, NY', 'Queens')]))
        self.assertIsNone(await self.resolve([('284 Grafton Street, Brooklyn, NY', 'Brooklyn'),
                                              ('284 Grafton Avenue, Brooklyn, NY', 'Brooklyn')]))

    async def test_suffixless_map_failure_never_sends(self):
        from unittest.mock import Mock
        hit = detect.analyze(TEXT, 'fdny')
        with (patch.object(main, '_resolve_fdny_suffixless', new_callable=AsyncMock, return_value=None),
              patch.object(main.control, 'muted_feeds', return_value=set()),
              patch.object(main, '_load_recent', return_value=[]),
              patch.object(main, 'ops_log'),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock) as send):
            outcome = await main.verify_and_send('fdny', hit, Mock(), prepare_only=True)
        self.assertEqual(outcome, 'suppressed')
        self.assertIn('not exactly map verified', hit['hold_reason'])
        send.assert_not_awaited()

    async def test_verified_house_survives_box_cross_mismatch(self):
        from unittest.mock import Mock
        hit = detect.analyze(TEXT, 'fdny')
        with (patch.object(main, '_resolve_fdny_suffixless', new_callable=AsyncMock,
                           return_value='284 Grafton Street, Brooklyn, NY'),
              patch.object(main, 'geocode_verify', new_callable=AsyncMock,
                           return_value=(True, False, '284 Grafton Street, Brooklyn, NY', 40.6, -73.9, 'Brooklyn')),
              patch.object(main, '_box_lookup', new_callable=AsyncMock,
                           return_value=[('OTHER ST at REMOTE AVE', 'Brooklyn')]),
              patch.object(main, '_nearest_box', new_callable=AsyncMock, return_value=('', '', 999)),
              patch.object(main, '_cross_streets', new_callable=AsyncMock, return_value=(None,False)),
              patch.object(main, '_map_street_names', new_callable=AsyncMock, return_value=set()),
              patch.object(main.control, 'muted_feeds', return_value=set()),
              patch.object(main, '_load_recent', return_value=[]),
              patch.object(main, 'ops_log'),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock) as send):
            outcome = await main.verify_and_send('fdny', hit, Mock(), prepare_only=True)
        self.assertEqual(outcome, 'verified')
        self.assertEqual(hit['address'], '284 Grafton Street, Brooklyn, NY')
        send.assert_not_awaited()

    async def test_true_box_only_keeps_cross_corroboration(self):
        from unittest.mock import Mock
        hit = {'address':'FDNY Box 1636, Brooklyn, NY', 'nature':'All Hands',
               'box_only':True, 'box_heard':'1636', 'excerpt':'Box 1636 all hands', 'cross':''}
        with (patch.object(main, '_box_lookup', new_callable=AsyncMock,
                           return_value=[('OTHER ST at REMOTE AVE', 'Brooklyn')]),
              patch.object(main.control, 'muted_feeds', return_value=set()),
              patch.object(main, '_load_recent', return_value=[]),patch.object(main, 'ops_log')):
            outcome = await main.verify_and_send('fdny', hit, Mock(), prepare_only=True)
        self.assertEqual(outcome, 'suppressed')
        self.assertEqual(hit['hold_reason'], 'box-only crosses uncorroborated')

if __name__ == '__main__':
    unittest.main()
