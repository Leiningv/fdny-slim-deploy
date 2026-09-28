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
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import alert_waha
import detect
import ingest
import transcribe
import zello_ingest
from status import ARCHIVE_DIR, ARCHIVE_KEEP, Stats, keepalive, start_web

NY = ZoneInfo("America/New_York")
DEDUP_SEC = int(os.environ.get("DEDUP_SECONDS", str(30 * 60)))
SEG_DIR = Path(os.environ.get("SEG_DIR", "./segments"))
SEEN_FILE = Path(os.environ.get("SEEN_FILE", "./segments/seen.json"))
FDNY_INBOX = SEG_DIR / "fdny_inbox.jsonl"
FDNY_IDS = SEG_DIR / "fdny_ids.json"

SOURCE_LABEL = {"hatzolah": "Hatzolah Brooklyn", "sullivan": "Sullivan Co Fire/EMS",
                "fdny": "FDNY Brooklyn Dispatch"}


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



GEOCODE_VERIFY = os.environ.get("GEOCODE_VERIFY", "1") != "0"


_GEOCODE_ABBREV = {"Ave": "Avenue", "St": "Street", "Rd": "Road", "Blvd": "Boulevard",
                   "Pkwy": "Parkway", "Dr": "Drive", "Ln": "Lane", "Ct": "Court", "Pl": "Place"}


def _geocode_variants(addr: str, profile: str) -> list[str]:
    """Query rewrites: expand abbreviations; '14th Ave between 50th & 51st St' ->
    '14th Avenue & 51st Street'; locality hints per feed."""
    base = addr if ", NY" in addr else f"{addr}, NY"
    street, _, tail = base.partition(",")
    for a, b in _GEOCODE_ABBREV.items():
        street = re.sub(rf"\b{a}\b", b, street)
    import re as _re
    m = _re.search(r"(.+?)\s+between\s+(.+?)\s*&\s*(.+)", street)
    variants = []
    if m:
        variants.append(f"{m.group(1).strip()} & {m.group(3).strip()}{',' + tail if tail else ''}")
        variants.append(f"{m.group(1).strip()} & {m.group(2).strip()}{',' + tail if tail else ''}")
    variants.append(street + ("," + tail if tail else ""))
    if profile == "sullivan":
        variants.append(f"{street}, Sullivan County, NY")
        variants.append(f"{street}, Monticello, NY")
    return [v for i, v in enumerate(variants) if v not in variants[:i]]


async def _nominatim(q: str):
    import urllib.parse
    import aiohttp
    url = ("https://nominatim.openstreetmap.org/search?" +
           urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "addressdetails": 1}))
    try:
        async with aiohttp.ClientSession(
                headers={"User-Agent": "fdny-slim/1.0 dispatch monitor"}) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                return await r.json()
    except Exception:  # noqa: BLE001
        return None


async def geocode_verify(addr: str, profile: str = "") -> tuple[bool, bool]:
    """Verify an address against OpenStreetMap Nominatim (free, no key).
    Returns (verified, in_sullivan_county). Fails open as (False, False)."""
    for q in _geocode_variants(addr, profile):
        res = await _nominatim(q)
        if res is None:
            return False, False  # network/API failure: don't burn retries
        if res:
            disp = str(res[0].get("display_name", ""))
            county = str((res[0].get("address") or {}).get("county", ""))
            return True, ("Sullivan" in county or "Sullivan County" in disp)
        await asyncio.sleep(1.1)  # nominatim 1 req/s
    return False, False


async def verify_and_send(profile: str, hit: dict, stats, clip_name: str | None = None) -> str:
    """User's posting rules (9/28): verified addresses only; Sullivan feed posts
    only Sullivan-County-verified addresses; unverifiable posts marked not confirmed.
    Returns 'sent' | 'queued' | 'suppressed'."""
    text_out = format_alert(hit)
    if GEOCODE_VERIFY:
        verified, in_sullivan = await geocode_verify(hit["address"], profile)
        if profile == "sullivan" and verified and not in_sullivan:
            logging.info("[%s] suppressed (verified outside Sullivan Co): %s", profile, hit["address"])
            stats.event(profile, f"suppressed (outside Sullivan Co): {hit['nature']} @ {hit['address']}")
            return "suppressed"
        if not verified:
            text_out = text_out.replace(hit["address"], hit["address"] + " (not confirmed)", 1)
            stats.event(profile, f"unconfirmed address: {hit['address']}")
    if clip_name:
        base = os.environ.get("RENDER_EXTERNAL_URL", "https://fdny-slim.onrender.com").rstrip("/")
        ok = await alert_waha.send_file(text_out, f"{base}/audio/{clip_name}", clip_name)
        if not ok:
            ok = await alert_waha.send_text(text_out)
    else:
        ok = await alert_waha.send_text(text_out)
    return "sent" if ok else "queued"


