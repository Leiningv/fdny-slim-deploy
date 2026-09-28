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

import aiohttp
import alert_waha
import control
import detect
import ingest
import transcribe
import zello_ingest
from status import ARCHIVE_DIR, ARCHIVE_KEEP, Stats, keepalive, start_web

_OPS_Q: list[str] = []
_OPS_TASKS: list = []


def ops_log(line: str) -> None:
    logging.info("ops: %s", line)
    _OPS_Q.append(line)


async def _kw_check(profile: str, text: str) -> None:
    """Post a heads-up to the ops group when a transcript hits a watched keyword."""
    try:
        watches = control.keyword_watches()
    except Exception:  # noqa: BLE001
        return
    low = text.lower()
    hits = [w for w in watches if w.lower() in low]
    if hits:
        stats.event(profile, f"watch hit ({', '.join(hits)}): {text[:120]}")
        ops_log(f"\U0001F440 watch hit [{profile}] ({', '.join(hits)}): {text[:200]}")


async def _uguu_upload(path: Path) -> str:
    """Upload the voice-note OGG to uguu.se (free, permanent) -> durable URL."""
    try:
        data = aiohttp.FormData()
        data.add_field("files[]", path.read_bytes(), filename=path.name,
                       content_type="audio/ogg")
        async with aiohttp.ClientSession() as s:
            async with s.post("https://uguu.se/upload?output=json", data=data,
                              timeout=aiohttp.ClientTimeout(total=45)) as r:
                d = await r.json(content_type=None)
        url = str(((d.get("files") or [{}])[0]).get("url") or "")
        if d.get("success") and url.startswith("https://"):
            return url
        logging.warning("uguu upload rejected: %s", str(d)[:200])
    except Exception as e:  # noqa: BLE001
        logging.warning("uguu upload failed: %s", e)
    return ""


async def _ops_flusher() -> None:
    while True:
        await asyncio.sleep(300)
        if not _OPS_Q:
            continue
        lines, _OPS_Q[:] = _OPS_Q[:12], _OPS_Q[12:]
        try:
            await alert_waha.send_ops("🛠 " + "\n".join(lines))
        except Exception as e:  # noqa: BLE001
            logging.warning("ops flush failed: %s", e)


def _ensure_ogg(clip_name: str):
    src = ARCHIVE_DIR / clip_name
    ogg = src.with_suffix(".ogg")
    if ogg.exists():
        return ogg.name
    try:
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001
            ff = "ffmpeg"
        import subprocess
        subprocess.run([ff, "-y", "-v", "error", "-i", str(src), "-c:a", "libopus", "-b:a", "32k", str(ogg)],
                       check=True, timeout=60)
        return ogg.name
    except Exception as e:  # noqa: BLE001
        logging.warning("ogg convert failed for %s: %s", clip_name, e)
        return None

NY = ZoneInfo("America/New_York")
DEDUP_SEC = int(os.environ.get("DEDUP_SECONDS", str(30 * 60)))
# Freshness gate (user rule 9/28: "Never post an old recording - has to be on
# time. It's an alert system for first responders."). A stale alert is worse
# than none: suppress + ops-log instead of posting.
FRESH_LIVE_SEC = int(os.environ.get("FRESH_LIVE_SEC", "300"))   # Zello/HLS live: normal lag <2 min
FRESH_FDNY_SEC = int(os.environ.get("FRESH_FDNY_SEC", "600"))   # Broadcastify Calls: normal lag 2-5 min
SEG_DIR = Path(os.environ.get("SEG_DIR", "./segments"))
SEEN_FILE = Path(os.environ.get("SEEN_FILE", "./segments/seen.json"))
FDNY_INBOX = SEG_DIR / "fdny_inbox.jsonl"
FDNY_IDS = SEG_DIR / "fdny_ids.json"

