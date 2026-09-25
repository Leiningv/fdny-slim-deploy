# fdny-slim

Slim, **100% free** FDNY/Hatzolah dispatch alert system, v2 rebuilt and
operated by **Instinct**. Listens to two Broadcastify live dispatch feeds,
transcribes locally, extracts the emergency address, and posts WhatsApp
alerts via WAHA to the "FD - BROOKLYN/SULLIVAN" group.

```
Broadcastify HLS ─► ffmpeg (continuous, gapless 20s segments, rotating ring)
   ─► faster-whisper tiny.en (local, RMS energy gate + VAD)
   ─► detect (emergency? address?) ─► dedup 30 min ─► WhatsApp via WAHA
```

No paid APIs. No cloud transcription. No blind spots: ffmpeg records
continuously, and adjacent segment PAIRS are transcribed so a dispatch split
across a segment boundary is still captured whole.

## Feeds

| Profile    | Feed                            | Broadcastify ID |
|------------|---------------------------------|-----------------|
| `hatzolah` | Hatzolah EMS Dispatch Brooklyn   | 7392            |
| `sullivan` | Sullivan County Fire/EMS Paging  | 32727           |

## Standalone status page

The service runs a small web server (binds `$PORT`):

- `/` — live status page: alive state, per-feed capture status, job/alert
  log, **playable audio of recent feed captures**, event log. Auto-refresh 60s.
- `/status` — same data as JSON.
- `/health` — plain `ok` for uptime pingers.
- `/audio/<file>` — archived speech clips.

## Run (Render free web service, current production)

Render service type **web service, existing image** `docker.io/library/python:3.11-slim`,
start command:

```bash
apt-get update -qq && apt-get install -y -qq ffmpeg git curl && \
git clone -q https://x-access-token:$GH_PAT@github.com/Leiningv/Fdny-slim /app && \
cd /app && pip install -q -r requirements.txt && python main.py
```

Env vars on the host (never committed): `GH_PAT`, `BROADCASTIFY_USER`,
`BROADCASTIFY_PASS`, `WAHA_API_KEY`, plus `WAHA_URL`, `WAHA_CHAT_ID`,
`WAHA_SESSION`, `WHISPER_MODEL`. Render provides `PORT` and
`RENDER_EXTERNAL_URL` (the latter enables the built-in self-keepalive ping
that stops the free tier from sleeping).

## Run (VM / systemd)

Python 3.11+, `apt install ffmpeg`, `pip install -r requirements.txt`,
`cp config.env.example config.env` and fill it in, then `python3 main.py`
or install `fdny-slim.service` (edit `YOUR_USER` first).

## Files

- `ingest.py` — HLS login (free web-player flow), supervised continuous
  segmented capture, ring of WAV segments
- `transcribe.py` — faster-whisper CPU int8 + RMS energy gate
- `detect.py` — emergency patterns, nature classification, address extraction
  (Brooklyn grid, house addresses, highway exits)
- `alert_waha.py` — WhatsApp text via WAHA `POST /api/sendText`
- `status.py` — status page/JSON, audio archive serving, self-keepalive
- `main.py` — asyncio orchestrator, pair transcription, persistent dedup,
  alert log
- `test_detect.py` — unit tests for the detection logic (`python3 test_detect.py`)