def format_alert(hit: dict) -> str:
    now = datetime.now(NY).strftime("%-m/%-d %-I:%M %p")
    label = SOURCE_LABEL.get(hit["source"], hit["source"])
    priority = "\N{POLICE CARS REVOLVING LIGHT} PRIORITY — " if hit.get("priority") else ""
    return (
        f"{priority}\N{FIRE} {hit['nature']} — {label}\n"
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
            outcome = await verify_and_send(profile, hit, stats, clip_name)
            ok = outcome == "sent"
            stats.mark_alert(profile, hit["nature"], hit["address"], ok)
            _append_alert_log({"t": now, "feed": profile, "nature": hit["nature"],
                               "address": hit["address"], "sent": ok,
                               "excerpt": hit["excerpt"]})
            logging.info("[%s] ALERT %s @ %s - sent=%s", profile, hit["nature"], hit["address"], ok)
        await asyncio.sleep(2)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return default


def _fdny_fetch_clip(url: str, m4a: Path, wav: Path) -> Path | None:
    """Download one Calls audio file and convert to 16kHz mono WAV."""
    import subprocess
    import urllib.request
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "fdny-slim/1.0",
                          "Referer": "https://www.broadcastify.com/calls/"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 500:
            return None
        m4a.write_bytes(data)
        rc = subprocess.call([
            ingest.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(m4a), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
        if rc != 0 or not wav.exists():
            return None
        return wav
    except Exception as e:  # noqa: BLE001
        logging.warning("[fdny] clip fetch failed: %s", e)
        return None


async def _fdny_handle_call(call: dict, stats: Stats, seen: dict, tmp: Path) -> None:
    stats.mark_segment("fdny")
    cid = str(call.get("id") or call.get("filename") or int(time.time()))
    text = (call.get("transcription") or "").strip()
    wav = None
    url = call.get("audio_url") or ""
    if url:
        tmp.mkdir(parents=True, exist_ok=True)
        wav = await asyncio.to_thread(_fdny_fetch_clip, url, tmp / f"{cid}.m4a", tmp / f"{cid}.wav")
    if not text and wav is not None:
        text = await asyncio.to_thread(transcribe.transcribe, wav)
    if not text:
        stats.event("fdny", "call with no transcription - detect skipped")
        return
    stats.mark_transcript("fdny", text)
    logging.info("[fdny] heard: %s", text[:160])
    if wav is not None:
        clip_name = f"fdny-{int(time.time())}.wav"
        await asyncio.to_thread(_archive_clip, wav, clip_name)
        stats.mark_clip("fdny", clip_name, text)
    for suffix in (".m4a", ".wav"):
        try:
            (tmp / f"{cid}{suffix}").unlink()
        except Exception:  # noqa: BLE001
            pass
    hit = detect.analyze(text, "fdny")
    if not hit:
        return
    key = f"fdny|{hit['nature']}|{hit['address']}"
    now = time.time()
    if now - seen.get(key, 0) < DEDUP_SEC:
        logging.info("[fdny] deduped: %s @ %s", hit["nature"], hit["address"])
        stats.event("fdny", f"deduped: {hit['nature']} @ {hit['address']}")
        return
    seen[key] = now
    _save_seen(seen)
    outcome = await verify_and_send("fdny", hit, stats, clip_name)
    ok = outcome == "sent"
    stats.mark_alert("fdny", hit["nature"], hit["address"], ok)
    _append_alert_log({"t": now, "feed": "fdny", "nature": hit["nature"],
                       "address": hit["address"], "sent": ok,
                       "excerpt": hit["excerpt"]})
    logging.info("[fdny] ALERT %s @ %s - sent=%s", hit["nature"], hit["address"], ok)


async def fdny_consumer(stats: Stats, seen: dict) -> None:
    """Process FDNY Calls pushed by the off-box poller.

    www.broadcastify.com refuses Render egress, so the Calls poll/login runs
    in the sandbox relay (same as the HLS URL relay) and POSTs new calls to
    /fdny_calls, which appends them to FDNY_INBOX. The call AUDIO lives on
    the calls CDN, which Render can reach, so clips are downloaded here.
    Server-side transcription rides along free with each call; the local
    whisper is only the fallback. From here on it is the exact same
    detect -> 30-min dedup -> WAHA -> status-page path as the live feeds.
    """
    ids: dict = _load_json(FDNY_IDS, {})
    offset = 0
    tmp = SEG_DIR / "fdny_tmp"
    while True:
        try:
            if FDNY_INBOX.exists():
                size = FDNY_INBOX.stat().st_size
                if size < offset:
                    offset = 0
                if size > offset:
                    with FDNY_INBOX.open("r") as fh:
                        fh.seek(offset)
                        chunk = fh.read()
                        offset = fh.tell()
                    for line in chunk.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            call = json.loads(line)
                        except Exception:  # noqa: BLE001
                            continue
                        cid = str(call.get("id") or call.get("filename") or "")
                        if not cid or cid in ids:
                            continue
                        now = time.time()
                        ids = {k: v for k, v in ids.items() if now - v < 48 * 3600}
                        ids[cid] = now
                        try:
                            FDNY_IDS.write_text(json.dumps(ids))
                        except Exception:  # noqa: BLE001
                            pass
                        await _fdny_handle_call(call, stats, seen, tmp)
        except Exception as e:  # noqa: BLE001
            logging.warning("[fdny] consumer error: %s", e)
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
    hls_profiles = [] if os.environ.get("HLS_DISABLED", "1") == "1" else list(ingest.FEEDS)
    # legacy broadcastify HLS is 403-blocked from Render egress and replaced by
    # the Zello listener; set HLS_DISABLED=0 to re-enable
    for profile in hls_profiles:
        loop.run_in_executor(None, ingest.supervisor, profile, SEG_DIR, stats)
    for profile in zello_ingest.CHANNELS:
        loop.run_in_executor(None, zello_ingest.supervisor, profile, SEG_DIR, stats)
    stats.mark_ffmpeg_start("fdny")  # push-driven capture; keeps the card honest
    stats.event("fdny", "calls ingest armed (sandbox poller -> /fdny_calls)")
    seen = _load_seen()
    logging.info("monitoring feeds: %s", ", ".join(f"{p}={fid}" for p, fid in ingest.FEEDS.items()))
    await start_web(stats)
    await asyncio.gather(
        *(consumer(p, stats, seen) for p in hls_profiles),
        *(consumer(p, stats, seen) for p in zello_ingest.CHANNELS),
        fdny_consumer(stats, seen),
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