SOURCE_LABEL = {"hatzolah": "Hatzolah Dispatch", "sullivan": "Sullivan Co Fire/EMS",
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
    base = addr if re.search(r",\s*(?:NY|NJ)$", addr, re.I) else f"{addr}, NY"
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
    # digit-word road names: the map spells them out ('Marcel 4 Road' ->
    # 'Marcel Four Road', Eldred 9/28). Lookahead to the street type keeps
    # house numbers and ordinals untouched.
    _SPELL = {"1": "One", "2": "Two", "3": "Three", "4": "Four", "5": "Five",
              "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine", "10": "Ten"}
    _md = re.search(r"\b(\d{1,2})\b(?=\s+(?:road|rd|street|st|avenue|ave|drive|dr|"
                    r"lane|ln|court|ct|place|pl|boulevard|blvd)\b)", street, re.I)
    if _md and _md.group(1) in _SPELL:
        spelled = street[:_md.start()] + _SPELL[_md.group(1)] + street[_md.end():]
        variants.append(spelled + ("," + tail if tail else ""))
    if profile == "sullivan":
        variants.append(f"{street}, Sullivan County, NY")
        variants.append(f"{street}, Monticello, NY")
    if "hatzal" in profile.lower() or "hatzol" in profile.lower():
        # TSL/Chevra covers NYC + Sullivan/Five Towns: the extracted area suffix
        # is a guess ("Brooklyn" by default) - also try de-biased queries
        variants.append(f"{street}, Sullivan County, NY")
        variants.append(f"{street}, NY")
        if base.endswith(", NJ"):
            variants.insert(0, f"{street}, Bergen County, NJ")
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


async def _planning_labs(addr: str, allowed_boroughs: list[str]) -> tuple:
    """NYC Planning Labs geosearch (free, keyless). Returns (label, lat, lon)
    when the top hit is in an allowed borough, else (None, None, None).
    Network error -> ('', None, None)."""
    try:
        q = addr.replace(" ", "%20")
        url = f"https://geosearch.planninglabs.nyc/v2/search?text={q}&size=1"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return "", None, None
                data = await r.json()
        feats = data.get("features") or []
        if not feats:
            return None, None, None
        feat = feats[0]
        props = feat.get("properties") or {}
        borough = (props.get("borough") or "").lower()
        if borough not in [b.lower() for b in allowed_boroughs]:
            return None, None, None
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        lat = lon = None
        if len(coords) >= 2:
            lon, lat = float(coords[0]), float(coords[1])
        label = str(props.get("label") or "") or None
        return label, lat, lon
    except Exception:  # noqa: BLE001
        return "", None, None


def _street_sides(core: str) -> list:
    return [s.strip() for s in re.split(r"\s+&\s+", core) if s.strip()]


def _street_token_groups(side: str) -> list:
    """Rare street tokens as groups of equivalent forms: an ordinal and its
    digit form ('64th'/'64') are ONE requirement - the map normalizes to the
    digit form. Every group of at least one side must hit for a street to
    verify ('Israel Ocean Parkway' passed on 'ocean' alone 9/28 12:46 PM;
    'Monticello 4 Road' matched the VILLAGE name 9/28 7:38 AM)."""
    toks = {t for t in re.split(r"[\s,.&'-]+", side.lower())
            if ((len(t) >= 4) or (len(t) == 1 and t.isalpha()))
            and t not in _ADDR_GENERIC and not t.isdigit()}
    groups = []
    for t in toks:
        m_ord = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", t)
        groups.append({t, m_ord.group(1)} if m_ord else {t})
    return groups


def _side_verifies(side: str, target: str) -> bool:
    gs = _street_token_groups(side)
    return bool(gs) and all(any(_tok_hit(v, target) for v in g) for g in gs)


async def geocode_verify(addr: str, profile: str = "") -> tuple:
    """Returns (verified, in_sullivan_county, verified_label, lat, lon, locality).
    NYC profiles: Planning Labs with the old system's borough filters (FDNY
    Brooklyn-only; Hatzalah Brooklyn/Queens/Manhattan/Bronx), Nominatim fallback.
    Sullivan: Nominatim + county check."""
    p = profile.lower()
    if "fdny" in p or "hatzalah" in p or "hatzolah" in p:
        boroughs = ["Brooklyn"] if "fdny" in p else ["Brooklyn", "Queens", "Manhattan", "Bronx", "Staten Island"]
        requested_area = addr.split(",")[1].strip().lower() if "," in addr else ""
        if addr.upper().endswith(", NJ") or (requested_area and requested_area not in
                ("brooklyn", "queens", "manhattan", "bronx", "staten island", "riverdale", "new york")):
            boroughs = []  # Non-borough NY towns must resolve with county/town-aware Nominatim.
        for q in _geocode_variants(addr, profile):
            if not boroughs:
                break  # NJ uses county-aware Nominatim; NYC search is invalid.
            label, lat, lon = await _planning_labs(q, boroughs)
            if label == "":
                break  # network failure -> Nominatim fallback
            if label:
                # reject fallback hits on a DIFFERENT street (e.g. "Ganser Road"
                # matching "Shore Road Park") - the label must share a rare
                # street token with the query, else it's not this address
                core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", q.split(",")[0]).strip().lower()
                ltok = label.lower()
                # (the query's '&' reaches PL unencoded, so intersection
                # queries geocode the LEFT street - side-aware matching is
                # what keeps 'X & Y' verifiable at all)
                sides = _street_sides(core)
                if not any(_street_token_groups(s) for s in sides):
                    # no rare token at all ('The Street' -> 'the street'):
                    # type-only chatter verifies against ANY fuzzy hit
                    # ('1 THE ST OF CULTURE' posted 6:25 AM 9/28). Short
                    # generic cores are unverifiable; longer ones must match
                    # the label verbatim.
                    if len(core.split()) <= 2 or core not in ltok:
                        logging.info("geocode: rejected generic-street fallback: %s -> %s", q, label)
                        continue
                elif not any(_side_verifies(s, ltok) for s in sides):
                    # EVERY distinctive word of one side must hit - 'Israel
                    # Ocean Parkway' verified on 'ocean' alone while 'israel'
                    # (the shul name) was ignored (bad post 9/28 12:46 PM)
                    logging.info("geocode: rejected partial-token fallback: %s -> %s", q, label)
                    continue
                found_borough = label.split(",")[1].strip() if "," in label else ""
                requested_area = addr.split(",")[1].strip() if "," in addr else ""
                if "hatzal" in p or "hatzol" in p:
                    permitted_boroughs = {
                        "brooklyn": {"brooklyn"}, "queens": {"queens"},
                        "manhattan": {"manhattan", "new york"},
                        "bronx": {"bronx"}, "riverdale": {"bronx"},
                        "staten island": {"staten island"},
                    }
                    expected = permitted_boroughs.get(requested_area.lower())
                    if expected is not None and found_borough.lower() not in expected:
                        continue
                    if requested_area.lower() in ("rockland", "monsey"):
                        continue
                return True, False, label, lat, lon, found_borough
        if "fdny" in p:
            return False, False, "", None, None, ""
        # hatzalah: fall through to Nominatim for non-NYC (5 Towns, Rockland...)
    for q in _geocode_variants(addr, profile):
        res = await _nominatim(q)
        if res is None:
            return False, False, "", None, None, ""  # network/API failure: don't burn retries
        if res:
            disp = str(res[0].get("display_name", ""))
            ad = res[0].get("address") or {}
            state = str(ad.get("state", ""))
            county_name = str(ad.get("county", ""))
            if "hatzal" in p or "hatzol" in p:
                # An explicit NJ address must resolve to Bergen County. NY hits
                # must not cross into excluded Rockland or unspecified Catskills.
                permitted = ((state in ("New York", "NY") and
                              ("Rockland" not in county_name) and
                              (not addr.upper().endswith(", NJ")) and
                              (county_name in ("Kings County", "Queens County", "New York County",
                                               "Bronx County", "Richmond County", "Sullivan County",
                                               "Nassau County") or
                               any(x in county_name for x in ("Kings", "Queens", "Bronx", "Richmond", "Sullivan", "Nassau"))))
                             or (state in ("New Jersey", "NJ") and "Bergen" in county_name
                                 and addr.upper().endswith(", NJ")))
                if not permitted:
                    logging.info("geocode: rejected outside Hatzalah coverage: %s -> %s", q, disp)
                    await asyncio.sleep(1.1)
                    continue
            # coverage gate: these channels serve NYC metro + the Catskills -
            # in-state is not enough ('3457 Northland Avenue' fuzzy-matched
            # Buffalo, 470km away, and posted to the Brooklyn group 9/28 14:26)
            try:
                _la, _lo = float(res[0].get("lat")), float(res[0].get("lon"))
                import math as _math
                def _km(a1, o1, a2, o2):
                    r = _math.pi / 180
                    h = (_math.sin((a2 - a1) * r / 2) ** 2
                         + _math.cos(a1 * r) * _math.cos(a2 * r)
                         * _math.sin((o2 - o1) * r / 2) ** 2)
                    return 6371 * 2 * _math.asin(_math.sqrt(h))
                if min(_km(_la, _lo, 40.7128, -74.0060),
                       _km(_la, _lo, 41.6556, -74.6893)) > 130:
                    logging.info("geocode: rejected out-of-coverage hit: %s -> %s", q, disp)
                    await asyncio.sleep(1.1)
                    continue
            except (TypeError, ValueError):
                pass
            core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", q.split(",")[0]).strip().lower()

            def _toks_of(side: str) -> set:
                toks = {t for t in re.split(r"[\s,.&'-]+", side)
                        if ((len(t) >= 4) or (len(t) == 1 and t.isalpha()))
                        and t not in _ADDR_GENERIC and not t.isdigit()}
                toks |= {re.sub(r"(\d+)(?:st|nd|rd|th)$", r"\1", t)
                         for t in list(toks)
                         if re.fullmatch(r"\d+(?:st|nd|rd|th)", t)}
                return toks

            typed = bool(re.search(
                r"\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|place|pl|"
                r"lane|ln|parkway|pkwy|highway|hwy|court|ct|terrace|ter|way)\b", core))
            if typed:
                # street query: the heard street must match the returned ROAD
                # component, not the locality half of the display name -
                # 'Monticello 4 Road' fuzzy-matched a house on FORESTBURGH
                # Road because 'monticello' appears as the VILLAGE (real
                # dispatch: '2 Marcel Four Road', Eldred; bad post 9/28 7:38
                # AM). And EVERY rare token of one side must hit - 'Israel
                # Ocean Parkway' passed on 'ocean' alone (9/28 12:46 PM).
                road = " ".join(str(ad.get(k) or "") for k in
                                ("road", "pedestrian", "footway", "residential",
                                 "cycleway", "path")).lower()
                if not road.strip():
                    logging.info("geocode: rejected no-road hit: %s -> %s", q, disp)
                    await asyncio.sleep(1.1)
                    continue
                ok = False
                for side in _street_sides(core):
                    if _side_verifies(side, road):
                        ok = True
                        break
                    if not _street_token_groups(side) and side and side in road:
                        ok = True
                        break
                if not ok:
                    logging.info("geocode: rejected wrong-road hit: %s -> %s (road: %s)",
                                 q, disp, road)
                    await asyncio.sleep(1.1)
                    continue
            else:
                qtoks = _toks_of(core)
                if not qtoks:
                    if len(core.split()) <= 2 or core not in disp.lower():
                        logging.info("geocode: rejected generic-street hit: %s -> %s", q, disp)
                        await asyncio.sleep(1.1)
                        continue
                elif not any(_tok_hit(t, disp.lower()) for t in qtoks):
                    logging.info("geocode: rejected wrong-street hit: %s -> %s", q, disp)
                    await asyncio.sleep(1.1)
                    continue
            county = str(ad.get("county", ""))
            locality = str(ad.get("village") or ad.get("town") or ad.get("city")
                           or ad.get("hamlet") or ad.get("borough") or "")
            # Nominatim sometimes reports NYC roads with city="New York"
            # even when county=Queens. The county is the borough evidence.
            if "hatzal" in p or "hatzol" in p:
                locality = {"Kings County": "Brooklyn", "Queens County": "Queens",
                            "New York County": "Manhattan", "Bronx County": "Bronx",
                            "Richmond County": "Staten Island"}.get(county_name, locality)
            if "fdny" in p and ("Kings" not in county_name and
                                 "Brooklyn" not in str(ad.get("borough", ""))):
                continue
            if "sullivan" in p and "Sullivan" not in county_name:
                continue
            # Explicit dispatch locality wins over a fuzzy same-road hit in
            # another city. This check is intentionally stricter for Bergen.
            requested_area = addr.split(",")[1].strip() if "," in addr else ""
            if ("hatzal" in p or "hatzol" in p) and requested_area:
                location_names = " ".join(str(ad.get(k) or "") for k in
                                          ("city", "town", "village", "hamlet", "borough", "suburb"))
                if addr.upper().endswith(", NJ") and requested_area.lower() not in location_names.lower():
                    continue
                if requested_area.lower() in ("brooklyn", "queens", "manhattan", "bronx", "staten island"):
                    county_expected = {"brooklyn": "Kings", "queens": "Queens",
                                       "manhattan": "New York", "bronx": "Bronx",
                                       "staten island": "Richmond"}[requested_area.lower()]
                    if county_expected not in county_name and requested_area.lower() not in location_names.lower():
                        continue
                if requested_area.lower() == "riverdale" and "Bronx" not in county_name:
                    continue
                if requested_area.lower() in ("rockland", "monsey"):
                    continue
                # For a named small NY locality, a permitted county alone is
                # not proof: "Corbett" must not become Franklin Square.
                # Only use a normalized exact town/hamlet token, not a
                # substring in an unrelated administrative label.
                known_boroughs = ("brooklyn", "queens", "manhattan", "bronx",
                                  "staten island", "riverdale", "new york")
                if state in ("New York", "NY") and requested_area.lower() not in known_boroughs:
                    names = [str(ad.get(k) or "").lower() for k in
                             ("city", "town", "village", "hamlet", "suburb")]
                    normalized = [re.sub(r"^(?:village|town|city|hamlet) of\s+", "", x).strip()
                                  for x in names if x]
                    if requested_area.lower() not in normalized:
                        continue
            lat = lon = None
            try:
                lat, lon = float(res[0].get("lat")), float(res[0].get("lon"))
            except (TypeError, ValueError):
                pass
            return True, ("Sullivan" in county or "Sullivan County" in disp), disp, lat, lon, locality
        await asyncio.sleep(1.1)  # nominatim 1 req/s
    return False, False, "", None, None, ""


_OVERPASS_EPS = ("https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter",
                 "https://overpass.private.coffee/api/interpreter")


async def _intersection_point(address: str, cross: str) -> tuple:
    """Bare-street verification: the heard street truly crosses a spoken cross
    street (shared OSM way node) -> (lat, lon) of a shared node, else
    (None, None). '15th & 16th Avenue' shares its suffix with the bare side."""
    street = re.sub(r"[,.;].*$", "", address).strip()
    parts = [p.strip() for p in (cross or "").split("&", 1) if p.strip()]
    if not street or not parts:
        return None, None
    _T = r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Place|Pl|Lane|Ln|Parkway|Pkwy|Court|Ct|Terrace|Ter)"
    # A dispatcher may omit the first suffix ("Coleridge and Hampton Avenue").
    # Try plausible typed variants; verify by an ACTUAL shared OSM node,
    # rather than trusting a fuzzy hit on the second street alone.
    alt = []
    for p in ([street] + parts if "&" not in street else street.split("&", 1)):
        p = p.strip()
        # OSM uses full street types; the FDNY parser often abbreviates them.
        p = re.sub(r"\b(St|Ave|Rd|Blvd|Dr|Pl|Ln|Pkwy|Ct|Ter)$",
                   lambda m: {"st":"Street", "ave":"Avenue", "rd":"Road",
                              "blvd":"Boulevard", "dr":"Drive", "pl":"Place",
                              "ln":"Lane", "pkwy":"Parkway", "ct":"Court",
                              "ter":"Terrace"}[m.group(1).lower()], p, flags=re.I)
        if re.search(rf"\b{_T}\b", p, re.I):
            alt.append([p])
        else:
            alt.append([f"{p} {suffix}" for suffix in
                        ("Street", "Avenue", "Road", "Boulevard", "Place",
                         "Drive", "Court", "Terrace", "Lane")])
    names = list(dict.fromkeys([x for group in alt for x in group]))
    pat = "^(" + "|".join(re.escape(n) for n in names) + ")$"
    hdrs = {"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"}
    # The old Brooklyn-only bbox silently rejected Fair Lawn and Queens.
    # Use the spoken region to search the appropriate map; a NJ candidate
    # remains subject to Bergen County verification by the address geocoder.
    area = address.lower()
    bbox = ("40.75,-74.30,41.13,-73.87" if area.endswith(", nj") else
            "41.35,-75.10,42.00,-74.25" if "sullivan" in area or any(
                n in area for n in ("monticello", "fallsburg", "woodridge", "liberty")) else
            "40.48,-74.26,40.94,-73.70")
    q = f'[out:json][timeout:15];way["name"~"{pat}",i]({bbox});out geom;'
    data = None
    for ep in _OVERPASS_EPS:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(ep, data={"data": q}, headers=hdrs,
                                  timeout=aiohttp.ClientTimeout(total=18)) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    break
        except Exception:  # noqa: BLE001
            continue
    if data is None:
        return None, None
    nodes: dict = {}
    for el in data.get("elements") or []:
        nm = (el.get("tags") or {}).get("name", "").strip().lower()
        for g in el.get("geometry") or []:
            nodes.setdefault(nm, {})[(round(g.get("lat", 0), 6),
                                      round(g.get("lon", 0), 6))] = (g.get("lat"), g.get("lon"))
    if "&" in street:
        # Address itself is the intersection: both sides must meet spatially.
        for left in alt[0]:
            own = nodes.get(left.strip().lower()) or {}
            for right in alt[1]:
                other = nodes.get(right.strip().lower()) or {}
                shared = set(own) & set(other)
                if shared:
                    return own[sorted(shared)[0]]
                # OSM splits crossing ways at independently rounded nodes on
                # map exports; tight ~25m snap is acceptable when map names
                # identify both roads, never one road alone.
                for a in own.values():
                    for z in other.values():
                        if abs(a[0] - z[0]) < 0.00017 and abs(a[1] - z[1]) < 0.00023:
                            return ((a[0]+z[0])/2, (a[1]+z[1])/2)
        return None, None
    own = nodes.get(street.lower()) or {}
    if not own:
        return None, None
    for p in names[1:]:
        shared = set(own) & set(nodes.get(p.lower()) or {})
        if shared:
            return own[sorted(shared)[0]]
    return None, None

