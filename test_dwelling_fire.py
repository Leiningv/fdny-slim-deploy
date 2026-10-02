import unittest
import detect

T = ("Phone Alarm Box 1853, 114 Crescent Street, atn the street to Danforth Street, "
     "fire in a dwelling. Phone Alarm Box 1853, 114 Crescent Street, atn the street to "
     "Danforth Street, fire in a dwelling.")


class DwellingFire(unittest.TestCase):
    def test_plain_dwelling_fire_is_a_nature(self):
        h = detect.analyze(T, 'fdny')
        self.assertEqual(h['nature'].lower(), 'fire in a dwelling')
        self.assertEqual(h['address'], '114 Crescent Street, Brooklyn, NY')

    def test_private_dwelling_unchanged(self):
        h = detect.analyze('Box 1853, 114 Crescent Street, fire in a private dwelling', 'fdny')
        self.assertEqual(h['nature'], 'Fire in a Private Dwelling')


if __name__ == '__main__':
    unittest.main()
