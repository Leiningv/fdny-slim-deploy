"""fdny-slim - free-only dispatch monitor, rebuilt and operated by Instinct.

    Broadcastify live audio (continuous, overlapped segments)
      -> faster-whisper (local, energy-gated)
      -> detect (emergency? address?)
      -> WhatsApp (WAHA)

One capture supervisor + one consumer per feed. Alerts deduped for 30 minutes
(persisted to disk, best-effort across restarts). Status/health web server and
self-keepalive run alongside. Timestamps in America/New_York. No paid APIs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import alert_waha
import detect
import ingest
import transcribe
from status import ARCHIVE_DIR, ARCHIVE_KEEP, Stats, keepalive, start_web

NY = ZoneInfo("America/New_York")
DEDUP_SEC = int(os.environ.get("DEDUP_SECONDS", str(30 * 60)))
SEG_DIR = Path(os.environ.get("SEG_DIR", "./segments"))
SEEN_FILE = Path(os.environ.get("SEEN_FILE", "./segments/seen.json"))

SOURCE_LABEL = {"hatzolah": "Hatzolah Brooklyn", "sullivan": "Sullivan Co Fire/EMS"}


def _load_env_file(path: Path = Path("config.env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


ALERTS_LOG = SEG_DIR / "alerts.jsonl"


def _archive_clip(src: Path, name: str) -> None:
    """Keep a copy of a speech segment for the status page; prune per feed."""
    try:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copyfile(src, ARCHIVE_DIR / name)
    except Exception as e:  # noqa: BLE001
        logging.warning("clip archive failed: %s", e)
        return
    try:
        profile = name.rsplit("-", 1)[0]
        clips = sorted(ARCHIVE_DIR.glob(f"{profile}-*.wav"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for old in clips[ARCHIVE_KEEP:]:
            old.unlink()
    except Exception:  # noqa: BLE001
        pass


def _append_alert_log(entry: dict) -> None:
    try:
        SEG_DIR.mkdir(parents=True, exist_ok=True)
        with ALERTS_LOG.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _load_seen() -> dict:
    try:
        data = json.loads(SEEN_FILE.read_text())
        now = time.time()
        return {k: v for k, v in data.items() if now - v < DEDUP_SEC}
    except Exception:  # noqa: BLE001
        return {}


def _save_seen(seen: dict) -> None:
    try:
        SEG_DIR.mkdir(parents=True, exist_ok=True)
        SEEN_FILE.write_text(json.dumps(seen))
    except Exception as e:  # noqa: BLE001
        logging.warning("seen save failed: %s", e)


def format_alert(hit: dict) -> str:
    now = datetime.now(NY).strftime("%-m/%-d %-I:%M %p")
    label = SOURCE_LABEL.get(hit["source"], hit["source"])
    return (
        f"\N{FIRE} {hit['nature']} — {label}\n"
        f"\N{ROUND PUSHPIN} {hit['address']}\n"
        f"\N{CLOCK FACE ONE OCLOCK} {now} ET\n"
        f'"{hit["excerpt"]}"'
    )


def _concat_pcm(a: Path, b: Path, out: Path) -> bool:
    """Concat two 16kHz mono pcm_s16le WAVs into one. Pure stdlib."""
    import wave
    try:
        with wave.open(str(a), "rb") as wa, wave.open(str(b), "rb") as wb:
            frames = wa.readframes(wa.getnframes()) + wb.readframes(wb.getnframes())
        with wave.open(str(out), "wb") as wo:
            wo.setnchannels(1)
            wo.setsampwidth(2)
            wo.setframerate(16000)
            wo.writeframes(frames)
        return True
    except Exception as e:  # noqa: BLE001
        logging.warning("concat failed: %s", e)
        return False


async def consumer(profile: str, stats: Stats, seen: dict) -> None:
    """Pick up finished segments for one feed, transcribe pairs, detect, alert.

    Transcribing the adjacent pair (prev+current) puts every segment boundary
    mid-audio in one of the pairs, so a dispatch split across a boundary is
    still captured whole. The RMS gate on both halves keeps silent periods
    free; the 30-min dedup absorbs the intentional 2x coverage.
    """
    processed: dict[str, float] = {}  # name -> mtime already handled
    prev: Path | None = None
    pair_out = SEG_DIR / f"pair-{profile}.wav"
    while True:
        for wav in ingest.ready_segments(profile, SEG_DIR):
            mtime = wav.stat().st_mtime
            if processed.get(wav.name) == mtime:
                continue
            processed[wav.name] = mtime
            if len(processed) > ingest.SEG_WRAP * 2:
                for name in list(processed):
                    if not (SEG_DIR / name).exists():
                        processed.pop(name, None)
            stats.mark_segment(profile)
            level = transcribe.rms(wav)
            if level < transcribe.RMS_MIN and (prev is None or transcribe.rms(prev) < transcribe.RMS_MIN):
                stats.mark_silence(profile)
                prev = wav
                continue
            target = wav
            if prev is not None and _concat_pcm(prev, wav, pair_out):
                target = pair_out
            prev = wav
            text = await asyncio.to_thread(transcribe.transcribe, target)
            if not text:
                continue
            stats.mark_transcript(profile, text)
            logging.info("[%s] heard: %s", profile, text[:160])
            clip_name = f"{profile}-{int(time.time())}.wav"
            await asyncio.to_thread(_archive_clip, target, clip_name)
            stats.mark_clip(profile, clip_name, text)
            hit = detect.analyze(text, profile)
            if not hit:
                continue
            key = f"{profile}|{hit['nature']}|{hit['address']}"
            now = time.time()
            if now - seen.get(key, 0) < DEDUP_SEC:
                logging.info("[%s] deduped: %s @ %s", profile, hit["nature"], hit["address"])
                stats.event(profile, f"deduped: {hit['nature']} @ {hit['address']}")
                continue
            seen[key] = now
            _save_seen(seen)
            ok = await alert_waha.send_text(format_alert(hit))
            stats.mark_alert(profile, hit["nature"], hit["address"], ok)
            _append_alert_log({"t": now, "feed": profile, "nature": hit["nature"],
                               "address": hit["address"], "sent": ok,
                               "excerpt": hit["excerpt"]})
            logging.info("[%s] ALERT %s @ %s - sent=%s", profile, hit["nature"], hit["address"], ok)
        await asyncio.sleep(2)


async def waha_watch(stats: Stats) -> None:
    while True:
        stats.waha_status = await alert_waha.check_session()
        await asyncio.sleep(300)


async def amain() -> None:
    _load_env_file()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    ingest.check_ffmpeg()
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("BROADCASTIFY_USER"):
        logging.warning("BROADCASTIFY_USER not set - streams will refuse the connection")

    stats = Stats()
    try:
        if ALERTS_LOG.exists():
            for line in ALERTS_LOG.read_text().splitlines()[-100:]:
                a = json.loads(line)
                if time.time() - a.get("t", 0) < 7 * 86400:
                    stats.alerts.append({"t": a["t"], "feed": a["feed"], "nature": a["nature"],
                                         "address": a["address"], "sent": a.get("sent", True)})
            stats.alerts_sent = sum(1 for a in stats.alerts if a["sent"])
    except Exception as e:  # noqa: BLE001
        logging.warning("alert log restore failed: %s", e)
    stats.waha_status = await alert_waha.check_session()
    logging.info("WAHA session status: %s", stats.waha_status)
    if not alert_waha.configured():
        logging.warning("WAHA not fully configured - alerts will fail until WAHA_URL/API_KEY/CHAT_ID are set")

    loop = asyncio.get_running_loop()
    for profile in ingest.FEEDS:
        loop.run_in_executor(None, ingest.supervisor, profile, SEG_DIR, stats)
    seen = _load_seen()
    logging.info("monitoring feeds: %s", ", ".join(f"{p}={fid}" for p, fid in ingest.FEEDS.items()))
    await start_web(stats)
    await asyncio.gather(
        *(consumer(p, stats, seen) for p in ingest.FEEDS),
        keepalive(stats),
        waha_watch(stats),
    )


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        logging.info("stopped")


if __name__ == "__main__":
    main()