async def _correct_street_via_crosses(heard_addr: str, cross: str) -> str:
    """User rule 9/28: when the heard street can't be confirmed but the cross
    streets are known, the real street is the one that truly crosses BOTH -
    fuzzy-match its map name against the heard name ('4-0 Haywood' + crosses
    Bedford/Wythe -> '40 Heyward Street'). Returns the corrected address, or
    '' when the intersection evidence doesn't pin it (keep 'not confirmed')."""
    import difflib
    parts = [p.strip() for p in (cross or "").split("&", 1)]
    if len(parts) != 2 or not all(parts):
        return ""
    hdrs = {"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"}

    async def _ov(q: str, timeout: int = 15):
        for ep in _OVERPASS_EPS:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(ep, data={"data": q}, headers=hdrs,
                                      timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                        if r.status != 200:
                            continue
                        return await r.json()
            except Exception:  # noqa: BLE001
                continue
        return None

    heard_core = re.sub(r"^\s*\d+(?:-\d+)?[A-Za-z]?\s+", "", heard_addr)
    heard_core = re.sub(r"[,.;].*$", "", heard_core).strip().lower()
    if not heard_core:
        return ""
    pat = "^(" + "|".join(re.escape(p) for p in parts) + ")$"
    d1 = await _ov(f'[out:json][timeout:15];way["name"~"{pat}",i]'
                   f'(40.55,-74.06,40.75,-73.85);out geom;')
    cross_nodes = []
    for want in parts:
        nodes = set()
        for el in (d1 or {}).get("elements") or []:
            nm = (el.get("tags") or {}).get("name", "").strip().lower()
            if nm != want.lower():
                continue
            for g in el.get("geometry") or []:
                nodes.add((round(g.get("lat", 0), 6), round(g.get("lon", 0), 6)))
        if not nodes:
            return ""
        cross_nodes.append(nodes)
    allpts = [p for ns in cross_nodes for p in ns]
    la = [p[0] for p in allpts]
    lo = [p[1] for p in allpts]
    bbox = f"{min(la)-0.008},{min(lo)-0.008},{max(la)+0.008},{max(lo)+0.008}"
    d2 = await _ov(f'[out:json][timeout:20];way[highway][name]({bbox});out geom;',
                   timeout=24)
    best = (0.0, "")
    for el in (d2 or {}).get("elements") or []:
        nm = (el.get("tags") or {}).get("name", "").strip()
        if not nm or nm.lower() in (parts[0].lower(), parts[1].lower()):
            continue
        nset = {(round(g.get("lat", 0), 6), round(g.get("lon", 0), 6))
                for g in el.get("geometry") or []}
        if not nset or any(not (nset & ns) for ns in cross_nodes):
            continue  # must truly cross BOTH cross streets
        score = difflib.SequenceMatcher(None, heard_core, nm.lower()).ratio()
        if nm.lower()[:1] == heard_core[:1] and score > best[0]:
            best = (score, nm)
    if best[0] < 0.70 or not best[1]:
        logging.info("cross-correction: no street pinning '%s' via [%s] (best %.2f)",
                     heard_addr, cross, best[0])
        return ""
    tok = heard_addr.strip().split(" ", 1)[0]
    if re.fullmatch(r"\d+-\d+", tok):
        num = tok.replace("-", "")  # whisper '4-0' = '40'
    elif re.fullmatch(r"\d+[A-Za-z]?", tok):
        num = tok
    else:
        num = ""
    mtail = re.search(r",\s*(.*)$", heard_addr)
    corrected = (f"{num} " if num else "") + best[1] + (", " + mtail.group(1) if mtail else "")
    logging.info("cross-correction candidate: '%s' + [%s] -> '%s' (score %.2f)",
                 heard_addr, cross, corrected, best[0])
    return corrected


async def _cross_streets(lat: float, lon: float, address: str) -> tuple:
    """Cross streets via Overpass (free, keyless): ways sharing a node with the
    job's own street truly cross it. Returns (crosses, exact) - ('A & B', True),
    or ('A & B', False) when falling back to nearest streets, or (None, False)."""
    import math
    q = (f'[out:json][timeout:15];way(around:250,{lat},{lon})'
         f'[highway][name];out tags geom;')
    hdrs = {"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"}
    data = None
    for attempt in (1, 2):  # one retry pass: Overpass rate-limits bursts
        for endpoint in _OVERPASS_EPS:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(endpoint, data={"data": q}, headers=hdrs,
                                      timeout=aiohttp.ClientTimeout(total=18)) as r:
                        if r.status != 200:
                            continue
                        data = await r.json()
                        break
            except Exception:  # noqa: BLE001
                continue
            if data is not None:
                break
        if data is not None:
            break
        await asyncio.sleep(3)
    if data is None:
        return None, False
    skip_hw = {"service", "footway", "path", "track", "cycleway", "pedestrian",
               "steps", "construction", "proposed", "corridor", "bus_stop"}
    own = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", address).strip().lower()
    own = re.sub(r"[,.;].*$", "", own).strip()
    cos_lat = math.cos(math.radians(lat))

    def _dist2(geom):
        return min(((g.get("lon", lon) - lon) * cos_lat * 111320) ** 2 +
                   ((g.get("lat", lat) - lat) * 110540) ** 2 for g in geom)

    own_nodes = set()
    cands = []
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        hw = tags.get("highway")
        geom = el.get("geometry") or []
        if not name or hw in skip_hw or not geom:
            continue
        nl = name.lower().strip()
        is_own = (nl == own or (len(own) >= 6 and own in nl)
                  or (len(nl) >= 6 and nl in own))
        if is_own:
            for g in geom:
                own_nodes.add((round(g.get("lat", 0), 6), round(g.get("lon", 0), 6)))
        else:
            cands.append((name, geom))
    rows = {}
    for name, geom in cands:
        crosses = any((round(g.get("lat", 0), 6), round(g.get("lon", 0), 6)) in own_nodes
                      for g in geom)
        d2 = _dist2(geom)
        nl = name.lower()
        if nl not in rows or (crosses and not rows[nl][1]) or d2 < rows[nl][0]:
            rows[nl] = (d2, crosses, name)
    if not rows:
        return None, False
    exact = sorted((v for v in rows.values() if v[1]))
    approx = sorted((v for v in rows.values() if not v[1]))
    if len(exact) >= 2:
        return f"{exact[0][2]} & {exact[1][2]}", True
    if len(exact) == 1 and approx:
        return f"{exact[0][2]} & {approx[0][2]}", True
    if len(approx) >= 2:
        return f"{approx[0][2]} & {approx[1][2]}", False
    return None, False


async def _map_street_names(lat: float, lon: float, street: str = "") -> set:
    """Canonical street-name pool for fixing whisper-mangled names ('Nickabocker'
    -> 'Knickerbocker'). Primary: every street crossing the incident street - a
    wrong house number can put the geocoded point far from the spoken crosses,
    so a point-radius pool alone misses them. Fallback: names around the point.
    Overpass is free/keyless; failures just skip canonicalization."""
    hdrs = {"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"}
    eps = _OVERPASS_EPS

    async def _ov(q: str):
        for endpoint in eps:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(endpoint, data={"data": q}, headers=hdrs,
                                      timeout=aiohttp.ClientTimeout(total=12)) as r:
                        if r.status != 200:
                            continue
                        return await r.json()
            except Exception:  # noqa: BLE001
                continue
        return None

    async def _build() -> set:
        pool: set = set()
        if street:
            pat = re.escape(street.strip())
            d1 = await _ov(f"[out:json][timeout:10];way(around:3000,{lat},{lon})"
                           f"[highway][name~\"^{pat}$\",i];node(w);out ids;")
            ids = [str(e["id"]) for e in (d1 or {}).get("elements") or [] if e.get("id")]
            if ids:
                d2 = await _ov(f"[out:json][timeout:10];node(id:{','.join(ids)})->.n;"
                               f"way(bn.n)[highway][name];out tags;")
                pool |= {(el.get("tags") or {}).get("name", "").strip()
                         for el in (d2 or {}).get("elements") or []
                         if (el.get("tags") or {}).get("name")}
        if not pool:
            d3 = await _ov(f"[out:json][timeout:10];way(around:800,{lat},{lon})[highway][name];out tags;")
            pool |= {(el.get("tags") or {}).get("name", "").strip()
                     for el in (d3 or {}).get("elements") or []
                     if (el.get("tags") or {}).get("name")}
        return pool

    try:
        return await asyncio.wait_for(_build(), timeout=30)
    except Exception:  # noqa: BLE001 - never delay an alert over spelling polish
        return set()


def _canon_name(name: str, pool: set) -> str:
    """Fuzzy-normalize a (possibly whisper-mangled) street name to the
    map-canonical spelling from the local pool. Conservative: only replaces
    on a close confident match, otherwise keeps the original."""
    import difflib
    nl = name.lower().strip()
    if not nl or not pool:
        return name
    best, best_r = None, 0.0
    for cand in pool:
        r = difflib.SequenceMatcher(None, nl, cand.lower()).ratio()
        if r > best_r:
            best, best_r = cand, r
    if best and best_r >= 0.75 and best.lower() != nl:
        return best
    return name


BOX_CACHE_FILE = SEG_DIR / "box_cache.json"


def _load_box_cache() -> dict:
    try:
        return json.loads(BOX_CACHE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_box_cache(c: dict) -> None:
    try:
        BOX_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BOX_CACHE_FILE.write_text(json.dumps(c))
    except Exception:  # noqa: BLE001
        pass


_SOCRATA_BOX = "https://data.cityofnewyork.us/resource/v57i-gtxb.json"
_BORO_PREFIX = {"B": "Brooklyn", "M": "Manhattan", "Q": "Queens",
                "X": "Bronx", "R": "Staten Island"}


async def _box_lookup_socrata(box4: str) -> list:
    """FDNY box -> [(location, borough), ...] from the NYC Open Data
    'In-Service Alarm Box Locations' dataset (v57i-gtxb). Numbering verified
    identical to fdnewyork dispatch boxes (B2393='AVENUE M & E 84 ST')."""
    codes = ",".join(f"'{p}{box4}'" for p in _BORO_PREFIX)
    url = (f"{_SOCRATA_BOX}?$select=borobox,location&$where=borobox in({codes})"
           f"&$limit=10")
    rows: list = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"User-Agent": "fdny-slim/1.0"},
                             timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status != 200:
                    return []
                data = await r.json()
        for rec in data:
            code = rec.get("borobox") or ""
            loc = (rec.get("location") or "").strip()
            boro = _BORO_PREFIX.get(code[:1], "")
            if loc and boro:
                rows.append((loc, boro))
    except Exception as e:  # noqa: BLE001
        logging.warning("socrata box lookup failed for %s: %s", box4, e)
        return []
    return rows


async def _nearest_box(lat: float, lon: float, borough: str = "") -> tuple:
    """Address -> closest FDNY box (user rule 9/28: no heard box -> look up
    the closest box to the address). Radius-ordered Socrata query; returns
    (box_digits, location, distance_m) or (None, None, None)."""
    import urllib.parse
    boro_filter = ""
    if borough and borough.lower() in ("brooklyn", "queens", "manhattan", "bronx", "staten island"):
        boro_filter = f" AND borough='{borough.title()}'"
    where = (f"within_circle(location_point,{lat},{lon},500){boro_filter}")
    order = f"distance_in_meters(location_point,'POINT({lon} {lat})')"
    url = (f"{_SOCRATA_BOX}?$select=borobox,location"
           f"&$where={urllib.parse.quote(where)}"
           f"&$order={urllib.parse.quote(order)}&$limit=1")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"User-Agent": "fdny-slim/1.0"},
                             timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status != 200:
                    return None, None, None
                data = await r.json()
        if data:
            code = data[0].get("borobox") or ""
            return code[1:], (data[0].get("location") or "").strip(), None
    except Exception as e:  # noqa: BLE001
        logging.warning("nearest box lookup failed: %s", e)
    return None, None, None


