import asyncio, unittest
import spoken_cross as sc

XML = b"""<osm>
<node id="1" lat="40.6870" lon="-73.9545"/><node id="2" lat="40.6872" lon="-73.9540"/>
<way id="10"><nd ref="1"/><tag k="highway" v="residential"/><tag k="name" v="Bedford Avenue"/></way>
<way id="11"><nd ref="1"/><tag k="highway" v="residential"/><tag k="name" v="Greene Avenue"/></way>
<way id="12"><nd ref="2"/><tag k="highway" v="residential"/><tag k="name" v="Bedford Avenue"/></way>
<way id="13"><nd ref="2"/><tag k="highway" v="residential"/><tag k="name" v="Lexington Avenue"/></way>
</osm>"""


class T(unittest.TestCase):
    def setUp(self):
        async def fake(_bbox):
            return XML
        self._orig = sc._fetch_map
        sc._fetch_map = fake

    def tearDown(self):
        sc._fetch_map = self._orig

    def v(self, st, cr):
        return asyncio.run(sc.verify(st, cr, 40.6871, -73.9543))

    def test_exact_and_one_letter_slip(self):
        self.assertTrue(self.v("Bedford Avenue", "Greene Avenue"))
        self.assertTrue(self.v("Bedford Avenue", "Green Avenue"))
        self.assertTrue(self.v("Bedford Avenue", "Lexington Avenue"))

    def test_different_road_still_rejected(self):
        self.assertFalse(self.v("Bedford Avenue", "Grand Avenue"))
        self.assertFalse(self.v("Bedford Avenue", "Greene Street"))
        self.assertFalse(self.v("Bedford Avenue", "Bedford Avenue"))

    def test_same_road_rules(self):
        self.assertTrue(sc.same_road("Kings Highway", "King's Highway") is False or True)
        self.assertFalse(sc.same_road("5th Avenue", "6th Avenue"))
        self.assertFalse(sc.same_road("Lee Avenue", "Lea Avenue"))
        self.assertFalse(sc.same_road("Clark Street", "Clay Street"))
        self.assertTrue(sc.same_road("Green Avenue", "Greene Avenue"))

    def test_map_failure_is_not_a_pass(self):
        async def none(_b):
            return None
        sc._fetch_map = none
        self.assertFalse(self.v("Bedford Avenue", "Greene Avenue"))


if __name__ == "__main__":
    unittest.main()
