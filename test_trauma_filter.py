import unittest, detect
class T(unittest.TestCase):
    def test_only_full_trauma(self):
        for p in ('hatzolah','fdny'):
            for t in ('minor trauma','elderly trauma','trauma','traumatic trauma patient'):
                self.assertFalse(detect.get_nature('Any units for '+t+' on Main Street',p),t)
            self.assertEqual(detect.get_nature('Any units for full trauma on Main Street',p),'Full Trauma')
class Ave(unittest.TestCase):
    def test_lettered_avenue_keeps_letter(self):
        for t in ('Any units for Ocean Parkway and Avenue C unresponsive','Any units for Ocean Parkway and Avenue Charlie unresponsive'):
            self.assertEqual(detect.analyze(t,'hatzolah')['direct_cross_candidate'],'Avenue C')
class Sull(unittest.TestCase):
    def test_church_road_mountain_dale(self):
        for t in ("Dispatch to Mountain Dell. ALS response needed. 21 Church Road. 56-year-old female, hemorrhage.",
                  "Blade for Malletdale for 21 Church Road. A 56-year-old female hemorrhaging, ALS response."):
            h=detect.analyze(t,'sullivan')
            self.assertEqual(h['address'],'21 Church Road, Mountain Dale, NY')
            self.assertEqual(h['nature'],'Hemorrhage')