async def _box_lookup(box4: str) -> list:
    """FDNY box -> location rows from fdnewyork.com/getbox.asp (the user's named
    source). Boxes are per-borough; returns [(location, borough), ...].
    Cached forever on disk - box geography is static, so each unique box costs
    the site exactly one request."""
    import urllib.parse
    import urllib.request
    cache = _load_box_cache()
    if box4 in cache:
        return [tuple(r) for r in cache[box4]]
    rows: list = await _box_lookup_socrata(box4)
    if rows:
        cache[box4] = rows
        _save_box_cache(cache)
        return rows
    try:
        data = urllib.parse.urlencode({"action": "Save Form Data", "id": box4}).encode()
        req = urllib.request.Request(
            "https://www.fdnewyork.com/getbox.asp", data=data,
            headers={"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"})

        def _fetch():
            with urllib.request.urlopen(req, timeout=12) as r:
                return r.read().decode("utf-8", "replace")

        html_txt = await asyncio.to_thread(_fetch)
        for m in re.finditer(
                r"<td class=\w+>(\d{4})</td><td class=\w+>([^<]+)</td><td class=\w+>\s*([^<]+?)\s*</td>",
                html_txt):
            if m.group(1) == box4:
                rows.append((m.group(2).strip(), m.group(3).strip()))
    except Exception as e:  # noqa: BLE001
        logging.warning("box lookup failed for %s: %s", box4, e)
        return []
    cache[box4] = rows
    _save_box_cache(cache)
    return rows


