import unittest
from unittest.mock import patch
import sullivan_colonies as s
import main

LABEL='425, Old Falls Road, Village of Woodridge, Town of Fallsburg, Sullivan County, New York, 12789, United States'
class ExactSiteTests(unittest.TestCase):
    def test_long_and_compact(self):
        for label in (LABEL,'425 Old Falls Road, Woodridge, NY'):
            r=s.match_colony_for_verified_point(label,41.7142452,-74.5842268)
            self.assertTrue(r.found)
            self.assertEqual(r.colony_name,'Ridgewood Estates-Menorah Bungalows')
    def test_no_weak_matches(self):
        for label in ('426 Old Falls Road, Woodridge, NY','425 Old Fall Road, Woodridge, NY','425 Old Falls Road, Fallsburg, NY','425 Old Falls Road, Woodridge, NJ','425 Old Falls Road'):
            self.assertFalse(s.match_colony_for_verified_point(label,41.7142452,-74.5842268).found)
        for lat,lon in ((None,None),(41,-74),(float('nan'),-74)):
            self.assertFalse(s.match_colony_for_verified_point(LABEL,lat,lon).found)
    def test_ambiguous(self):
        row=next(r for r in s._COLONY_ADDRESS_ENTRIES if r['colony_name']=='Ridgewood Estates-Menorah Bungalows')
        with patch.object(s,'_COLONY_ADDRESS_ENTRIES',[row,dict(row,colony_name='Another label')]):
            self.assertFalse(s.match_colony_for_verified_point(LABEL,41.7142452,-74.5842268).found)
    def test_layout(self):
        h={'nature':'Activated Fire Alarm','address':'425 Old Falls Road, Woodridge, NY','source':'sullivan','verified_area':'Village of Woodridge'}
        text=main.format_alert(h,footer='Ridgewood Estates-Menorah Bungalows',crosses='Heard Road')
        self.assertIn('📍 *425 Old Falls Road, Woodridge*\nRidgewood Estates-Menorah Bungalows\nC/s Heard Road',text)
        self.assertIn('_Sullivan FD_',text)
