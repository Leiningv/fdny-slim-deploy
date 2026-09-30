import unittest
import detect
import fdny_audio_gate
import audio_review

class ComplaintRetention(unittest.TestCase):
    def test_recorded_truck_fire(self):
        t='Alarm, Box 2973, 1678 East 3rd Street off Avenue O Avenue P, for fire in a sanitation truck. Brooklyn Box 2973, 1678 East 3rd Street off Avenue O and P, for fire in a truck.'
        a=detect.analyze(t,'fdny')
        self.assertEqual(a['nature'],'Fire in a Sanitation Truck')
        self.assertFalse(fdny_audio_gate.generic_nature_invariant(t,a['nature']))
        self.assertFalse(audio_review.complaint_lost(t,a['nature']))
        self.assertEqual(detect.get_nature('Box 2973 for fire in a truck','fdny'),'Fire in a Truck')

    def test_medical_alert_extension(self):
        t='For a medical alert activation, 123 Leans Road Extension, cross street Leans Road, 0752.'
        a=detect.analyze(t,'sullivan')
        self.assertEqual(a['nature'],'Medical Alert Activation')
        self.assertEqual(a['address'],'123 Leans Road Extension, Sullivan Co, NY')
        self.assertEqual(detect.get_nature('medical alert activation test','sullivan'),'')
        self.assertEqual(detect.get_nature('no medical alert activation','sullivan'),'')
        self.assertEqual(detect.get_nature('medical alert activation','hatzolah'),'')

    def test_mva_repeat_with_chatter(self):
        t='Windsor Hills Estates for Folsburgh-Woodridge automatic response. Amherst County 5262 VC3 your pay location. A priority response motor vehicle accident 5143 South Fallsburg Main Street near Brothers Pizza.'
        self.assertEqual(detect.analyze(t,'sullivan')['nature'],'Motor Vehicle Accident')
        self.assertEqual(detect.get_nature('Motor vehicle accident 5262','sullivan'),'')
        self.assertEqual(detect.get_nature('a priority response motor vehicle accident 5262 responding','sullivan'),'')

    def test_no_extension_invention_or_truck_chatter(self):
        self.assertNotIn('Extension',detect.analyze('medical alert activation 123 Leans Road','sullivan')['address'])
        self.assertNotEqual(detect.get_nature('Box 2973 training for fire in a sanitation truck','fdny'),'Fire in a Sanitation Truck')
        self.assertNotEqual(detect.get_nature('Box 2973 for no fire in a sanitation truck','fdny'),'Fire in a Sanitation Truck')

if __name__=='__main__':unittest.main()
