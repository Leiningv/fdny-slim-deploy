import time
import unittest

import main

ADDR = "545 Prospect Place, Brooklyn, NY"


def row(nature, apt, address=ADDR, t=None):
    return {"t": time.time() - 2 if t is None else t, "nature": nature, "tokens": [],
            "address": address, "source": "fdny", "apartment": apt}


class FdnyVariantDup(unittest.TestCase):
    def test_prospect_place_second_broadcast_held(self):
        hit = {"nature": "Smoke in Apartment", "apartment": "Apartment 5N", "address": ADDR}
        self.assertTrue(main._variant_nature_repeat("fdny", hit, [row("smoke", "Apartment 5N")], time.time()))

    def test_apartment_inside_nature_text(self):
        hit = {"nature": "Smoke in Apartment, Apartment 5N", "address": ADDR}
        self.assertTrue(main._variant_nature_repeat("fdny", hit, [row("smoke, apartment 5n", "")], time.time()))

    def test_upgrade_fire_to_working_fire_posts(self):
        hit = {"nature": "Working Fire", "apartment": "Apartment 5N", "address": ADDR}
        self.assertFalse(main._variant_nature_repeat("fdny", hit, [row("smoke", "Apartment 5N")], time.time()))

    def test_changed_nature_posts(self):
        hit = {"nature": "Fire in Apartment", "apartment": "Apartment 5N", "address": ADDR}
        self.assertFalse(main._variant_nature_repeat("fdny", hit, [row("smoke", "Apartment 5N")], time.time()))

    def test_different_apartment_posts(self):
        hit = {"nature": "Smoke", "apartment": "Apartment 6N", "address": ADDR}
        self.assertFalse(main._variant_nature_repeat("fdny", hit, [row("smoke", "Apartment 5N")], time.time()))

    def test_no_apartment_posts(self):
        hit = {"nature": "Smoke", "address": ADDR}
        self.assertFalse(main._variant_nature_repeat("fdny", hit, [row("smoke", "")], time.time()))

    def test_different_address_or_old_posts(self):
        hit = {"nature": "Smoke", "apartment": "Apartment 5N", "address": "1 Main St, Brooklyn, NY"}
        self.assertFalse(main._variant_nature_repeat("fdny", hit, [row("smoke", "Apartment 5N")], time.time()))
        hit = {"nature": "Smoke", "apartment": "Apartment 5N", "address": ADDR}
        self.assertFalse(main._variant_nature_repeat("fdny", hit, [row("smoke", "Apartment 5N", t=time.time()-700)], time.time()))
