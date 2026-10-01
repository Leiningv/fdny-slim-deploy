import json
from pathlib import Path
import unittest
import detect, audio_review

CASES = {r['case']:r for r in json.loads(Path(__file__).with_name('parser_recording_cases.json').read_text())}

class RecordingBatch(unittest.TestCase):
    def test_recorded_medical_words_and_house(self):
        expected = {'Kingston':'Patient Down From a Height','Cardiac':'Cardiac Problem',
                    'Renal':'Renal Colic','Lift':'Probably Just a Lift Assist','Liberty':'Fall'}
        for key,nature in expected.items():
            row=CASES[key];hit=detect.analyze(row['text'],row['feed'])
            self.assertEqual(hit['nature'],nature,key)
        self.assertEqual(detect.analyze(CASES['Liberty']['text'],'zello-sullivan')['address'],
                         '10 Liberty Commons Way, Liberty, NY')
    def test_new_medical_words_negation(self):
        for phrase,profile in [('patient down from a height','hatzolah'),('renal colic','hatzolah'),
                               ('probably just a lift assist','hatzolah'),('cardiac problem','sullivan')]:
            for prefix in ['no ','not ','training ','drill ']:
                self.assertNotEqual(detect.get_nature(prefix+phrase,profile),detect._addr_title(phrase))
    def test_way_mixed_addresses_stay_held(self):
        self.assertTrue(audio_review.mixed('10 Liberty Commons Way, fall. Another call, 20 Liberty Commons Way, seizure.','zello-sullivan'))
        self.assertIsNone(detect.analyze('Had an accident on the way.','zello-sullivan'))
    def test_pleasant_routing_only_exception(self):
        t=CASES['PleasantRouting3']['text']
        self.assertFalse(audio_review.mixed(t,'zello-sullivan'))
        for modified in [t+' Third call, 20 Pleasant Street, seizure.',
                         t+' New call at 20 Pleasant Street, seizure.',
                         t.replace('10 Pleasant Street','414 Broadway'),
                         t.replace('County 5262','County 9999')]:
            self.assertTrue(detect.sullivan_numbered_jobs(modified,'sullivan'))
        self.assertTrue(audio_review.mixed(t+' 20 Pleasant Street for seizure.','zello-sullivan'))
    def test_compactor_words_not_asr_global_rewrite(self):
        t='1077 Brooklyn box 421 191 Sands Street off of Gold Street. It is for a fire in a compactor.'
        self.assertEqual(detect.get_nature(t,'fdny'),'Fire in a Compactor')
        self.assertEqual(detect.get_nature('Box 421 191 Sand Street for compactor fire.','fdny'),'Compactor Fire')
        self.assertNotEqual(detect.get_nature('Box 421 191 Sand Street for no compactor fire.','fdny'),'Compactor Fire')
        self.assertEqual(detect.analyze(CASES['SandSaint']['text'],'fdny')['address'],'191 Saint Street, Brooklyn, NY')
    def test_unresolved_vendor_cases_unchanged(self):
        self.assertEqual(detect.analyze(CASES['Tooth']['text'],'zello-sullivan')['nature'],'')
        self.assertEqual(detect.analyze(CASES['Kent']['text'],'fdny')['cross'],'South 9 & South 10 Street')
