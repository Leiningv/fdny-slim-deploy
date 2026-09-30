import unittest
import detect

class AvenueLetterCorner(unittest.TestCase):
    def test_spoken_oscar(self):
        h=detect.analyze('Are there any units for West 11th and Avenue Oscar for a patient not feeling well?', 'zello-hatzalah')
        self.assertEqual(h['address'], 'West 11th Street & Avenue O, Brooklyn, NY')
        self.assertEqual(h['nature'], 'Not Feeling Well')
        self.assertTrue(h['directional_numbered_corner'])
        self.assertTrue(h['area_defaulted'])
    def test_untaught_letters_not_promoted(self):
        for word in ['Bravo','Echo','Foxtrot','Golf','Quebec','Zulu','Q','Z']:
            self.assertIsNone(detect._directional_numbered_corner('West 11th and Avenue '+word))
    def test_missing_conjunction_not_invented(self):
        self.assertIsNone(detect._directional_numbered_corner('West 11th Avenue O'))
