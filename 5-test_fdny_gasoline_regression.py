"""2775 East 16th Street regression: complaint must outrank dispatch prefix.

These tests intentionally expose the current production bug. They belong in
 the general pre-post audio verification build, not a standalone deployment.
"""
import unittest
import detect

VENDOR = ('Phone Alarm Box 3302, 2775 East 16th Street, Bell Parkway South, '
          'Hammonds Avenue, for an odor of gasoline. Phone Alarm Box 3302, '
          '2775 East 16th Street, Bell Parkway South, Hammonds Avenue, for an odor')
SECOND = ('Phone alarm box 3302, 2775 East 16th Street, Belt Parkway South to '
          'Emmons Avenue, for an odor of gasoline.')

class GasolineComplaint(unittest.TestCase):
    def test_correct_vendor_complaint_not_phone_alarm(self):
        hit = detect.analyze(VENDOR, 'fdny')
        self.assertEqual(hit['nature'], 'Odor of Gasoline')
        self.assertEqual(hit['box_heard'], '3302')
        self.assertEqual(hit['address'], '2775 East 16th Street, Brooklyn, NY')
    def test_second_reading_preserves_complaint_and_spoken_crosses(self):
        hit = detect.analyze(SECOND, 'fdny')
        self.assertEqual(hit['nature'], 'Odor of Gasoline')
        self.assertEqual(hit['box_heard'], '3302')
        self.assertEqual(hit['cross'], 'Belt Parkway South & Emmons Avenue')
    def test_negated_gasoline_not_positive_complaint(self):
        self.assertNotEqual(detect.get_nature('No odor of gasoline, returning to service', 'fdny'),
                            'Odor of Gasoline')
    def test_truck_fire_is_not_transmission_prefix(self):
        self.assertEqual(detect.get_nature('Phone alarm box 2688, Fort Hamilton Parkway for truck fire', 'fdny'), 'Truck Fire')
