import unittest
import detect
class Compound(unittest.TestCase):
    def test_medical_both_orders(self):
        for text in ['difficulty breathing, altered mental status','altered mental status and difficulty breathing']:
            self.assertEqual(detect.get_nature('female in her60s '+text+', ALS response','sullivan'),detect._addr_title(text))
    def test_flash_fire_with_gas_leak(self):
        self.assertEqual(detect.get_nature('Box0533,191ClintonStreet. We had a flash fire with a gas leak. Units are still investigating.','fdny'),'Flash Fire With a Gas Leak')
    def test_no_borrowing_between_jobs(self):
        h=detect.get_nature('difficulty breathing. Another job altered mental status','sullivan')
        self.assertEqual(h,'Difficulty Breathing')
    def test_negated_compound_not_promoted(self):
        for text,p in [('difficulty breathing, altered mental status','sullivan'),('flash fire with a gas leak','fdny')]:
            for prefix in ['no ','training ','drill ']:
                self.assertNotEqual(detect.get_nature(prefix+text,p),detect._addr_title(text))
