import unittest
import detect
import audio_review
import fdny_audio_gate

class TruckBroadway(unittest.TestCase):
    def test_recorded_reversed_truck(self):
        t='Box 728, Troutman Street at Bushwick Avenue for a truck on fire. Box 728, Troutman Street at Bushwick Avenue for a truck on fire.'
        a=detect.analyze(t,'fdny')
        self.assertEqual(a['nature'],'Truck on Fire')
        self.assertFalse(audio_review.complaint_lost(t,a['nature']))
        self.assertFalse(fdny_audio_gate.generic_nature_invariant(t,a['nature']))

    def test_no_reversed_truck_inference(self):
        for t in ['training for a truck on fire','for no truck on fire','truck on fire engine 271','for a truck not on fire']:
            self.assertNotEqual(detect.get_nature(t,'fdny'),'Truck on Fire')

    def test_recorded_liberty_broadway(self):
        t='Second call, the Village of Monticello, Liberty Street and Broadway for the motor vehicle accident. Team4 Rock Hill mutually2 empress for a call in Monticello, Liberty Street and Broadway.'
        a=detect.analyze(t,'sullivan')
        self.assertEqual(a['nature'],'Motor Vehicle Accident')
        self.assertEqual(a['address'],'Liberty Street & Broadway, Monticello, NY')
        self.assertIsNone(a['cross'])
        self.assertEqual(detect.analyze(t,'zello-sullivan')['address'],a['address'])

    def test_no_broadway_join_without_separator(self):
        a=detect.analyze('Monticello Liberty Street responding Broadway for motor vehicle accident','sullivan')
        self.assertNotIn('& Broadway',a['address'])
        a=detect.analyze('Monticello Liberty Street for motor vehicle accident','sullivan')
        self.assertNotIn('Broadway',a['address'])

if __name__=='__main__':unittest.main()
