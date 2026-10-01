"""Both owner-submitted misposts and safe pre-post veto cases."""
import unittest

import detect
from fdny_audio_gate import compare_weak_fdny, unclassified_fire_complaint

MONROE = ("Phone alarm box 880, 585 Monroe Street, 5th Avenue, Lewis Avenue, "
          "oven fire, 5 Adam. Phone alarm box 880, 585 Monroe Street, "
          "5th Avenue to Lewis Avenue, oven fire, apartment 5 Adam.")
E14 = ("Phone Alarm Box 2323, 1535 East 14th Street, O Ocean, a PD Paul, "
       "point fire in the balcony, 276. 10-4, Box 2323, 1535 East 14th "
       "Street, Avenue P, Paul, Avenue O Ocean, point fire in the balcony.")


class AudioGateTests(unittest.TestCase):
    def test_monroe_vendor_fire_cannot_post_as_phone_alarm(self):
        hit = detect.analyze(MONROE, "fdny")
        self.assertEqual(hit["nature"], "")  # Phone Alarm is never a nature; no-nature calls are held

    def test_east14_vendor_fire_cannot_post_as_phone_alarm(self):
        hit = detect.analyze(E14, "fdny")
        self.assertEqual(hit["nature"], "")
        self.assertEqual(hit["box_heard"], "2323")
        self.assertIsNone(hit["cross"])
        self.assertTrue(unclassified_fire_complaint(E14, "Fire Alarm"))

    def test_no_false_upgrade_from_alarm_or_negated_fire(self):
        for s in ("Phone Alarm Box 2427, 1409 New York Avenue, fire alarm activation",
                  "Phone Alarm Box 2427, 1409 New York Avenue, no oven fire reported"):
            h = detect.analyze(s, "fdny")
            self.assertFalse(unclassified_fire_complaint(s, h["nature"]), s)

    def test_same_job_confirmed_without_specific_fire(self):
        s = "Phone Alarm Box 2427, 1409 New York Avenue, apartment 6 George"
        h = detect.analyze(s, "fdny")
        self.assertEqual(compare_weak_fdny(h, s), "")
        self.assertIn("address", compare_weak_fdny(h, s.replace("1409", "1408")))
        self.assertIn("box", compare_weak_fdny(h, s.replace("Box 2427", "Box 2428")))
        self.assertIn("unavailable", compare_weak_fdny(h, ""))

class HandlerRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def _check_held(self, transcript):
        import tempfile
        from pathlib import Path
        from unittest.mock import AsyncMock, Mock, patch
        import main
        stats = Mock()
        with tempfile.TemporaryDirectory() as d:
            with (patch.object(main, "_fdny_fetch_clip", return_value=Path(d)/"clip.wav"),
                  patch.object(main, "_fdny_clip_sanity", return_value=""),
                  patch.object(main, "_archive_clip"), patch.object(main, "_save_seen"),
                  patch.object(main, "_kw_check", new_callable=AsyncMock),
                  patch.object(main, "_held_recording", new_callable=AsyncMock, return_value=""),
                  patch.object(main, "_post_held_review", new_callable=AsyncMock),
                  patch.object(main, "_append_alert_log"), patch.object(main, "_fdny_call_record"),
                  patch.object(main, "ops_log"), patch.object(main, "verify_and_send",
                               new_callable=AsyncMock) as sender):
                await main._fdny_handle_call({"id":"specific-fire","transcription":transcript,
                                              "audio_url":"https://example.invalid/x"},
                                             stats, {}, Path(d))
        sender.assert_not_awaited()
        self.assertIn("specific fire complaint", stats.mark_alert.call_args.kwargs["reason"])

    async def _never_sent(self, transcript):
        # Phone Alarm is no longer a nature: the call has no nature and is held.
        from unittest.mock import AsyncMock, Mock, patch
        import main
        h = detect.analyze(transcript, "fdny")
        with patch.object(main.alert_waha, "send_text", new_callable=AsyncMock) as send, patch.object(main, "ops_log"):
            out = await main.verify_and_send("fdny", h, Mock(), source_call={"transcription": transcript})
        self.assertEqual(out, "suppressed"); send.assert_not_awaited()

    async def test_monroe_handler_holds(self):
        await self._never_sent(MONROE)

    async def test_east14_handler_holds(self):
        await self._never_sent(E14)
