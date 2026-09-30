import unittest
import detect
class RouteNasal(unittest.TestCase):
    def test_nasal(self):
        self.assertEqual(detect.get_nature('Queens65Road108Street to check out a child nasal obstruction','hatzolah'),'Nasal Obstruction')
    def test_no_patient_not_promoted(self):
        self.assertNotEqual(detect.get_nature('equipment nasal obstruction','hatzolah'),'Nasal Obstruction')
    def test_primary_route_before_cross(self):
        text='Sullivan dispatch,Highland mutual aid to Lumberland,890 State Route 97,68-year-old female generally ill,BLS response.Cross of Short Tract Road.'
        h=detect.analyze(text,'zello-sullivan')
        self.assertEqual(h['address'],'890 State Route 97, Sullivan Co, NY')
        self.assertEqual(h['nature'],'Generally Ill')
    def test_route_not_invented(self):
        self.assertNotIn('890',str(detect.analyze('Sullivan dispatch Short Tract Road female generally ill BLS response','zello-sullivan')))

    def test_cross_route_not_primary(self):
        h=detect.analyze("Sullivan dispatch 75 Herschel Drive female generally ill BLS response cross 890 State Route 97", "zello-sullivan")
        self.assertEqual(h["address"], "75 Herschel Drive, Sullivan Co, NY")