def _box_address_correction(heard_addr: str, rows: list) -> str:
    """Box-supported address correction for the whisper ordinal digit-drop:
    heard '1238 East 4th Street' (or bare 'East 4th Street'), box row side
    'E 84 ST' -> 'East 84th Street, Brooklyn, NY' when the shapes line up:
    same direction prefix, same street type, and the heard ordinal's digits
    are a strict suffix of the row ordinal's digits ('4' in '84'). Returns ''
    when no row side supports a correction - never guesses."""
    _DIR = {"e": "East", "w": "West", "n": "North", "s": "South",
            "east": "East", "west": "West", "north": "North", "south": "South"}
    m = re.match(r"^\s*(\d+\s+)?(?:(east|west|north|south|e|w|n|s)\s+)?"
                 r"(\d+)(?:st|nd|rd|th)?\s+(street|st|avenue|ave|road|rd|boulevard|blvd)",
                 heard_addr, re.I)
    if not m:
        return ""
    house = (m.group(1) or "").strip()
    heard_dir = (m.group(2) or "").lower()
    heard_num = m.group(3)
    heard_type = m.group(4).lower()
    heard_type = {"st": "street", "ave": "avenue", "rd": "road", "blvd": "boulevard"}.get(
        heard_type, heard_type)
    tail = ""
    mt = re.search(r",\s*(.*)$", heard_addr)
    if mt:
        tail = ", " + mt.group(1)
    for loc, _borough in rows:
        for side in re.split(r"\s+at\s+|&", loc):
            sm = re.match(r"^\s*(?:(east|west|north|south|e|w|n|s)\s+)?"
                          r"(\d+)(?:st|nd|rd|th)?\s*(street|st|avenue|ave|road|rd|boulevard|blvd)?",
                          side, re.I)
            if not sm:
                continue
            row_dir = (sm.group(1) or "").lower()
            row_num = sm.group(2)
            row_type = (sm.group(3) or heard_type).lower()
            row_type = {"st": "street", "ave": "avenue", "rd": "road",
                        "blvd": "boulevard"}.get(row_type, row_type)
            _FULL = {"e": "east", "w": "west", "n": "north", "s": "south"}
            if (_FULL.get(heard_dir, heard_dir) != _FULL.get(row_dir, row_dir)
                    or heard_type != row_type):
                continue
            if len(row_num) > len(heard_num) and row_num.endswith(heard_num):
                direction = _DIR.get(row_dir, "")
                n = int(row_num)
                suf = ("th" if 10 <= n % 100 <= 20
                       else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))
                type_disp = {"street": "Street", "avenue": "Avenue", "road": "Road",
                             "boulevard": "Boulevard"}.get(row_type, row_type.title())
                street = f"{direction + ' ' if direction else ''}{row_num}{suf} {type_disp}"
                corrected = f"{house + ' ' if house else ''}{street}{tail}"
                logging.info("box address correction: '%s' -> '%s' (row '%s')",
                             heard_addr, corrected, loc)
                return corrected
    return ""


def _box_row_matches_address_and_cross(location: str, address: str, crosses: str) -> bool:
    """Box row 'SURF AVE at W 25 ST' corroborates the spoken W 25th
    address + Surf cross. Ordinal '25th' and source '25' are same street;
    'W' and 'West' are the same direction. Never compare mere city tokens.
    """
    def canon(street: str) -> str:
        t = street.lower().strip()
        t = re.sub(r"\bwest\b", "w", t)
        t = re.sub(r"\beast\b", "e", t)
        t = re.sub(r"\bnorth\b", "n", t)
        t = re.sub(r"\bsouth\b", "s", t)
        t = re.sub(r"\bavenue\b", "ave", t)
        t = re.sub(r"\bstreet\b", "st", t)
        t = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", t)
        return re.sub(r"\s+", " ", t).strip()
    row_sides = [canon(x) for x in re.split(r"\s+at\s+|\s*&\s*", location, flags=re.I)]
    own = canon(re.sub(r"^\d+\s+", "", address.split(",", 1)[0]))
    cross_sides = [canon(x) for x in re.split(r"\s*&\s*", crosses) if x.strip()]
    return bool(own and cross_sides and own in row_sides and any(x in row_sides for x in cross_sides))


def _heard_box(excerpt: str) -> str | None:
    # user ruling 9/28 13:36: 'class 3 2584' digits are an ALARM readout, not a
    # box ('it can come over as a class 3... but the box is wrong') - only a
    # spoken 'box NNNN' counts as a heard box
    m = re.search(r"\bbox\s+(\d{1,4})\b", excerpt or "", re.I)
    return m.group(1).zfill(4) if m else None


RECENT_FILE = Path(os.environ.get("RECENT_FILE", "./segments/recent_posts.json"))
_INCIDENT_DEDUP_SEC = 600
_ADDR_GENERIC = {"street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd",
                 "place", "pl", "drive", "dr", "lane", "ln", "parkway", "pkwy", "court",
                 "ct", "east", "west", "north", "south", "ny", "brooklyn", "new", "york",
                 "queens", "manhattan", "bronx", "and", "the", "between", "county", "co", "sullivan", "nassau", "bergen", "kings", "richmond", "thompson", "monticello", "parksville", "cedarhurst", "fallsburg", "loch", "sheldrake"}


def _tok_hit(tok: str, haystack: str) -> bool:
    """Token match on word boundaries: single-letter/short street tokens
    ('m' from 'Avenue M') must not substring-match inside other words
    ('Manhattan Ave' is not 'Avenue M')."""
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])",
                          haystack))


def _rare_tokens(addr: str) -> set:
    return {t for t in re.split(r"[\s,.&'-]+", addr.lower())
            if len(t) >= 4 and t not in _ADDR_GENERIC and not t.isdigit()}


def _street_core(addr: str) -> str:
    """Normalized primary street: '535 4th Ave, Brooklyn' -> '4th ave';
    '4TH AVE at 13 ST' -> '4th ave'."""
    s = re.split(r"\s+at\s+|,|&", addr.lower())[0]
    s = re.sub(r"^\s*\d+(?:[A-Za-z])?\s+", "", s).strip()
    s = re.sub(r"\b(avenue|ave)\b", "ave", s)
    s = re.sub(r"\b(street|st)\b", "st", s)
    s = re.sub(r"\b(road|rd)\b", "rd", s)
    s = re.sub(r"\b(boulevard|blvd)\b", "blvd", s)
    return re.sub(r"\s+", " ", s)


def _load_recent() -> list:
    try:
        data = json.loads(RECENT_FILE.read_text())
        now = time.time()
        return [r for r in data if now - r.get("t", 0) < _INCIDENT_DEDUP_SEC]
    except Exception:  # noqa: BLE001
        return []


def _save_recent(rows: list) -> None:
    try:
        RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RECENT_FILE.write_text(json.dumps(rows[-50:]))
    except Exception:  # noqa: BLE001
        pass


