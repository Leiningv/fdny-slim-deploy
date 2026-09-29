"""Local-only Hatzalah borough ambiguity gate (not a geocoder replacement)."""
import re
import aiohttp

_BORO={'brooklyn':'Brooklyn','queens':'Queens','manhattan':'Manhattan',
       'bronx':'Bronx','staten island':'Staten Island'}


def explicit_borough(text: str) -> str:
    low=(text or '').lower()
    # Explicit dispatch locality, not a road name or a responding unit label.
    for name in sorted(_BORO,key=len,reverse=True):
        if re.search(r'\b(?:in|at|near|for|dispatch(?:ing)? to)\s+'+re.escape(name)+r'\b',low):
            return _BORO[name]
    return ''


async def plausible_boroughs(street: str, house: str='') -> set[str] | None:
    """Neutral NYC address search. None is unavailable, not a pass."""
    q=(house+' '+street if house else street).strip()+', NY'
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get('https://geosearch.planninglabs.nyc/v2/search',
                                params={'text':q,'size':30},timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status!=200:return None
                feats=(await r.json()).get('features') or []
    except Exception:
        return None
    # Exact road-name agreement, not a substring like 'Roosevelt Ave' for
    # 'Roosevelt Court'. Results can be houses along the road.
    core=re.sub(r'^\d+\s+','',street).strip().lower()
    core=re.sub(r'\b(\d+)(?:st|nd|rd|th)\b',r'\1',core)
    core=re.sub(r'\b(?:court|ct)\b','ct',core)
    core=re.sub(r'\b(?:road|rd)\b','rd',core)
    core=re.sub(r'\b(?:street|st)\b','st',core)
    core=re.sub(r'\b(?:avenue|ave)\b','ave',core)
    names=set()
    for f in feats:
        prop=f.get('properties') or {}
        label=str(prop.get('label') or '')
        road=label.split(',')[0].strip().lower()
        road=re.sub(r'^\d+\s+','',road)
        road=re.sub(r'\b(\d+)(?:st|nd|rd|th)\b',r'\1',road)
        road=re.sub(r'\b(?:court|ct)\b','ct',road)
        road=re.sub(r'\b(?:road|rd)\b','rd',road)
        road=re.sub(r'\b(?:street|st)\b','st',road)
        road=re.sub(r'\b(?:avenue|ave)\b','ave',road)
        if road==core:
            if not house or label.split(' ',1)[0]==house:
                names.add(str(prop.get('borough') or '').title())
    return names


async def default_area_safe(hit: dict, transcript: str) -> bool:
    """No posting via a guessed Brooklyn suffix if neutral map is ambiguous."""
    if hit.get('source','').removeprefix('zello-') not in ('hatzolah','hatzalah'):
        return True
    addr=str(hit.get('address') or '')
    if explicit_borough(transcript):
        return True   # existing verified-locality and coverage gates still apply
    if not addr.lower().endswith(', brooklyn, ny'):
        return True   # a named locality goes through existing exact-town gate
    street=addr.split(',')[0].strip()
    m=re.match(r'^(\d+)\s+(.+)',street)
    house=m.group(1) if m else ''
    core=m.group(2) if m else street
    boroughs=await plausible_boroughs(core,house)
    # A street name alone does not locate a call within NYC. The same street
    # can recur outside the search result window; require an actual spoken
    # house number before accepting default borough. Directly spoken borough
    # uses the existing exact-borough verifier instead.
    return bool(house) and boroughs=={'Brooklyn'}
