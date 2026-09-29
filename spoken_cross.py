"""Verify a directly spoken FDNY cross against OSM street geometry, bounded."""
import asyncio
import math
import re
import xml.etree.ElementTree as ET
import aiohttp


def _road(s):
    s=s.lower().strip()
    s=re.sub(r'\b(\d+)(?:st|nd|rd|th)\b',r'\1',s)
    for pat,repl in [(r'\bavenue\b','ave'),(r'\bstreet\b','st'),(r'\broad\b','rd'),(r'\bboulevard\b','blvd')]:
        s=re.sub(pat,repl,s)
    return s


async def verify(street: str, cross: str, lat: float, lon: float) -> bool:
    """True iff distinct named road ways share a node within 250m of address.
    No source/map failure is a pass. Aimed at display, not location creation.
    """
    if not street or not cross or lat is None or lon is None:
        return False
    # A ~300m box is narrow enough for address-nearby crosses and well below
    # the OSM map endpoint's maximum allowed bounding box.
    delta_lat=0.0027
    delta_lon=0.0036
    bbox=f'{lon-delta_lon},{lat-delta_lat},{lon+delta_lon},{lat+delta_lat}'
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get('https://www.openstreetmap.org/api/0.6/map',params={'bbox':bbox},
                             timeout=aiohttp.ClientTimeout(total=9)) as r:
                if r.status!=200:return False
                blob=await r.read()
                if len(blob)>3_000_000:return False
        root=ET.fromstring(blob)
    except Exception:
        return False
    coords={n.attrib['id']:(float(n.attrib['lat']),float(n.attrib['lon'])) for n in root.findall('node')}
    roads={_road(street):set(),_road(cross):set()}
    for way in root.findall('way'):
        tags={x.attrib['k']:x.attrib['v'] for x in way.findall('tag')}
        name=_road(tags.get('name',''))
        if name in roads and tags.get('highway'):
            roads[name].update(x.attrib['ref'] for x in way.findall('nd'))
    if _road(street)==_road(cross):return False
    for node in roads[_road(street)]&roads[_road(cross)]:
        if node not in coords:continue
        a,b=coords[node]
        dlat=(a-lat)*110540
        dlon=(b-lon)*111320*math.cos(math.radians(lat))
        if math.hypot(dlat,dlon)<=250:return True
    return False
