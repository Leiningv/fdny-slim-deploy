"""Broadcastify login relay: www.broadcastify.com blocks Render egress IPs but
not GitHub Actions runners. Logs in for each feed and pushes the tokenized HLS
URLs to the fdny-slim status server. Never prints the URLs."""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ingest  # noqa: E402

urls = {}
for prof, fid in ingest.FEEDS.items():
    try:
        urls[prof] = ingest.get_hls_url(fid)
        print(prof, "login ok")
    except Exception as e:  # noqa: BLE001
        print(prof, "login FAILED:", e)

if not urls:
    sys.exit("no feed URLs obtained")

body = json.dumps({"secret": os.environ["HLS_PUSH_SECRET"], "urls": urls}).encode()
req = urllib.request.Request(
    os.environ.get("PUSH_URL", "https://fdny-slim.onrender.com/hls"),
    data=body, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=30) as r:
    print("push status:", r.status)
