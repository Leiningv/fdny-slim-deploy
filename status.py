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
        self.alerts: deque = deque(maxlen=500)
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

    def mark_alert(self, profile: str, nature: str, address: str, ok: bool,
                   failed: bool = True, outcome: str = "") -> None:
        with self._lock:
            f = self.feed(profile)
            f["last_alert_at"] = time.time()
            f["last_alert"] = f"{nature} @ {address}"
            if ok:
                self.alerts_sent += 1
            elif failed:
                self.alerts_failed += 1
            out = outcome or ("sent" if ok else ("failed" if failed else "suppressed"))
            self.alerts.appendleft({"t": time.time(), "feed": profile,
                                    "nature": nature, "address": address, "sent": ok,
                                    "outcome": out})
            self.events.appendleft({"t": time.time(), "feed": profile,
                                    "msg": f"ALERT {out}: {nature} @ {address}"})

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
                     "address": a["address"], "sent": a["sent"],
                     "outcome": a.get("outcome") or ("sent" if a["sent"] else "failed")}
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


_PAGE_CSS = """
*{box-sizing:border-box;border-radius:0!important}
body{background:#15171b;color:#d6d8db;font:12px/1.45 Arial,Helvetica,sans-serif;margin:0;padding:18px 22px}
h1{font-size:15px;letter-spacing:3px;font-weight:700;margin:0;color:#e8e9eb}
.sub{color:#7c828b;font-size:11px;letter-spacing:1px}
table{border-collapse:collapse;width:100%;margin:4px 0 16px}
th{text-align:left;font-size:10px;letter-spacing:2px;color:#82888f;border-bottom:1px solid #3a3e45;padding:3px 8px 3px 0;font-weight:600}
td{border-bottom:1px solid #262a30;padding:4px 8px 4px 0;vertical-align:top}
.sec{font-size:10px;letter-spacing:3px;color:#82888f;border-bottom:2px solid #3a3e45;margin:18px 0 2px;padding-bottom:3px}
.mono{font-family:'Courier New',monospace;font-size:11px}
.num{font-family:'Courier New',monospace;text-align:right;padding-right:14px}
.ok{color:#5fb96e} .warn{color:#c9a44a} .bad{color:#c05046} .dim{color:#6d737c} .heard{color:#a6abb3;font-size:11px}
.hdr{border:1px solid #3a3e45;border-left:6px solid #5fb96e;padding:10px 14px;margin-bottom:14px}
.hdr table td{border:0;padding:1px 26px 1px 0}
.kv b{color:#e8e9eb}
.rules{color:#a6abb3;font-size:11px;margin-top:2px}
audio{height:22px;width:190px}
@media(max-width:760px){
body{padding:10px}
h1{font-size:13px;letter-spacing:2px}
.hdr{padding:8px 10px}
.hdr table td{display:inline-block;padding:3px 16px 3px 0}
table.resp thead{display:none}
table.resp,table.resp tbody{display:block}
table.resp tr{display:block;border-bottom:1px solid #3a3e45;padding:5px 0}
table.resp td{display:block;border:0;padding:2px 0}
table.resp td::before{content:attr(data-label);display:inline-block;min-width:96px;color:#82888f;font-size:10px;letter-spacing:1px}
table.resp td.num{text-align:left;padding-right:0}
audio{width:100%;max-width:280px;height:30px}
}
"""

