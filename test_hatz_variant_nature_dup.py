import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import main

P = "zello-hatzalah"
ADDR = "Queens Boulevard, Queens, NY"
# Real clips 10/3 8:09 PM EDT: the same fainting call was posted twice.
CLIP1 = "Queens unit on the Far Rock for Queens Boulevard and 69th Avenue, patient fainted."
CLIP2 = ("and the Queens unit, the Safari Hills for Queens Boulevard and 69th Avenue, "
         "patient fainted. 10903 no ALS required. That's code 124.")


def row(nature, address=ADDR, t=None, source=P):
    return {"t": time.time() - 90 if t is None else t, "nature": nature,
            "tokens": [], "address": address, "source": source}


class VariantNatureDup(unittest.TestCase):
    def test_real_queens_repeat_is_duplicate(self):
        hit = {"nature": "Fainting", "address": ADDR}
        self.assertTrue(main._variant_nature_repeat(P, hit, [row("fainted")], time.time()))

    def test_same_stem_other_direction(self):
        hit = {"nature": "Fainted", "address": ADDR}
        self.assertTrue(main._variant_nature_repeat(P, hit, [row("fainting")], time.time()))

    def test_different_address_not_duplicate(self):
        hit = {"nature": "Fainting", "address": "Queens Boulevard, Liberty, NY"}
        self.assertFalse(main._variant_nature_repeat(P, hit, [row("fainted")], time.time()))

    def test_different_nature_not_duplicate(self):
        hit = {"nature": "Chest Pain", "address": ADDR}
        self.assertFalse(main._variant_nature_repeat(P, hit, [row("fainted")], time.time()))

    def test_old_row_not_duplicate(self):
        hit = {"nature": "Fainting", "address": ADDR}
        self.assertFalse(main._variant_nature_repeat(P, hit, [row("fainted", t=time.time() - 700)], time.time()))

    def test_other_source_and_fdny_not_caught(self):
        hit = {"nature": "Fainting", "address": ADDR}
        self.assertFalse(main._variant_nature_repeat(P, hit, [row("fainted", source="zello-sullivan")], time.time()))
        self.assertFalse(main._variant_nature_repeat("fdny", hit, [row("fainted", source="fdny")], time.time()))

    def test_flow_holds_second_post(self):
        with tempfile.TemporaryDirectory() as d:
            rf = Path(d) / "recent.json"
            rf.write_text(json.dumps([row("fainted")]))
            hit = {"nature": "Fainting", "address": ADDR,
                   "dispatch_source_text": CLIP2, "excerpt": CLIP2}
            with patch.object(main, "RECENT_FILE", rf), \
                 patch.object(main.alert_waha, "send_text", new_callable=AsyncMock) as send:
                out = asyncio.run(main.verify_and_send(P, hit, Mock(), "x.wav"))
            send.assert_not_awaited()
        self.assertEqual(out, "suppressed")
        self.assertEqual(hit.get("hold_reason"), "dup incident")


if __name__ == "__main__":
    unittest.main()
