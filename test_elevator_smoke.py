import unittest
import detect,main
class ElevatorSmoke(unittest.TestCase):
    def test_actual_capture_both_reads(self):
        for tail in ['odor of smoke from the elevator','an odor of smoke, the elevator']:
            h=detect.analyze('Phone Alarm Box1483,4802 10th Avenue, south of 48th Street, '+tail+'.','fdny')
            self.assertEqual(h['nature'],'Odor of Smoke from the Elevator')
            text=main.format_alert(h);self.assertIn('ODOR OF SMOKE FROM THE ELEVATOR',text);self.assertNotIn('ELEVATOR FIRE',text)
    def test_ordinary_stuck_elevator_unchanged(self):
        self.assertEqual(detect.get_nature('4802 10th Avenue stuck occupied elevator.','fdny'),'Stuck Occupied Elevator')
    def test_negated_smoke_not_promoted(self):
        n=detect.get_nature('4802 10th Avenue no odor of smoke from the elevator.','fdny')
        self.assertNotIn('Odor of Smoke',n)
    def test_unrelated_smoke_not_attached(self):
        n=detect.get_nature('Elevator at4802 10th Avenue. Old job had odor of smoke at200 Henry Street.','fdny')
        self.assertNotEqual(n,'Odor of Smoke from the Elevator')
    def test_two_boxes_no_new_locality_claim(self):
        n=detect.get_nature('Box1483 elevator. Box1234 odor of smoke from the elevator.','fdny')
        self.assertNotEqual(n,'Odor of Smoke from the Elevator')
