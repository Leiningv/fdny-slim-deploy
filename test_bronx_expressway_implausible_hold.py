import unittest
from unittest.mock import AsyncMock, Mock, patch
import main

CB = "40897 the Cross Bronx Expressway southbound at Jerome Avenue for auto accident."

class Holds(unittest.IsolatedAsyncioTestCase):
    async def _run(self, profile, hit):
        with patch.object(main.alert_waha, "send_text", new_callable=AsyncMock) as send:
            out = await main.verify_and_send(profile, hit, Mock())
        return out, send

    async def test_bronx_expressway_plain_street_held(self):
        h = {"nature": "Motor Vehicle Accident", "address": "Jerome Avenue, Brooklyn, NY", "dispatch_source_text": CB, "excerpt": CB}
        out, send = await self._run("fdny", h)
        self.assertEqual(out, "suppressed")
        self.assertIn("Bronx expressway", h["hold_reason"])
        send.assert_not_awaited()

    async def test_implausible_street_held(self):
        for a in ["Said the Road, Brooklyn, NY", "12 Said the Road, Brooklyn, NY"]:
            h = {"nature": "Accident", "address": a, "excerpt": "x"}
            out, send = await self._run("fdny", h)
            self.assertEqual(out, "suppressed")
            self.assertIn("not a plausible street", h["hold_reason"])
            send.assert_not_awaited()

    async def test_normal_not_caught(self):
        for p, h in [("fdny", {"address": "Cross Bronx Expressway, Bronx, NY", "dispatch_source_text": CB}),
                     ("zello-hatzalah", {"address": "Jerome Avenue, Bronx, NY", "dispatch_source_text": CB}),
                     ("fdny", {"address": "The Bowery, Manhattan, NY", "dispatch_source_text": "x"}),
                     ("fdny", {"address": "Avenue of the Americas, Manhattan, NY", "dispatch_source_text": "x"})]:
            h = dict(h, nature="Accident", excerpt="x")
            try:
                await self._run(p, h)
            except Exception:
                pass
            hr = h.get("hold_reason", "")
            self.assertNotIn("Bronx expressway", hr)
            self.assertNotIn("not a plausible street", hr)

if __name__ == "__main__":
    unittest.main()
