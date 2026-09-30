import unittest
import detect
class StuckElevator(unittest.TestCase):
    def test_exact_phrase_not_flattened(self):
        t='All units in the W for Bedford and Flushing for a stuck occupied elevator. 101 head over to Bedford Flushing and Park.'
        self.assertEqual(detect.get_nature(t,'hatzolah'),'Stuck Occupied Elevator')
    def test_plain_elevator_unchanged(self):
        self.assertEqual(detect.get_nature('Bedford and Flushing elevator','hatzolah'),'Elevator')
