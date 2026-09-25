"""Standalone status page + health/status API + self-keepalive.

This is the "verifiably running" piece - its own URL, real data only:
  GET /health  -> 200 plain "ok" (host health checks, uptime pingers)
  GET /status  -> JSON: uptime, per-feed ingest/transcription/alert counters
                  and ages, WAHA session state, alert log, recent events
  GET /        -> standalone status page: alive state, per-feed table,
                  job/alert log, playable audio of recent feed captures
  GET /audio/<file> -> archived audio of recent speech captures

The keepalive task pings our own external URL every few minutes so a free
Render web service never idles into sleep.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path

from aiohttp import web

STARTED_AT = time.time()
ARCHIVE_DIR = Path(os.environ.get("ARCHIVE_DIR", "./segments/archive"))
ARCHIVE_KEEP = int(os.environ.get("ARCHIVE_KEEP", "10"))  # clips per feed


class Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.feeds: dict[str, dict] = {}
        self.events: deque = deque(maxlen=60)
        self.alerts: deque = deque(maxlen=100)
        self.clips: deque = deque(maxlen=ARCHIVE_KEEP * 4)
        self.alerts_sent = 0
        self.alerts_failed = 0
        self.waha_status = "unknown"
        self.git_commit = os.environ.get("RENDER_GIT_COMMIT", "")[:7] or os.environ.get("GIT_COMMIT", "")[:7]

    def feed(self, name: str) -> dict:
        return self.feeds.setdefault(name, {
            "ffmpeg_running_since": None, "ffmpeg_restarts": 0,
            "segments_seen": 0, "segments_silence_skipped": 0,
            "transcripts": 0, "last_segment_at": None, "last_transcript_at": None,
            "last_transcript": "", "last_alert_at": None, "last_alert": "",
        })

    def mark_ffmpeg_start(self, profile: str) -> None:
        with self._lock:
            f = self.feed(profile)
            if f["ffmpeg_running_since"] is not None:
                f["ffmpeg_restarts"] += 1
            f["ffmpeg_running_since"] = time.time()

    def mark_ffmpeg_exit(self, profile: str) -> None:
        with self._lock:
            self.feed(profile)["ffmpeg_running_since"] = None

    def event(self, profile: str, msg: str) -> None:
        with self._lock:
            self.events.appendleft({"t": time.time(), "feed": profile, "msg": msg[:300]})

    def mark_segment(self, profile: str) -> None:
        with self._lock:
            f = self.feed(profile)
            f["segments_seen"] += 1
            f["last_segment_at"] = time.time()

    def mark_silence(self, profile: str) -> None:
        with self._lock:
            self.feed(profile)["segments_silence_skipped"] += 1

    def mark_transcript(self, profile: str, text: str) -> None:
        with self._lock:
            f = self.feed(profile)
            f["transcripts"] += 1
            f["last_transcript_at"] = time.time()
            f["last_transcript"] = text[:280]
            self.events.appendleft({"t": time.time(), "feed": profile, "msg": "heard: " + text[:240]})

    def mark_clip(self, profile: str, filename: str, transcript: str) -> None:
        with self._lock:
            self.clips.appendleft({"t": time.time(), "feed": profile,
                                   "file": filename, "transcript": transcript[:200]})

    def mark_alert(self, profile: str, nature: str, address: str, ok: bool) -> None:
        with self._lock:
            f = self.feed(profile)
            f["last_alert_at"] = time.time()
            f["last_alert"] = f"{nature} @ {address}"
            if ok:
                self.alerts_sent += 1
            else:
                self.alerts_failed += 1
            self.alerts.appendleft({"t": time.time(), "feed": profile,
                                    "nature": nature, "address": address, "sent": ok})
            self.events.appendleft({"t": time.time(), "feed": profile,
                                    "msg": f"ALERT sent={ok}: {nature} @ {address}"})

    @staticmethod
    def _age(ts):
        return None if ts is None else round(time.time() - ts, 1)

    def snapshot(self) -> dict:
        with self._lock:
            feeds = {}
            for name, f in self.feeds.items():
                feeds[name] = {
                    "ffmpeg_running": f["ffmpeg_running_since"] is not None,
                    "ffmpeg_restarts": f["ffmpeg_restarts"],
                    "segments_seen": f["segments_seen"],
                    "segments_silence_skipped": f["segments_silence_skipped"],
                    "transcripts": f["transcripts"],
                    "last_segment_age_sec": self._age(f["last_segment_at"]),
                    "last_transcript_age_sec": self._age(f["last_transcript_at"]),
                    "last_transcript": f["last_transcript"],
                    "last_alert_age_sec": self._age(f["last_alert_at"]),
                    "last_alert": f["last_alert"],
                }
            return {
                "service": "fdny-slim",
                "operator": "Instinct",
                "up": True,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(STARTED_AT)),
                "uptime_sec": round(time.time() - STARTED_AT, 1),
                "git_commit": self.git_commit,
                "waha_session": self.waha_status,
                "alerts_sent": self.alerts_sent,
                "alerts_failed": self.alerts_failed,
                "feeds": feeds,
                "alert_log": [
                    {"age_sec": self._age(a["t"]), "feed": a["feed"], "nature": a["nature"],
                     "address": a["address"], "sent": a["sent"]}
                    for a in list(self.alerts)[:30]
                ],
                "clips": [
                    {"age_sec": self._age(c["t"]), "feed": c["feed"],
                     "url": "/audio/" + c["file"], "transcript": c["transcript"]}
                    for c in list(self.clips)[:20]
                ],
                "recent_events": [
                    {"age_sec": self._age(e["t"]), "feed": e["feed"], "msg": e["msg"]}
                    for e in list(self.events)[:20]
                ],
            }


def _fmt_age(sec) -> str:
    if sec is None:
        return "-"
    sec = int(sec)
    if sec < 90:
        return f"{sec}s ago"
    if sec < 5400:
        return f"{sec // 60}m ago"
    return f"{sec // 3600}h ago"


def _html(snap: dict) -> str:
    def esc(x):
        return html.escape(str(x))

    feed_rows = []
    for name, f in snap["feeds"].items():
        state = '<span class="ok">RECORDING</span>' if f["ffmpeg_running"] else '<span class="bad">DOWN</span>'
        feed_rows.append(
            f"<tr><td>{esc(name)}</td><td>{state}</td>"
            f"<td>{f['segments_seen']}</td><td>{f['transcripts']}</td>"
            f"<td>{f['ffmpeg_restarts']}</td>"
            f"<td>{_fmt_age(f['last_segment_age_sec'])}</td>"
            f"<td>{esc(f['last_transcript'][:140])}</td></tr>")

    if snap["alert_log"]:
        alert_rows = "".join(
            f"<tr><td>{_fmt_age(a['age_sec'])}</td><td>{esc(a['feed'])}</td>"
            f"<td>{esc(a['nature'])}</td><td>{esc(a['address'])}</td>"
            f"<td>{'sent' if a['sent'] else 'FAILED'}</td></tr>"
            for a in snap["alert_log"])
    else:
        alert_rows = '<tr><td colspan="5" class="dim">no dispatch alerts yet this run</td></tr>'

    if snap["clips"]:
        clip_items = "".join(
            f"<tr><td>{_fmt_age(c['age_sec'])}</td><td>{esc(c['feed'])}</td>"
            f'<td><audio controls preload="none" src="{esc(c["url"])}"></audio></td>'
            f"<td class=\"dim\">{esc(c['transcript'][:120])}</td></tr>"
            for c in snap["clips"])
    else:
        clip_items = '<tr><td colspan="4" class="dim">no speech captured yet this run - clips appear here the first time a feed talks</td></tr>'

    evs = "".join(
        f"<li>[{esc(e['feed'])}] {esc(e['msg'])} <span class=dim>({_fmt_age(e['age_sec'])})</span></li>"
        for e in snap["recent_events"])

    return f"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta http-equiv=refresh content=60>
<title>FD - Brooklyn/Sullivan monitor status</title>
<style>
body{{font:13px/1.45 ui-monospace,Menlo,Consolas,monospace;background:#fff;color:#111;padding:16px;max-width:1000px;margin:auto}}
h1{{font-size:15px;margin:0 0 2px}} h2{{font-size:13px;margin:18px 0 6px;text-transform:uppercase;letter-spacing:.5px}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #999;padding:3px 8px;text-align:left;vertical-align:top}}
th{{background:#eee}}
.ok{{font-weight:700}} .bad{{color:#b00;font-weight:700}} .dim{{color:#666}}
audio{{height:28px;width:220px}}
ul{{margin:0;padding-left:18px}} li{{margin:2px 0}}
.bar{{border:1px solid #999;background:#eee;padding:6px 10px;margin:8px 0}}
</style>
<h1>FD - BROOKLYN/SULLIVAN dispatch monitor</h1>
<div class="bar">
status: <span class="ok">LIVE</span> &middot; uptime {int(snap['uptime_sec'] // 60)}m
&middot; commit {esc(snap['git_commit'] or '?')}
&middot; WAHA session: <b>{esc(snap['waha_session'])}</b>
&middot; alerts sent {snap['alerts_sent']} (failed {snap['alerts_failed']})
&middot; feeds: Hatzolah Brooklyn EMS (Broadcastify 7392), Sullivan County Fire/EMS (32727)
&middot; auto-refresh 60s
</div>
<h2>feeds</h2>
<table><tr><th>feed</th><th>capture</th><th>segments</th><th>transcripts</th><th>restarts</th><th>last audio</th><th>last thing heard</th></tr>
{''.join(feed_rows)}</table>
<h2>job / alert log</h2>
<table><tr><th>when</th><th>feed</th><th>nature</th><th>address</th><th>whatsapp</th></tr>
{alert_rows}</table>
<h2>recent feed audio</h2>
<table><tr><th>when</th><th>feed</th><th>play</th><th>transcript</th></tr>
{clip_items}</table>
<h2>event log</h2>
<ul>{evs}</ul>
<p class="dim"><a href="/status">/status JSON</a> &middot; <a href="/health">/health</a> &middot; operated by Instinct</p>"""