async def verify_and_send(profile: str, hit: dict, stats, clip_name: str | None = None,
                            fresh_ts: float | None = None,
                            audio_ts: float | None = None, spoken_time: str = "") -> str:
    """User's posting rules (9/28): verified addresses only; Sullivan feed posts
    only Sullivan-County-verified addresses; unverifiable posts marked not confirmed.
    Returns 'sent' | 'queued' | 'suppressed'."""
    now = time.time()
    if profile in control.muted_feeds():
        logging.info("[%s] suppressed (feed muted): %s @ %s", profile, hit["nature"], hit["address"])
        stats.event(profile, f"suppressed (feed muted): {hit['nature']} @ {hit['address']}")
        ops_log(f"suppressed (feed muted): {hit['nature']} @ {hit['address']}")
        return "suppressed"
    if fresh_ts:
        fresh_limit = FRESH_FDNY_SEC if profile == "fdny" else FRESH_LIVE_SEC
        age = time.time() - fresh_ts
        if age > fresh_limit:
            logging.info("[%s] suppressed (stale, %.0fm old, limit %dm): %s @ %s",
                         profile, age / 60, fresh_limit / 60, hit["nature"], hit["address"])
            stats.event(profile, f"suppressed (stale, {age / 60:.0f}m old): {hit['nature']} @ {hit['address']}")
            ops_log(f"suppressed (stale, {age / 60:.0f}m old): {hit['nature']} @ {hit['address']}")
            return "suppressed"
    nat_norm = (hit.get("nature") or "").strip().lower()
    toks = _rare_tokens(hit["address"])
    if nat_norm and toks:
        for r in _load_recent():
            if r.get("nature") == nat_norm and toks & set(r.get("tokens") or []):
                logging.info("[%s] suppressed (duplicate incident): %s @ %s",
                             profile, hit["nature"], hit["address"])
                stats.event(profile, f"suppressed (dup incident): {hit['nature']} @ {hit['address']}")
                ops_log(f"suppressed (dup incident): {hit['nature']} @ {hit['address']}")
                return "suppressed"
    if re.match(r"^FDNY Box \d+", hit["address"]) and not hit.get("box_only"):
        logging.info("[%s] suppressed (bare box, no street address): %s", profile, hit["address"])
        stats.event(profile, f"suppressed (bare box): {hit['address']}")
        ops_log(f"suppressed (bare box): {hit['address']}")
        return "suppressed"
    if not (hit.get("nature") or "").strip():
        logging.info("[%s] suppressed (no discernible nature): %s", profile, hit["address"])
        stats.event(profile, f"suppressed (no nature): {hit['address']}")
        ops_log(f"suppressed (no nature): {hit['address']}")
        return "suppressed"
    if profile.lower().startswith(("hatzalah", "zello-hatzalah")) and \
            (hit.get("nature") or "").strip().lower() in control.excluded_natures():
        logging.info("[%s] suppressed (Hatzalah %s excluded): %s", profile, hit.get("nature"), hit["address"])
        stats.event(profile, f"suppressed ({hit.get('nature')} excluded): {hit['address']}")
        ops_log(f"suppressed ({hit.get('nature')} excluded): {hit['address']}")
        return "suppressed"
    box_task = None
    if not profile.lower().startswith(("sullivan", "zello-sullivan")):
        heard = hit.get("box_heard") or _heard_box(hit.get("excerpt") or "")
        if heard:
            box_task = asyncio.create_task(_box_lookup(heard))
    ogg_task = None
    if clip_name:
        # Convert the voice note concurrently with geocode/canonicalization so
        # text and audio can post back-to-back (user rule 9/28: "Job has to be
        # posted same second as audio"). Conversion is ~1-2s, verification is
        # usually slower, so the text post is not delayed.
        ogg_task = asyncio.create_task(asyncio.to_thread(_ensure_ogg, clip_name))
    verified = True
    verified_label = ""
    lat = lon = None
    locality = ""
    if profile.lower().startswith(("hatzalah", "zello-hatzalah")) and re.search(
            r"\b(?:rockland|monsey|spring valley|new square|suffern|"
            r"haverstraw|garnerville|airmont|chestnut ridge)\b",
            hit.get("excerpt") or "", re.I):
        stats.event(profile, f"suppressed (Rockland dispatch): {hit['address']}")
        return "suppressed"
    if hit.get("terminal_street_box_correlated"):
        # A user's specific reading of this garbled dispatch is still gated
        # by independent map and NYC box corroboration before any post.
        box_num = hit.get("box_heard") or ""
        rows = await _box_lookup(box_num) if box_num else []
        exact_row = any(boro == "Brooklyn" and "53 ST" in loc.upper()
                        and "9 AVE" in loc.upper() for loc, boro in rows)
        if not exact_row:
            stats.event(profile, "suppressed (terminal street box mismatch)")
            return "suppressed"
    if hit.get("box_only"):
        # A terminal-ID dispatch with no trustworthy spoken street may use
        # the verified Brooklyn box location as its address anchor. Never
        # invent a house number or let a box from another borough through.
        heard_box = hit.get("box_heard") or ""
        box_rows = await _box_lookup(heard_box) if heard_box else []
        brooklyn_rows = [place for place, boro in box_rows if boro == "Brooklyn"]
        if len(brooklyn_rows) != 1:
            stats.event(profile, f"suppressed (box-only location unverified): {heard_box}")
            return "suppressed"
        box_place = brooklyn_rows[0]
        sides = [p.strip() for p in re.split(r"\s+at\s+|&", box_place, flags=re.I)]
        if len(sides) != 2 or not all(sides):
            stats.event(profile, f"suppressed (box-only location incomplete): {heard_box}")
            return "suppressed"
        # The spoken 8th/9th corridor must corroborate at least one side of
        # the box location. Generic area words don't count as a match.
        said = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", hit.get("cross") or "", flags=re.I)
        listed = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", box_place, flags=re.I)
        if not said or not any(re.search(r"\b" + re.escape(x) + r"\b", listed, re.I)
                               for x in re.findall(r"\b\d{1,2}\b", said)):
            stats.event(profile, f"suppressed (box-only crosses uncorroborated): {heard_box}")
            return "suppressed"
        def box_side_name(raw):
            p = raw.strip().lower()
            p = re.sub(r"\b(\d{1,3})\b", lambda m:
                       str(int(m.group(1))) + ("th" if 11 <= int(m.group(1)) % 100 <= 13
                           else "st" if int(m.group(1)) % 10 == 1
                           else "nd" if int(m.group(1)) % 10 == 2
                           else "rd" if int(m.group(1)) % 10 == 3 else "th"), p)
            p = re.sub(r"\bave\b", "Avenue", p, flags=re.I)
            p = re.sub(r"\bst\b", "Street", p, flags=re.I)
            return p.title().replace("Th ", "th ").replace("St ", "st ").replace("Nd ", "nd ").replace("Rd ", "rd ")
        candidate = f"{box_side_name(sides[0])} & {box_side_name(sides[1])}, Brooklyn, NY"
        lat, lon = await _intersection_point(candidate, box_side_name(sides[1]))
        if lat is None:
            stats.event(profile, f"suppressed (box-only intersection unverified): {heard_box}")
            return "suppressed"
        hit["address"] = candidate
        hit["cross"] = ""
        stats.event(profile, f"box-only verified address from Brooklyn Box {heard_box}: {candidate}")
        verified_label, locality = candidate, "Brooklyn"
    if GEOCODE_VERIFY and not hit.get("box_only"):
        # Intersections require BOTH spoken roads at one point. The ordinary
        # geocoder can otherwise certify the first street only.
        spoken_location = hit["address"].split(",")[0]
        if " & " in spoken_location and not re.match(r"^\d+\s", spoken_location):
            side_a, side_b = (p.strip() for p in spoken_location.split("&", 1))
            lat, lon = await _intersection_point(hit["address"], side_b)
            verified = lat is not None
            # Spatially constrained road-name intersection. If map service
            # is unavailable, verified stays false and alert is suppressed.
            verified_label = hit["address"] if verified else ""
            locality = hit["address"].split(",")[1].strip() if verified and "," in hit["address"] else ""
        else:
            verified, in_sullivan, verified_label, lat, lon, locality = await geocode_verify(hit["address"], profile)
        if (verified and locality and profile.lower().startswith(("hatzalah", "zello-hatzalah"))
                and locality.lower() not in ("brooklyn", "queens", "manhattan", "bronx", "new york", "staten island")):
            state_suffix = "NJ" if hit["address"].upper().endswith(", NJ") else "NY"
            fixed = re.sub(r",\s*[^,]+,\s*(?:NY|NJ)$", f", {locality}, {state_suffix}", hit["address"])
            if fixed != hit["address"]:
                logging.info("[%s] area corrected by geocode: %s -> %s", profile, hit["address"], fixed)
                stats.event(profile, f"area corrected: {hit['address']} -> {fixed}")
                hit["address"] = fixed
        if profile.lower().startswith(("hatzalah", "zello-hatzalah")):
            # The dispatch explicitly names an excluded chapter. Never let a
            # generic street geocode in Brooklyn override that place name.
            if re.search(r"\b(?:rockland|monsey|spring valley|new square|suffern|"
                         r"haverstraw|garnerville|airmont|chestnut ridge)\b",
                         hit.get("excerpt") or "", re.I):
                stats.event(profile, f"suppressed (Rockland dispatch): {hit['address']}")
                return "suppressed"
        if profile == "sullivan" and verified and not in_sullivan:
            logging.info("[%s] suppressed (verified outside Sullivan Co): %s", profile, hit["address"])
            stats.event(profile, f"suppressed (outside Sullivan Co): {hit['nature']} @ {hit['address']}")
            ops_log(f"suppressed (outside Sullivan Co): {hit['nature']} @ {hit['address']}")
            return "suppressed"
        if not verified:
            stats.event(profile, f"unconfirmed address: {hit['address']}")
    # A directly spoken X and Y pair: keep the verified first street if the
    # map cannot prove the second at a real intersection. The map-verification
    # result controls the printed second side; no fuzzy substitution.
    direct_candidate = (hit.get("direct_cross_candidate") or "").strip()
    if direct_candidate and verified:
        pair_point = await _intersection_point(hit["address"], direct_candidate)
        if pair_point[0] is not None:
            hit["address"] = hit["address"].replace(
                hit["address"].split(",", 1)[0],
                f"{hit['address'].split(',', 1)[0]} & {direct_candidate}", 1)
            lat, lon = pair_point
            stats.event(profile, f"spoken intersection map-verified: {hit['address']}")
        else:
            stats.event(profile, f"spoken second street unverified: {direct_candidate}")
    cross = (hit.get("cross") or "").strip()
    if " & " in hit["address"].split(",")[0] and cross.lower() == hit["address"].split(",")[0].lower():
        cross = ""  # the spoken intersection already IS the location line
    if cross and "&" not in cross and lat is not None and lon is not None \
            and verified_label:
        # single spoken cross ('off Woodbine Street') - complete the pair
        # from the map, spoken side first
        comp, _exact = await _cross_streets(lat, lon, hit["address"])
        if comp:
            spoken = cross.strip().lower()
            other = [p.strip() for p in comp.split("&")
                     if p.strip() and p.strip().lower() != spoken]
            if other:
                cross = f"{cross} & {other[0]}"
                stats.event(profile, f"cross completed from map: {cross}")
    if not cross and lat is not None and lon is not None and verified_label:
        street_core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", hit["address"])
        street_core = re.sub(r"[,.;].*$", "", street_core).strip().lower()
        if street_core and street_core in verified_label.lower():
            cross, exact = await _cross_streets(lat, lon, hit["address"])
            cross = cross or ""
            if cross:
                tag = "computed" if exact else "approx"
                stats.event(profile, f"cross streets ({tag}): {cross}")
    if cross and lat is not None and lon is not None and verified_label:
        core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", hit["address"].split(",")[0]).strip()
        pool = await _map_street_names(lat, lon, core)
        if pool:
            parts = [p.strip() for p in cross.split("&", 1)]
            canon = [_canon_name(p, pool) for p in parts]
            new_cross = " & ".join(canon)
            if new_cross != cross:
                logging.info("[%s] crosses canonicalized: %s -> %s", profile, cross, new_cross)
                stats.event(profile, f"crosses canonicalized: {cross} -> {new_cross}")
                cross = new_cross
            canon_core = _canon_name(core, pool)
            if canon_core != core:
                fixed_addr = hit["address"].replace(core, canon_core, 1)
                logging.info("[%s] address canonicalized: %s -> %s", profile, hit["address"], fixed_addr)
                stats.event(profile, f"address canonicalized: {hit['address']} -> {fixed_addr}")
                hit["address"] = fixed_addr
    if (not verified and cross and GEOCODE_VERIFY
            and not re.match(r"^\s*\d", hit["address"])):
        # bare street ('53rd Street' + crosses '15th & 16th Avenue') - the
        # spoken intersection itself is the place; verify it on the map
        pt = await _intersection_point(hit["address"], cross)
        if pt[0] is not None:
            lat, lon = pt
            verified = True
            verified_label = re.sub(r",", f" at {cross.split('&', 1)[0].strip()},",
                                    hit["address"], count=1)
            mloc = re.search(r",\s*([A-Za-z ]+),\s*NY", hit["address"])
            locality = mloc.group(1).strip() if mloc else locality
            stats.event(profile, f"verified via intersection (map): {verified_label}")
    if not verified and cross and GEOCODE_VERIFY:
        corrected = await _correct_street_via_crosses(hit["address"], cross)
        if corrected and corrected.lower() != hit["address"].lower():
            v2, ins2, lbl2, la2, lo2, loc2 = await geocode_verify(corrected, profile)
            if v2:
                stats.event(profile, f"address corrected via crosses: "
                                     f"{hit['address']} -> {corrected}")
                ops_log(f"address corrected via crosses: {hit['address']} -> {corrected}")
                hit["address"] = corrected
                verified, in_sullivan = True, ins2
                verified_label, lat, lon, locality = lbl2, la2, lo2, loc2
    if not cross:
        ops_log(f"cross streets unresolved: {hit['nature']} @ {hit['address']}")
    colony = None
    if profile.lower().startswith(("sullivan", "hatzalah", "zello-sullivan", "zello-hatzalah")):
        try:
            import sullivan_colonies as scol
            if verified_label:
                r0 = scol.match_colony_for_verified_address(verified_label)
                colony = r0.colony_name if r0.found else None
            # No transcript/name fallback: only a verified street address may
            # identify a colony. Similar channel names are never job location.
        except Exception as e:  # noqa: BLE001
            logging.warning("colony match failed: %s", e)
    box_disp = ""
    box_loc = ""
    box_mismatch = False
    if box_task is not None:
        try:
            rows = await box_task
        except Exception:  # noqa: BLE001
            rows = []
        heard = hit.get("box_heard") or _heard_box(hit.get("excerpt") or "")
        if rows and heard:
            toks = _rare_tokens(f"{hit['address']} {cross} {verified_label}")
            inc_street = _street_core(verified_label or hit["address"])
            for loc, borough in rows:
                sides = {_street_core(p) for p in re.split(r"\s+at\s+|&", loc)}
                if (hit.get("terminal_street_box_correlated") and heard == "2685"
                        and borough == "Brooklyn" and "9 AVE" in loc.upper()
                        and "53 ST" in loc.upper()) or \
                        _box_row_matches_address_and_cross(loc, hit["address"], cross) or \
                        _rare_tokens(loc) & toks or \
                        (inc_street and inc_street in sides):
                    box_disp = heard
                    break
            if not box_disp and verified:
                # user verdict 9/28: never drop the box - it anchors. First try a
                # box-supported address correction (whisper ordinal digit-drop:
                # heard 'east 4th st', box row 'AVE M at E 84 ST' -> 'East 84th
                # Street'); else post the box + its location with a mismatch flag
                corrected_addr = _box_address_correction(hit["address"], rows)
                if corrected_addr:
                    stats.event(profile, f"address corrected via box: "
                                         f"{hit['address']} -> {corrected_addr} (Box {heard})")
                    ops_log(f"address corrected via box: {hit['address']} -> {corrected_addr} "
                            f"(Box {heard})")
                    hit["address"] = corrected_addr
                    box_disp = heard
                elif locality and not any(b.lower() == locality.lower() for _, b in rows):
                    # the heard box exists ONLY in other boroughs than the
                    # verified address - the digits are whisper-glued/mangled
                    # ('box 957 70 Herkimer' -> 9577 = a QUEENS box posted on a
                    # Brooklyn job with a flag, 9/28 8:03 AM; his verdict: a
                    # wrong-borough box never posts). Kill it - closest-box
                    # from the geocoded address takes over below.
                    stats.event(profile, f"box killed (borough mismatch): heard {heard} ("
                                + "; ".join(f"{l} {b}" for l, b in rows)
                                + f") vs {hit['address']} ({locality})")
                    ops_log(f"box killed (borough mismatch): heard {heard} vs "
                            f"{hit['address']} ({locality})")
                else:
                    pick = next((l for l, b in rows
                                 if locality and b.lower() == locality.lower()), rows[0][0])
                    box_disp = heard
                    box_loc = re.sub(r"\bAt\b", "at", pick.title())
                    box_mismatch = True
                    stats.event(profile, f"box kept despite mismatch: Box {heard} - {box_loc} "
                                         f"vs {hit['address']}")
                    ops_log(f"box kept despite mismatch: Box {heard} - {box_loc} vs {hit['address']}")
            elif not box_disp:
                logging.info("[%s] box mismatch: heard Box %s, lookup %s", profile, heard, rows)
                stats.event(profile, f"box mismatch (not posted): heard {heard}, lookup "
                            + "; ".join(f"{l} ({b})" for l, b in rows))
                ops_log(f"box mismatch (not posted): heard Box {heard} @ {hit['address']}, "
                        f"lookup: " + "; ".join(f"{l} ({b})" for l, b in rows))
        elif heard:
            logging.info("[%s] box %s not in lookup DB - not posted", profile, heard)
            stats.event(profile, f"box {heard} not in lookup DB (not posted)")
    # A five-digit box+house run can equally be a four-digit box plus a
    # one-digit house, or a two-digit box plus a three-digit house. Resolve
    # ONLY when the actual box lookup independently matches the heard cross
    # or verified location. 83255 North Henry at Norman is Box 0083 + 255,
    # not Box 0832 + 55 and not the unrelated 8355.
    raw_run = hit.get("raw_box_run") or ""
    if profile == "fdny" and len(raw_run) == 5 and hit.get("box_glue_ambiguous"):
        street_tail = re.sub(r"^\d+\s+", "", hit["address"].split(",", 1)[0])
        heard_cross = hit.get("cross") or ""
        choices = []
        for n in (2, 3, 4):
            num = raw_run[:n].zfill(4)
            house = raw_run[n:]
            if not house or house.startswith("0"):
                continue
            candidate = f"{house} {street_tail}, Brooklyn, NY"
            yes, _, label, la, lo, loc = await geocode_verify(candidate, "fdny")
            if not yes or la is None or lo is None:
                continue
            rr = await _box_lookup(num)
            candidate_street = _rare_tokens(street_tail)
            cross_tokens = _rare_tokens(heard_cross)
            matching = [(place, bor) for place, bor in rr if bor == "Brooklyn"
                        and (candidate_street & _rare_tokens(place))
                        and (cross_tokens & _rare_tokens(place))]
            if matching:
                choices.append((num, candidate, label, la, lo, loc))
        if len(choices) != 1:
            stats.event(profile, f"suppressed (ambiguous five-digit box/house): {raw_run}")
            ops_log(f"suppressed (ambiguous five-digit box/house): {raw_run}")
            return "suppressed"
        box_disp, hit["address"], verified_label, lat, lon, locality = choices[0]
        box_mismatch = False
        box_loc = ""
        verified = True
        stats.event(profile, f"five-digit box/house independently resolved: Box {box_disp} @ {hit['address']}")
    # Six-digit glued box/house runs have two plausible splits. Never post
    # an uncorroborated guess or a mismatch warning as though the guessed box
    # were spoken. A box location sharing the verified address/cross is the
    # independent anchor for the chosen split.
    if hit.get("box_glue_ambiguous") and (not verified or not box_disp or box_mismatch):
        stats.event(profile, f"suppressed (ambiguous box/house split): {hit['address']}")
        ops_log(f"suppressed (ambiguous box/house split): {hit['address']}")
        return "suppressed"
    # user rules 9/28 13:12 ("the deal"): ADDRESS MANDATORY on every post -
    # unconfirmed with no box anchor does not go out ("no such a thing a
    # address doesn't get posted"); BOX ON EVERY FDNY POST - no heard box ->
    # closest box to the address; no box obtainable -> the job does not post.
    # Verified job survives an unrelated or wrong-borough spoken box.
    # The closest Brooklyn box is selected below after the bad box dies.
    if not verified and not box_disp:
        logging.info("[%s] suppressed (unconfirmed address, no box anchor): %s",
                     profile, hit["address"])
        stats.event(profile, f"suppressed (unconfirmed, no box): {hit['nature']} @ {hit['address']}")
        ops_log(f"suppressed (unconfirmed, no box): {hit['nature']} @ {hit['address']}")
        return "suppressed"
    box_closest = False
    if profile == "fdny" and not box_disp:
        nb_digits = nb_loc = None
        if verified and lat is not None and lon is not None:
            nb_digits, nb_loc, _ = await _nearest_box(lat, lon, locality)
        if nb_digits:
            box_disp = nb_digits
            # When the selected box's documented street corroborates this
            # verified address, don't label it "closest" (user's 1610 ruling).
            def _box_road_key(street):
                road = _street_core(street).lower()
                for suffix, long in ((" pl", " place"), (" ave", " avenue"),
                                     (" st", " street"), (" rd", " road"),
                                     (" blvd", " boulevard"), (" dr", " drive")):
                    if road.endswith(suffix):
                        road = road[:-len(suffix)] + long
                return road
            own_street = _box_road_key(hit["address"])
            row_streets = {_box_road_key(part) for part in
                           re.split(r"\s+at\s+|&", nb_loc or "", flags=re.I)}
            # A street intersection may match one side of a nearby box.
            # Keep '(closest)' unless this specific job's street itself
            # corroborates the box location, not merely an adjacent road.
            box_closest = not (own_street and own_street in row_streets)
            stats.event(profile, f"closest box lookup: Box {nb_digits} - {nb_loc} "
                                 f"for {hit['address']}")
            ops_log(f"closest box lookup: Box {nb_digits} - {nb_loc} for {hit['address']}")
        else:
            logging.info("[%s] suppressed (FDNY, no box obtainable): %s @ %s",
                         profile, hit["nature"], hit["address"])
            stats.event(profile, f"suppressed (no box obtainable): {hit['nature']} @ {hit['address']}")
            ops_log(f"suppressed (no box obtainable): {hit['nature']} @ {hit['address']}")
            return "suppressed"
    # North Shore Towers is a documented complex reached from the Grand
    # Central Parkway service road. Keep the broad highway geocode as the
    # verification gate, but display the spoken landmark and approach rather
    # than replacing the location with an arbitrary tower's house number.
    if hit.get("north_shore_towers") and verified and \
            re.match(r"^Grand Central Parkway, Queens, NY$", hit["address"], re.I):
        access = ("Grand Central Parkway Service Road" if
                  hit.get("service_road_spoken") else "Grand Central Parkway")
        hit["address"] = f"North Shore Towers, {access}, Queens, NY"
    text_out = format_alert(hit, crosses=cross, confirmed=verified, footer=colony,
                            box=box_disp, box_loc=box_loc, box_mismatch=box_mismatch,
                            box_closest=box_closest,
                            audio_ts=(audio_ts if audio_ts is not None else fresh_ts)
                            if clip_name else None, spoken_time=hit.get("spoken_time") or "")
    ogg = None
    if ogg_task is not None:
        try:
            ogg = await ogg_task
        except Exception:  # noqa: BLE001
            ogg = None
    ok = await alert_waha.send_text(text_out)
    if not ok:
        ops_log(f"ALERT POST FAILED: {hit['nature']} @ {hit['address']}")
        return "queued"
    if clip_name:
        if ogg:
            base = os.environ.get("RENDER_EXTERNAL_URL", "https://fdny-slim.onrender.com").rstrip("/")
            vok = await alert_waha.send_voice(f"{base}/audio/{ogg}")
            if vok:
                hit["voice_url"] = await _uguu_upload(ARCHIVE_DIR / ogg)
                if not hit["voice_url"]:
                    ops_log(f"archive upload failed (post ok): {hit['nature']} @ {hit['address']}")
            else:
                ops_log(f"voice-note send failed: {hit['nature']} @ {hit['address']}")
        else:
            ops_log(f"voice-note convert failed: {hit['nature']} @ {hit['address']}")
    if nat_norm and toks:
        recent = _load_recent()
        recent.append({"t": now, "nature": nat_norm, "tokens": sorted(toks)})
        _save_recent(recent)
    return "sent"