_PAGE_JS = """
const FL={fdny:"FDNY Brooklyn dispatch (Calls)","zello-hatzalah":"Zello TSL-ChevraHatzalah (24/7)","zello-sullivan":"Zello Sullivan County (24/7, dedicated account)"};
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function fmtAge(sec){if(sec==null)return "-";sec=Math.floor(sec);if(sec<90)return sec+"s ago";if(sec<5400)return Math.floor(sec/60)+"m ago";return Math.floor(sec/3600)+"h ago";}
function fmtUp(sec){const m=Math.floor(sec/60);return m<180?m+"m":Math.floor(m/60)+"h"+String(m%60).padStart(2,"0")+"m";}
async function tick(){
 try{
  const s=await (await fetch("/status")).json();
  const feedsDown=Object.values(s.feeds||{}).some(f=>!f.ffmpeg_running);
  const deg=feedsDown||s.waha_session!=="WORKING";
  const st=document.getElementById("hd-status");
  st.textContent=deg?"\\u25A0 DEGRADED":"\\u25A0 OPERATIONAL";
  st.className=deg?"warn":"ok";
  document.getElementById("hd-uptime").textContent=fmtUp(s.uptime_sec);
  document.getElementById("hd-build").textContent=s.git_commit||"?";
  const w=document.getElementById("hd-waha");
  w.textContent=s.waha_session; w.className=s.waha_session==="WORKING"?"ok":"bad";
  document.getElementById("hd-sent").textContent=s.alerts_sent;
  document.getElementById("hd-failed").textContent=s.alerts_failed;
  document.getElementById("hd-queued").textContent=s.waha_session!=="WORKING"?s.alerts_failed:0;
  const ab=document.getElementById("alerts-body");
  if(s.alert_log&&s.alert_log.length){
   ab.innerHTML=s.alert_log.map(a=>{
    const oc=(a.outcome||(a.sent?"sent":"failed")).toUpperCase();
    const cls=a.sent?"ok":(oc==="FAILED"?"bad":"warn");
    return "<tr><td class=dim data-label=WHEN>"+fmtAge(a.age_sec)+"</td>"
     +"<td class=mono data-label=FEED>"+esc(a.feed)+"</td>"
     +"<td data-label=NATURE>"+esc(a.nature||"-")+"</td>"
     +"<td data-label=ADDRESS>"+esc(a.address)+"</td>"
     +"<td class="+cls+" data-label=RESULT>"+esc(oc)+"</td></tr>";
   }).join("");
  }else{
   ab.innerHTML='<tr><td colspan=5 class=dim>no dispatch alerts yet this run</td></tr>';
  }
  const fb=document.getElementById("feeds-body");
  const order=["fdny","zello-hatzalah","zello-sullivan"].filter(n=>s.feeds&&s.feeds[n])
   .concat(Object.keys(s.feeds||{}).filter(n=>!["fdny","zello-hatzalah","zello-sullivan"].includes(n)).sort());
  fb.innerHTML=order.map(n=>{
   const f=s.feeds[n];
   const st2=f.ffmpeg_running?'<td class=ok data-label=CAPTURE>\\u25A0 RECORDING</td>':'<td class=bad data-label=CAPTURE>\\u25A0 DOWN</td>';
   return "<tr><td class=mono data-label=ID>"+esc(n)+"</td>"
    +"<td data-label=CHANNEL>"+esc(FL[n]||n)+"</td>"+st2
    +'<td class=num data-label=SEG>'+f.segments_seen+"</td>"
    +'<td class=num data-label=TRX>'+f.transcripts+"</td>"
    +'<td class=num data-label=RST>'+f.ffmpeg_restarts+"</td>"
    +'<td class=dim data-label="LAST AUDIO">'+fmtAge(f.last_segment_age_sec)+"</td>"
    +'<td class=heard data-label="LAST HEARD">'+esc((f.last_transcript||"").slice(0,160))+"</td></tr>";
  }).join("");
 }catch(e){}
}
setInterval(tick,5000);
"""


