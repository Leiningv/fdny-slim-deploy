#!/usr/bin/env python3
"""FDNY Calls poller daemon.

Polls the Broadcastify Calls live-calls API from the sandbox (Render egress is
blocked on www.broadcastify.com) and pushes new calls to the fdny-slim service
/fdny_calls endpoint. Supervised by the 10-min wake (pidfile check + restart);
doInit=1 backlog on every (re)start covers downtime - the service dedups by
call id, so replays are harmless.
"""
import json, os, sys, time, secrets, http.cookiejar, urllib.request, urllib.parse, urllib.error

env = dict(map(str.strip, l.split('=',1)) for l in open('/tmp/bcfy_env') if '=' in l)
SECRET = open('/tmp/hls_secret').read().strip()
PUSH_URL = "https://fdny-slim.onrender.com/fdny_calls"
# Brooklyn Dispatch playlist. Citywide (config flag for later): b11f7ea0-0149-11f1-bb32-0ef97433b5f9
PLAYLIST = os.environ.get("FDNY_PLAYLIST", "72a9370f-010f-11f1-bb32-0ef97433b5f9")
API = "https://www.broadcastify.com/calls/apis/live-calls"
LOGIN = "https://www.broadcastify.com/login/"
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
IDS_FILE = '/tmp/fdny_ids.json'
POLL_SEC = 6

def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)

class Poller:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.sk = secrets.token_hex(16)
        self.init = '1'
        self.pos = 0.0
        self.ids = self._load_ids()
        self.last_count = 0
        self.last_source_stop = 0.0
    def _load_ids(self):
        try:
            d = json.load(open(IDS_FILE)); now = time.time()
            return {k: v for k, v in d.items() if now - v < 24 * 3600}
        except Exception:
            return {}
    def _save_ids(self):
        try: json.dump(self.ids, open(IDS_FILE, 'w'))
        except Exception: pass
    def req(self, url, data=None):
        r = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None,
            headers={'User-Agent': UA, 'Accept': '*/*', 'Referer': 'https://www.broadcastify.com/calls/'})
        return self.op.open(r, timeout=30)
    def login(self):
        self.req(LOGIN, {'username': env['BROADCASTIFY_USER'], 'password': env['BROADCASTIFY_PASS'],
                         'action': 'auth', 'redirect': 'https://www.broadcastify.com'}).read()
        log('login ok')
    def poll(self):
        payload = {'pos': f'{self.pos:.3f}', 'doInit': self.init, 'sessionKey': self.sk,
                   'playlist_uuid': PLAYLIST, 'systemId': '0', 'sid': '0'}
        try:
            d = json.loads(self.req(API, payload).read())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                log('poll HTTP', e.code, '- re-login next cycle')
                self.login()
                return []
            raise
        self.init = '0'
        calls = d.get('calls') or []
        self.last_count = len(calls)
        self.last_source_stop = max((float(c.get('meta_stoptime') or 0) for c in calls), default=0)
        new = []
        now = time.time()
        for c in calls:
            cid = str(c.get('filename') or c.get('id') or '')
            if not cid or cid in self.ids:
                continue
            self.ids[cid] = now
            audio = None
            if c.get('filename') and c.get('enc'):
                host = 'https://calls-ai-1.broadcastify.com' if str(c.get('transcribe')) == '1' else 'https://calls.broadcastify.com'
                h = (str(c.get('hash')) + '/') if c.get('hash') else ''
                audio = f"{host}/{h}{c.get('systemId')}/{c['filename']}.{c['enc']}"
            new.append({'id': cid, 'ts': c.get('meta_stoptime') or c.get('ts') or int(now), 'audio_start_ts': c.get('meta_starttime'),
                        'tg': c.get('descr') or '', 'duration': c.get('call_duration') or 0,
                        'transcription': (c.get('transcription') or '')[:1500],
                        'audio_url': audio})
            try:
                self.pos = max(self.pos, float(c.get('meta_stoptime') or 0) + 0.001)
            except Exception:
                pass
        try:
            lp = float(d.get('lastPos') or 0)
            if lp > self.pos:
                self.pos = lp
        except Exception:
            pass
        if new:
            self._save_ids()
        return new
    def push(self, calls):
        body = json.dumps({'secret': SECRET, 'calls': calls}).encode()
        r = urllib.request.Request(PUSH_URL, data=body,
                                   headers={'Content-Type': 'application/json', 'User-Agent': 'fdny-slim-poller/1.0'})
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read()[:120]

def main():
    p = Poller()
    p.login()
    total = 0
    previous_wall = previous_mono = None
    while True:
        wall, mono = time.time(), time.monotonic()
        log('heartbeat', 'phase', 'iteration_start', 'wall_ns', time.time_ns(),
            'monotonic_ns', time.monotonic_ns(),
            'wall_gap', round(wall-previous_wall,3) if previous_wall else None,
            'mono_gap', round(mono-previous_mono,3) if previous_mono else None,
            'pid', os.getpid())
        previous_wall, previous_mono = wall, mono
        try:
            started = time.monotonic()
            log('heartbeat', 'phase', 'poll_begin')
            new = p.poll()
            log('heartbeat', 'phase', 'poll_end')
            elapsed = time.monotonic() - started
            source_age = round(time.time() - p.last_source_stop, 1) if p.last_source_stop else None
            log('poll', 'duration', round(elapsed, 2), 'returned', p.last_count,
                'new', len(new), 'newest_stop_age', source_age)
            if new:
                log('heartbeat', 'phase', 'push_begin', 'count', len(new))
                st, resp = p.push(new)
                log('heartbeat', 'phase', 'push_end')
                total += len(new)
                log('pushed', len(new), '->', st, resp.decode(errors='ignore'), '| total', total)
        except Exception as e:
            log('ERROR', type(e).__name__, str(e)[:200])
            time.sleep(20)
        log('heartbeat', 'phase', 'sleep_begin', 'seconds', POLL_SEC)
        time.sleep(POLL_SEC)
        log('heartbeat', 'phase', 'sleep_end')

if __name__ == '__main__':
    main()