async def _health(_req: web.Request) -> web.Response:
    return web.Response(text="ok")


def make_app(stats: Stats) -> web.Application:
    async def status_json(_req: web.Request) -> web.Response:
        return web.Response(text=json.dumps(stats.snapshot(), indent=1),
                            content_type="application/json")

    async def home(_req: web.Request) -> web.Response:
        return web.Response(text=_html(stats.snapshot()), content_type="text/html")

    async def audio(req: web.Request) -> web.Response:
        name = req.match_info["name"]
        if not name or "/" in name or ".." in name:
            raise web.HTTPNotFound()
        path = ARCHIVE_DIR / name
        if not path.exists():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Content-Type": "audio/wav"})

    app = web.Application()
    app.router.add_get("/health", _health)
    app.router.add_get("/status", status_json)
    app.router.add_get("/audio/{name}", audio)
    app.router.add_get("/", home)
    return app


async def start_web(stats: Stats) -> None:
    port = int(os.environ.get("PORT", "10000"))
    runner = web.AppRunner(make_app(stats))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logging.info("status server on :%s (/ /health /status /audio/<file>)", port)


async def keepalive(stats: Stats) -> None:
    """Ping our own external URL so the free host never idles into sleep."""
    import aiohttp
    base = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if not base:
        logging.info("RENDER_EXTERNAL_URL unset - self-keepalive disabled")
        return
    while True:
        await asyncio.sleep(240)
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{base}/health", timeout=aiohttp.ClientTimeout(total=20)) as r:
                    logging.info("self-keepalive ping: HTTP %s", r.status)
        except Exception as e:  # noqa: BLE001
            logging.warning("self-keepalive failed: %s", e)
            stats.event("system", f"keepalive failed: {e}")
