"""BK0977 actual vendor wording, owner alert and independent audio agree."""
import unittest
import detect

TEXT = ('Phone Alarm Box 977, 780 Washington Avenue, Sterling Place, the Park Place, '
        'reporting a fire in the kitchen of a restaurant. Phone Alarm Box 977, '
        '780 Washington Avenue, Sterling Place, the Park Place, reporting fire '
        'in the restaurant, in the kitchen.')

class KitchenRestaurant(unittest.TestCase):
    def test_preserve_actual_complaint(self):
        hit = detect.analyze(TEXT, 'fdny')
        self.assertEqual(hit['nature'], 'Fire in the Kitchen of a Restaurant')
        self.assertEqual(hit['address'], '780 Washington Avenue, Brooklyn, NY')
        self.assertEqual(hit['box_heard'], '0977')

    def test_preserve_clean_spoken_crosses(self):
        hit = detect.analyze(TEXT, 'fdny')
        self.assertEqual(hit['cross'], 'Sterling Place & Park Place')

if __name__ == '__main__':
    unittest.main()
