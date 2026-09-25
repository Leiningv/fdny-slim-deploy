"""Continuous Broadcastify ingest with zero blind spots.

One supervised ffmpeg per feed records the live stream CONTINUOUSLY and the
segment muxer slices it into overlapping WAV files on a rotating ring:

    ffmpeg -i <hlsUrl> -f segment -segment_time 20 -segment_wrap 6 hatzolah-%03d.wav

Because ffmpeg never stops between segments (unlike the old per-chunk
capture), no audio is lost between files. To keep a dispatch split across a
segment boundary detectable, the consumer transcribes adjacent PAIRS of
segments (pure-PCM concat), so every boundary appears mid-audio in one pair.
The supervisor restarts ffmpeg on drop with backoff and refreshes the
tokenized HLS URL periodically (tokens expire) and after repeated failures.

Stream access (verified 2026-09-25, kept from v1): audio.broadcastify.com
direct MP3 URLs need Premium, so we use the free web-player flow:
  1. POST login to https://www.broadcastify.com/login/ (cookie jar)
  2. GET https://www.broadcastify.com/listen/feed/<id>
  3. Extract the per-user tokenized `hlsUrl` from the page
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

SEG_SEC = int(os.environ.get("SEG_SECONDS", "20"))
SEG_WRAP = int(os.environ.get("SEG_WRAP", "6"))
FEEDS = {
    "hatzolah": os.environ.get("FEED_HATZOLAH", "7392"),
    "sullivan": os.environ.get("FEED_SULLIVAN", "32727"),
}
LOGIN_URL = "https://www.broadcastify.com/login/"
FEED_URL = "https://www.broadcastify.com/listen/feed/{}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
URL_TTL = 25 * 60  # refresh the tokenized URL at least this often


def ffmpeg_bin() -> str:
    import shutil
    sys_bin = shutil.which("ffmpeg")
    if sys_bin:
        return sys_bin
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("ffmpeg not found - install it or add imageio-ffmpeg")

def check_ffmpeg() -> None:
    ffmpeg_bin()


def _enc(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


def get_hls_url(feed_id: str) -> str:
    """Log in and return the tokenized HLS URL for a feed. Raises on failure.
    Pure Python (urllib + CookieJar) - no curl needed on the host."""
    import http.cookiejar
    import urllib.request

    user = os.environ.get("BROADCASTIFY_USER", "")
    pw = os.environ.get("BROADCASTIFY_PASS", "")
    if not user or not pw:
        raise RuntimeError("BROADCASTIFY_USER / BROADCASTIFY_PASS not set")
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA)]
    post_data = f"username={_enc(user)}&password={_enc(pw)}&action=auth&redirect=%2F".encode()
    try:
        op.open(LOGIN_URL, timeout=30).read()
        req = urllib.request.Request(LOGIN_URL, data=post_data,
                                     headers={"Referer": LOGIN_URL,
                                              "Content-Type": "application/x-www-form-urlencoded"})
        op.open(req, timeout=30).read()
        page = op.open(FEED_URL.format(feed_id), timeout=30).read().decode("utf-8", "replace")
    except Exception as e:
        raise RuntimeError(f"broadcastify login request failed: {e}")
    m = re.search(r'hlsUrl:\s*"((?:[^"\\]|\\.)*)"', page)
    if not m:
        raise RuntimeError("login failed or no hlsUrl on feed page")
    return m.group(1).replace("\\/", "/")


def run_ffmpeg(profile: str, url: str, seg_dir: Path) -> int:
    """Record continuously until ffmpeg exits. Returns its exit code."""
    pattern = str(seg_dir / f"{profile}-%03d.wav")
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", url,
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        "-f", "segment",
        "-segment_time", str(SEG_SEC),
        "-reset_timestamps", "1",
        "-segment_wrap", str(SEG_WRAP),
        "-y", pattern,
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, timeout=None)
    except KeyboardInterrupt:
        return 0
    except Exception as e:  # noqa: BLE001
        logging.warning("[%s] ffmpeg supervisor error: %s", profile, e)
        return -1
    tail = (proc.stderr or b"")[-300:].decode(errors="replace").strip()
    if tail:
        logging.warning("[%s] ffmpeg exited rc=%s: %s", profile, proc.returncode, tail)
    else:
        logging.warning("[%s] ffmpeg exited rc=%s", profile, proc.returncode)
    return proc.returncode


def supervisor(profile: str, seg_dir: Path, stats) -> None:
    """Keep one continuous segmented capture running forever (blocking)."""
    seg_dir.mkdir(parents=True, exist_ok=True)
    url, url_at = "", 0.0
    backoff = 5
    quick_exits = 0
    while True:
        now = time.time()
        if not url or (now - url_at) > URL_TTL or quick_exits >= 2:
            try:
                url = get_hls_url(FEEDS[profile])
                url_at = now
                quick_exits = 0
                logging.info("[%s] got fresh stream URL", profile)
                stats.event(profile, "stream-url refreshed")
            except Exception as e:  # noqa: BLE001
                logging.warning("[%s] stream login failed: %s", profile, e)
                stats.event(profile, f"stream login failed: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue
        stats.mark_ffmpeg_start(profile)
        started = time.time()
        run_ffmpeg(profile, url, seg_dir)
        stats.mark_ffmpeg_exit(profile)
        lived = time.time() - started
        quick_exits = quick_exits + 1 if lived < 60 else 0
        backoff = 5 if lived >= 60 else min(backoff * 2, 120)
        logging.warning("[%s] restarting capture in %ss (lived %.0fs)", profile, backoff, lived)
        time.sleep(backoff)


def ready_segments(profile: str, seg_dir: Path) -> list[Path]:
    """Segment files that ffmpeg has finished writing (all but the active one).

    The ring wraps, so completeness is decided by mtime: a file not modified
    in the last few seconds while a newer file exists is final.
    """
    now = time.time()
    files = [p for p in seg_dir.glob(f"{profile}-*.wav") if p.stat().st_size > 44]
    if len(files) < 2:
        return []
    newest_mtime = max(p.stat().st_mtime for p in files)
    done = [p for p in files if p.stat().st_mtime < newest_mtime - 1.0
            and now - p.stat().st_mtime > 2.0]
    return sorted(done, key=lambda p: p.stat().st_mtime)
