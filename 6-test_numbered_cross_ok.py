import unittest
from unittest.mock import AsyncMock, patch
import main
import spoken_cross


class NumberedCross(unittest.IsolatedAsyncioTestCase):
    async def test_real_numbered_cross_passes(self):
        with patch.object(main, 'geocode_verify', new=AsyncMock(return_value=(True,False,'x',40.6353,-73.923,'Brooklyn'))), patch.object(spoken_cross, 'verify', new=AsyncMock(return_value=True)):
            self.assertTrue(await main._numbered_cross_map_verified(
                '5804 Farragut Road, Brooklyn, NY', 'East 58th Street'))

    async def test_unmatched_numbered_cross_holds(self):
        with patch.object(main, 'geocode_verify', new=AsyncMock(return_value=(True,False,'x',40.6353,-73.923,'Brooklyn'))), patch.object(spoken_cross, 'verify', new=AsyncMock(return_value=False)):
            self.assertFalse(await main._numbered_cross_map_verified(
                '5804 Farragut Road, Brooklyn, NY', 'East 2nd Street'))

    async def test_map_failure_holds(self):
        with patch.object(main, 'geocode_verify', new=AsyncMock(side_effect=RuntimeError('x'))):
            self.assertFalse(await main._numbered_cross_map_verified(
                '5804 Farragut Road, Brooklyn, NY', 'East 58th Street'))

    async def test_two_sides_both_must_verify(self):
        with patch.object(main, 'geocode_verify', new=AsyncMock(return_value=(True,False,'x',40.6353,-73.923,'Brooklyn'))), patch.object(spoken_cross, 'verify', new=AsyncMock(side_effect=[True, False])):
            self.assertFalse(await main._numbered_cross_map_verified(
                '5804 Farragut Road, Brooklyn, NY', 'East 58th Street & East 59th Street'))

    async def test_no_numbered_side_is_false(self):
        self.assertFalse(await main._numbered_cross_map_verified('1 A St', 'Nostrand Avenue'))


if __name__ == '__main__':
    unittest.main()
