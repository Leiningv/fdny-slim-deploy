import unittest
from unittest.mock import AsyncMock, Mock, patch
import main

class ImplausibleStreetSuffixes(unittest.IsolatedAsyncioTestCase):
    async def _run(self, addr):
        h = {"nature": "Accident", "address": addr, "excerpt": "x"}
        with patch.object(main.alert_waha, "send_text", new_callable=AsyncMock) as send:
            try:
                out = await main.verify_and_send("fdny", h, Mock())
            except Exception:
                out = None
        return out, h, send

    async def test_verb_the_suffix_held(self):
        for a in ["Shut the Highway, Brooklyn, NY", "Said the Road, Brooklyn, NY", "Shut the Hwy, Brooklyn, NY",
                  "Hold the Parkway, Brooklyn, NY", "Close the Expressway, Brooklyn, NY", "Take the Boulevard, Brooklyn, NY"]:
            out, h, send = await self._run(a)
            self.assertEqual(out, "suppressed", a)
            self.assertIn("not a plausible street", h["hold_reason"])
            send.assert_not_awaited()

    async def test_real_names_not_caught(self):
        for a in ["The Bowery, Manhattan, NY", "Avenue of the Americas, Manhattan, NY", "123 Ocean Parkway, Brooklyn, NY",
                  "Shore Parkway, Brooklyn, NY", "Belt Parkway, Brooklyn, NY"]:
            out, h, send = await self._run(a)
            self.assertNotIn("not a plausible street", h.get("hold_reason", ""), a)

if __name__ == "__main__":
    unittest.main()