def _html(snap: dict) -> str:
    def esc(x):
        return html.escape(str(x))

    feed_labels = {
        "fdny": "FDNY Brooklyn dispatch (Calls)",
        "zello-hatzalah": "Zello TSL-ChevraHatzalah (24/7)",
        "zello-sullivan": "Zello Sullivan County (24/7, dedicated account)",
    }
    order = [n for n in ("fdny", "zello-hatzalah", "zello-sullivan") if n in snap["feeds"]]
    order += sorted(n for n in snap["feeds"] if n not in order)

    feed_rows = []
    for name in order:
        f = snap["feeds"][name]
        if f["ffmpeg_running"]:
            state = '<td class="ok" data-label="CAPTURE">&#9632; RECORDING</td>'
        else:
            state = '<td class="bad" data-label="CAPTURE">&#9632; DOWN</td>'
        feed_rows.append(
            f'<tr><td class="mono" data-label="ID">{esc(name)}</td>'
            f'<td data-label="CHANNEL">{esc(feed_labels.get(name, name))}</td>{state}'
            f'<td class="num" data-label="SEG">{f["segments_seen"]}</td>'
            f'<td class="num" data-label="TRX">{f["transcripts"]}</td>'
            f'<td class="num" data-label="RST">{f["ffmpeg_restarts"]}</td>'
            f'<td class="dim" data-label="LAST AUDIO">{_fmt_age(f["last_segment_age_sec"])}</td>'
            f'<td class="heard" data-label="LAST HEARD">{esc(f["last_transcript"][:160])}</td></tr>')
    feeds_html = "".join(feed_rows) or '<tr><td colspan="8" class="dim">no feeds registered yet</td></tr>'

    if snap["alert_log"]:
        alert_rows = []
        for a in snap["alert_log"]:
            outcome = (a.get("outcome") or ("sent" if a["sent"] else "failed")).upper()
            cls = "ok" if a["sent"] else ("bad" if outcome == "FAILED" else "warn")
            alert_rows.append(
                f'<tr><td class="dim" data-label="WHEN">{_fmt_age(a["age_sec"])}</td>'
                f'<td class="mono" data-label="FEED">{esc(a["feed"])}</td>'
                f'<td data-label="NATURE">{esc(a["nature"] or "-")}</td>'
                f'<td data-label="ADDRESS">{esc(a["address"])}</td>'
                f'<td class="{cls}" data-label="RESULT">{esc(outcome)}</td></tr>')
        alerts_html = "".join(alert_rows)
    else:
        alerts_html = '<tr><td colspan="5" class="dim">no dispatch alerts yet this run</td></tr>'

    if snap["clips"]:
        clip_rows = "".join(
            f'<tr><td class="dim" data-label="WHEN">{_fmt_age(c["age_sec"])}</td>'
            f'<td class="mono" data-label="FEED">{esc(c["feed"])}</td>'
            f'<td data-label="PLAY"><audio controls preload="none" src="{esc(c["url"])}"></audio></td>'
            f'<td class="heard" data-label="TRANSCRIPT">{esc(c["transcript"][:140])}</td></tr>'
            for c in snap["clips"])
    else:
        clip_rows = ('<tr><td colspan="4" class="dim">no speech captured yet this run'
                     ' - clips appear here the first time a feed talks</td></tr>')

    ev_rows = "".join(
        f'<tr><td class="dim" data-label="WHEN">{_fmt_age(e["age_sec"])}</td>'
        f'<td class="mono" data-label="FEED">{esc(e["feed"])}</td>'
        f'<td data-label="EVENT">{esc(e["msg"])}</td></tr>'
        for e in snap["recent_events"]) or '<tr><td colspan="3" class="dim">no events yet</td></tr>'

    import transcribe as _tr
    engine = ("assemblyai universal-3-pro + keyterm boost (local whisper fallback)"
              if _tr.AAI_KEY else "local whisper (faster-whisper)")
    queued = snap["alerts_failed"] if snap["waha_session"] != "WORKING" else 0

    feeds_down = any(not f["ffmpeg_running"] for f in snap["feeds"].values())
    degraded = feeds_down or snap["waha_session"] != "WORKING"
    status_word = "DEGRADED" if degraded else "OPERATIONAL"
    status_cls = "warn" if degraded else "ok"
    waha_cls = "ok" if snap["waha_session"] == "WORKING" else "bad"
    hdr_border = "#c9a44a" if degraded else "#5fb96e"
    uptime_m = int(snap["uptime_sec"] // 60)
    uptime = f"{uptime_m}m" if uptime_m < 180 else f"{uptime_m // 60}h{uptime_m % 60:02d}m"

    head = (
        "<!doctype html><html><head><meta charset=utf-8>\n"
        '<meta name=viewport content="width=device-width,initial-scale=1">\n'
        '<meta http-equiv=refresh content=60>\n'
        "<title>FDNY-SLIM DISPATCH MONITOR</title>\n<style>" + _PAGE_CSS + "</style></head><body>\n")

    body = f"""<div class=hdr style="border-left-color:{hdr_border}"><h1>FDNY-SLIM &nbsp;DISPATCH MONITOR</h1>
<div class=sub>BROOKLYN DISPATCH WATCH &middot; CITY OF NEW YORK FIRE CHANNELS</div>
<table class=kv><tr>
<td>STATUS <b id=hd-status class={status_cls}>&#9632; {status_word}</b></td>
<td>UPTIME <b id=hd-uptime>{uptime}</b></td>
<td>BUILD <b id=hd-build class=mono>{esc(snap['git_commit'] or '?')}</b></td>
<td>WHATSAPP LINK <b id=hd-waha class={waha_cls}>{esc(snap['waha_session'])}</b></td>
<td>ALERTS POSTED <b id=hd-sent>{snap['alerts_sent']}</b></td>
<td>FAILED <b id=hd-failed>{snap['alerts_failed']}</b></td>
<td>QUEUED <b id=hd-queued>{queued}</b></td>
</tr></table>
<div class=rules>POSTING RULES &nbsp; option-1 layout &nbsp;|&nbsp; box numbers verified vs fdnewyork.com &nbsp;|&nbsp; map-canonical street spelling &nbsp;|&nbsp; freshness gate (live &le;5m, Calls &le;10m) &nbsp;|&nbsp; same-second text+voice note &nbsp;|&nbsp; ops log -&gt; FD SYSTEM UPDATES</div>
</div>
<div class=sec>LIVE ALERTS - JOB / ALERT LOG</div><table class=resp>
<thead><tr><th>WHEN</th><th>FEED</th><th>NATURE</th><th>ADDRESS</th><th>RESULT</th></tr></thead>
<tbody id=alerts-body>{alerts_html}</tbody></table>
<div class=sec>FEEDS</div><table class=resp>
<thead><tr><th>ID</th><th>CHANNEL</th><th>CAPTURE</th><th>SEG</th><th>TRX</th><th>RST</th><th>LAST AUDIO</th><th>LAST HEARD</th></tr></thead>
<tbody id=feeds-body>{feeds_html}</tbody></table>
<div class=sec>RECENT FEED AUDIO</div><table class=resp>
<thead><tr><th>WHEN</th><th>FEED</th><th>PLAY</th><th>TRANSCRIPT</th></tr></thead>
<tbody>{clip_rows}</tbody></table>
<div class=sec>EVENT LOG</div><table class=resp>
<thead><tr><th>WHEN</th><th>FEED</th><th>EVENT</th></tr></thead>
<tbody>{ev_rows}</tbody></table>
<div class=dim style="font-size:10px">{esc(engine)} &middot; live updates 5s &middot; <a href="/status" style="color:#6d737c">/status JSON</a> &middot; operated by Instinct</div>
<script>{_PAGE_JS}</script>
</body></html>"""
    return head + body


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
        ct = "audio/ogg" if path.suffix == ".ogg" else "audio/wav"
        return web.FileResponse(path, headers={"Content-Type": ct})

    app = web.Application()
    async def diag(req: web.Request) -> web.Response:
        # temporary egress diagnostic: GET /diag?u=<url> -> upstream status + body head
        import urllib.request, urllib.error
        u = req.rel_url.query.get("u", "")
        if not u.startswith("http"):
            return web.Response(status=400, text="need ?u=http...")
        rq = urllib.request.Request(u, headers={"User-Agent": "fdny-slim-diag"})
        try:
            with urllib.request.urlopen(rq, timeout=20) as r:
                body = r.read(400).decode("utf-8", "replace")
                return web.Response(text=f"OK {r.status}\n{body}")
        except urllib.error.HTTPError as e:
            body = e.read(400).decode("utf-8", "replace")
            return web.Response(text=f"HTTP {e.code}\n{body}")
        except Exception as e:
            return web.Response(text=f"ERR {e}")

    async def hls_push(req: web.Request) -> web.Response:
        # login relay pushes tokenized HLS URLs here (see .github/workflows/hls.yml)
        secret = os.environ.get("HLS_PUSH_SECRET", "")
        try:
            d = await req.json()
        except Exception:
            return web.Response(status=400, text="bad json")
        if not secret or d.get("secret") != secret:
            return web.Response(status=403, text="bad secret")
        p = Path(os.environ.get("SEG_DIR", "./segments")) / "hls_push.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        cur = {}
        try:
            cur = json.loads(p.read_text())
        except Exception:
            pass
        now = time.time()
        saved = []
        for prof, u in (d.get("urls") or {}).items():
            if prof in ("hatzolah", "sullivan") and isinstance(u, str) and u.startswith("https://"):
                cur[prof] = {"url": u, "ts": now}
                stats.event(prof, "stream URL pushed via relay")
                saved.append(prof)
        p.write_text(json.dumps(cur))
        return web.json_response({"ok": True, "feeds": saved})

    async def fdny_calls(req: web.Request) -> web.Response:
        # The sandbox poller pushes FDNY Calls here. www.broadcastify.com
        # refuses Render egress, so the poll/login runs off-box (same relay
        # pattern as /hls); call audio stays on the calls CDN, which Render
        # CAN reach, so clips are downloaded by the consumer in main.py.
        secret = os.environ.get("HLS_PUSH_SECRET", "")
        try:
            d = await req.json()
        except Exception:
            return web.Response(status=400, text="bad json")
        if not secret or d.get("secret") != secret:
            return web.Response(status=403, text="bad secret")
        calls = d.get("calls")
        if not isinstance(calls, list):
            return web.Response(status=400, text="calls must be a list")
        p = Path(os.environ.get("SEG_DIR", "./segments")) / "fdny_inbox.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        kept = 0
        with p.open("a") as fh:
            for c in calls[:50]:
                if isinstance(c, dict) and (c.get("id") or c.get("filename")):
                    fh.write(json.dumps(c)[:4000] + "\n")
                    kept += 1
        stats.event("fdny", f"{kept} call(s) pushed via relay")
        return web.json_response({"ok": True, "queued": kept})

    app.router.add_get("/health", _health)
    app.router.add_get("/diag", diag)
    app.router.add_post("/hls", hls_push)
    app.router.add_post("/fdny_calls", fdny_calls)
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
