import unittest
from unittest.mock import patch
import detect
import main
from status import Stats
import tempfile

class PatientDetails(unittest.TestCase):
    phrase = 'Any units in the W for Gary between Harris and MRC for a 5-month-old difficulty breathing.'
    def test_infant_exact_fixture(self):
        h = detect.analyze(self.phrase, 'zello-hatzalah')
        self.assertEqual(h['patient_age'], '5-month-old')
        self.assertEqual(h['address'], 'Harris & Mrc, Brooklyn, NY')
        self.assertEqual(h['heard_location_evidence'], self.phrase)
        text = main.format_alert(h)
        self.assertIn('5-month-old', text)
        self.assertIn('_Hatzalah Dispatch_', text)
        self.assertNotIn('Gary', text)
    def test_adult_age(self):
        self.assertEqual(detect.patient_age('18-year-old with chest pain'), '18-year-old')
    def test_units_are_not_age(self):
        for s in ['W18 to Gary and Harrison', '908 respond', 'CH-51 on scene', '5 months until renewal']:
            self.assertEqual(detect.patient_age(s), '')
    def test_two_ages_not_paired(self):
        self.assertEqual(detect.patient_age('5-month-old difficulty breathing. 18-year-old fall.'), '')
    def test_review_evidence_saved(self):
        with tempfile.TemporaryDirectory() as p, patch.dict('os.environ', {'SEG_DIR': p}):
            st = Stats()
            st.mark_alert('zello-hatzalah','Difficulty Breathing','Harris & Mrc, Brooklyn, NY',False,failed=False,
                          patient_age='5-month-old',heard_location_evidence=self.phrase)
            import json
            saved=json.loads(st._hist_file.read_text())[0]
            self.assertEqual(saved['heard_location_evidence'],self.phrase)
            self.assertEqual(saved['patient_age'],'5-month-old')
