"""Local-only strict CHVAC named-site candidate, not connected to production sender."""
from __future__ import annotations
import math
import re
import detect
from dataclasses import dataclass
from typing import Callable, Awaitable
import sullivan_colonies as sites

@dataclass(frozen=True)
class NamedSite:
    name: str
    address: str
    source: str
    lat: float
    lon: float
    verified_label: str


def heard_site(text: str, profile: str) -> dict | None:
    if profile.removeprefix('zello-') != 'sullivan':
        return None
    if not detect.is_emergency(text) or not detect.get_nature(text, 'sullivan'):
        return None
    # A mention isn't a job location. Keep only locative dispatch phrases.
    candidate = sites.unique_named_site_in_transcript(text, source_profile=profile)
    if candidate is None:
        return None
    name = re.escape(candidate['colony_name']).replace(r'\-', r'[- ]')
    if not re.search(r'\b(?:at|to|for|on|in)\s+(?:the\s+)?'+name+r'(?![\w-])', text, re.I):
        return None
    # A full street address in the same job is the primary location. Do not
    # let an incidental named complex overwrite it, especially when they
    # disagree. Its existing road/cross verifier handles that case.
    if detect.extract_dispatch_address(text, 'sullivan'):
        return None
    # A caller or dispatcher explicitly hedging the place isn't enough.
    if re.search(r'\b(?:maybe|possibly|perhaps|not at|instead of)\s+(?:the\s+)?'+name, text, re.I):
        return None
    return candidate


def _meters(a: float,b: float,c: float,d: float) -> float:
    r=math.pi/180
    h=math.sin((c-a)*r/2)**2+math.cos(a*r)*math.cos(c*r)*math.sin((d-b)*r/2)**2
    return 12742000*math.asin(math.sqrt(h))


async def independently_verify(text: str, profile: str,
    geocode: Callable[[str,str], Awaitable[tuple]]) -> NamedSite | None:
    """Require live independent road/county check and 250m map agreement.

    This is only a location result. Caller still applies fresh audio, emergency
    nature, spoken area and send/duplicate rules; no fallback to CHVAC alone.
    """
    row = heard_site(text,profile)
    if row is None or not row.get('lat') or not row.get('lon'):
        return None
    verified, county, label, lat, lon, locality = await geocode(row['address'],'sullivan')
    if not verified or not county or lat is None or lon is None:
        return None
    if _meters(float(row['lat']),float(row['lon']),float(lat),float(lon))>250:
        return None
    street = row['street']
    number = re.match(r'^(\d+)\b',street)
    if number and not re.match(r'^\s*'+number.group(1)+r'(?:\s|,|$)',label):
        return None
    # A stated, different town/hamlet is a conflict, not an optional hint.
    named_areas = {x.lower() for x in ('Loch Sheldrake','Monticello','Woodridge','Liberty','Ferndale','Fallsburg','South Fallsburg')}
    stated = {x for x in named_areas if re.search(r'(?<!\w)'+re.escape(x)+r'(?!\w)',text,re.I)}
    if stated and row['city'].lower() not in stated:
        return None
    return NamedSite(row['colony_name'],row['address'],row['source'],float(row['lat']),float(row['lon']),label)