def format_alert(hit: dict, crosses: str = "", confirmed: bool = True,
                 footer: str | None = None, box: str = "", box_loc: str = "",
                 box_mismatch: bool = False, box_closest: bool = False,
                 audio_ts: float | None = None, spoken_time: str = "") -> str:
    """User-picked layout (9/28, option 1): bold caps nature header with fire
    emoji; bold pinned address; plain 'between X & Y' crosses line; time;
    italic source footer at the very bottom. No transcript quote, ever.
    Audio follows separately as a voice-note bubble."""
    now = datetime.now(NY).strftime("%-I:%M %p")
    nature = (hit.get("nature") or "").strip().upper()
    addr_line = f"\N{ROUND PUSHPIN} *{hit['address']}*"
    if not confirmed:
        addr_line += " (not confirmed)"
    medical = re.search(
        r"\b(?:breath(?:ing)?|cardiac|arrest|cpr|unresponsive|responsive|chok|"
        r"overdose|stroke|cva|seizure|convuls|fall|fell|bleeding|hemorrhage|"
        r"chest pain|drown|syncope|faint|passed out|diabet|sugar|allergic|"
        r"anaphyla|bee sting|abdominal|stomach|altered|disoriented|"
        r"unconscious|aided|trauma|general illness|generally ill|gi distress|"
        r"not feeling well|feeling unwell|feels unwell|feels ill|feeling ill|"
        r"doesn.t feel well|does not feel well|"
        r"sick person|medical emergency|ped(?:estrian)?|mva|mvc|accident|"
        r"collision|rollover|entrap)\w*\b", nature, re.I)
    icon = "\N{AMBULANCE}" if medical else "\N{FIRE}"
    lines = [f"*{icon} {nature}*", "", addr_line]
    if hit.get("apartment"):
        lines.append(hit["apartment"])
    if crosses:
        lines.append(f"between {crosses}" if "&" in crosses else f"off {crosses}")
    if box:
        line = f"Box {box}"
        if box_closest:
            line += " (closest)"
        if box_loc:
            line += f" - {box_loc}"
        lines.append(line)
        if box_mismatch:
            lines.append("\N{WARNING SIGN} spoken address not at box location")
    try:
        stamp = float(audio_ts) if audio_ts is not None else 0
        # Timestamps outside the live job window cannot be trusted as this
        # dispatch's capture time; never print an invented CAD time.
        time_line = ("CAD - TIME " + datetime.fromtimestamp(stamp, NY).strftime("%H:%M")
                     if stamp > 0 and abs(time.time() - stamp) < 2 * 3600
                     else f"\N{CLOCK FACE ONE OCLOCK} {now}")
    except (ValueError, TypeError, OverflowError, OSError):
        time_line = f"\N{CLOCK FACE ONE OCLOCK} {now}"
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", spoken_time):
        time_line = f"CAD - TIME {spoken_time}"
    lines += ["", time_line]
    label = footer or SOURCE_LABEL.get(hit["source"], hit["source"])
    lines.append(f"_{label}_")
    # Presentation only: keep the spoken transcript and structured hit unchanged.
    text = "\n".join(lines)
    text = re.sub(r"\bpatient\b", "PTT", text, flags=re.I)
    return re.sub(r"\bapartment\b", "APT", text, flags=re.I)


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
            await _kw_check(profile, text)
            clip_name = f"{profile}-{int(time.time())}.wav"
            await asyncio.to_thread(_archive_clip, target, clip_name)
            stats.mark_clip(profile, clip_name, text)
            try:
                job_spans = detect.split_dispatch_jobs(text, profile)
                hits = [detect.analyze(span, profile) for span in job_spans]
            except Exception as e:  # noqa: BLE001 - one bad chunk must never kill the feed
                logging.warning("[%s] detect failed: %s", profile, e)
                stats.event(profile, f"detect error: {e}")
                prev = wav
                continue
            for hit in hits:
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
                outcome = await verify_and_send(profile, hit, stats, clip_name,
                                                fresh_ts=wav.stat().st_mtime)
                ok = outcome == "sent"
                stats.mark_alert(profile, hit["nature"], hit["address"], ok,
                                 voice_url=hit.get("voice_url", ""),
                                 failed=(outcome == "queued"), outcome=outcome)
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
    await _kw_check("fdny", text)
    if wav is not None:
        clip_name = f"fdny-{int(time.time())}.wav"
        await asyncio.to_thread(_archive_clip, wav, clip_name)
        stats.mark_clip("fdny", clip_name, text)
    for suffix in (".m4a", ".wav"):
        try:
            (tmp / f"{cid}{suffix}").unlink()
        except Exception:  # noqa: BLE001
            pass
    try:
        hit = detect.analyze(text, "fdny")
    except Exception as e:  # noqa: BLE001 - one bad call must never kill the consumer
        logging.warning("[fdny] detect failed: %s", e)
        stats.event("fdny", f"detect error: {e}")
        return
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
    try:
        call_ts = float(call.get("ts") or 0) or None
        audio_start = float(call.get("audio_start_ts") or 0) or None
    except Exception:  # noqa: BLE001
        call_ts = audio_start = None
    outcome = await verify_and_send("fdny", hit, stats, clip_name,
                                    fresh_ts=call_ts, audio_ts=audio_start)

    ok = outcome == "sent"
    stats.mark_alert("fdny", hit["nature"], hit["address"], ok,
                     failed=(outcome == "queued"), outcome=outcome,
                     voice_url=hit.get("voice_url", ""))
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
    _OPS_TASKS.append(asyncio.create_task(_ops_flusher()))
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
