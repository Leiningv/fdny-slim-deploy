"""Pure decision helpers for a bounded second listen. Never sends or geocodes."""
import re
from difflib import SequenceMatcher
import detect

FALLBACK = re.compile(r'^(?:phone alarm|fire alarm|automatic alarm|alarm activation|class 3)\b', re.I)

def complaint_lost(text, nature):
    """Veto a fallback when a specific job-local complaint was not extracted."""
    if not FALLBACK.match(nature or ''):
        return False
    for m in re.finditer(r'\b(?:for|reporting)\s+(?:an?\s+)?([^.,;]{3,85})', text or '', re.I):
        phrase = m.group(1).strip().lower()
        if re.match(r'(?:no|not|without|negative)\b', phrase):
            continue
        if re.search(r'\b(?:odor|gasoline|leak|fire|smoke|unconscious|unresponsive|chest pain|trauma|breathing)\b', phrase):
            if re.search(r'\b(?:automatic|fire|phone|smoke) alarm\b', phrase):
                continue
            return True
    import fdny_audio_gate
    return fdny_audio_gate.unclassified_fire_complaint(text, nature)

def mixed(text, profile):
    if detect.sullivan_numbered_jobs(text, profile):
        return True
    if profile == 'fdny':
        return len(set(re.findall(r'\bbox\s*[,;:]?\s*(\d{2,5})\b', text or '', re.I))) > 1
    # Brooklyn shorthand pairs can carry distinct medical calls in one PTT.
    # Repeats of the same pair are not a split. Require dispatch wording or
    # a complaint next to each pair; bare unit IDs do not establish roads.
    pairs=set()
    for m in re.finditer(r"\b(?:for|to|available for|units for)\s+(\d{1,2})"
                         r"\s*(?:and|&|/|-|,|\s)\s*(\d{2})(?!\d)\b", text or "", re.I):
        pairs.add((m.group(1),m.group(2)))
    for m in re.finditer(r"\b(?:for|to|available for|units for)\s+(\d{2})(\d{2})\b", text or "", re.I):
        pairs.add((m.group(1),m.group(2)))
    if len(pairs)>1:
        return True
    # Do not attach a complaint to the first of two distinct full addresses.
    houses = {re.sub(r'\s+', ' ', m.group().lower()) for m in re.finditer(
        r'\b\d{1,5}(?:-\d{1,3})?\s+(?:(?:[A-Za-z][A-Za-z\'-]*|\d+(?:st|nd|rd|th)?)\s+){1,4}'
        r'(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Place|Pl|Lane|Ln)\b', text or '', re.I)}
    return len(houses) > 1

def one_candidate(text, profile):
    if not text or mixed(text, profile):
        return None, 'second listen empty or contains multiple jobs'
    hits = [detect.analyze(span, profile) for span in detect.split_dispatch_jobs(text, profile)]
    hits = [h for h in hits if h and h.get('nature') and h.get('address')]
    if len(hits) != 1:
        return None, 'second listen did not establish one complete dispatch'
    hit = hits[0]
    if complaint_lost(text, hit['nature']):
        return None, 'second listen complaint still unclassified'
    return hit, ''

def parts(hit):
    address = str((hit or {}).get('address') or '').lower()
    bits = address.split(',')
    road = bits[0].strip()
    m = re.match(r'^(\d{1,5}(?:-\d{1,3})?[a-z]?)\s+', road)
    house = m.group(1) if m else ''
    if m: road = road[m.end():]
    road = re.sub(r'\b(\d+)(?:st|nd|rd|th)\b', r'\1', road)
    for long, short in [('avenue','ave'),('street','st'),('road','rd'),('boulevard','blvd')]:
        road = re.sub(r'\b'+long+r'\b', short, road)
    return house, road, bits[1].strip() if len(bits) > 1 else ''

def compatible(primary, candidate, profile, primary_verified=False):
    """Allow bounded repair with incident anchors, never a different plausible job."""
    if not primary:
        return True  # source recording still gets complete map/freshness checks
    a,b = parts(primary),parts(candidate)
    n1,n2 = primary.get('nature') or '', candidate.get('nature') or ''
    # A real complaint cannot be changed into another complaint. A vague
    # transmission prefix may be replaced only by the independently heard one.
    if n1 and not FALLBACK.match(n1) and n1.casefold()!=n2.casefold():
        return False
    if profile == 'fdny':
        bx1,bx2=primary.get('box_heard') or '',candidate.get('box_heard') or ''
        if bx1 and bx2 and bx1!=bx2:
            return False
        if a==b:
            return True
        if primary_verified:
            return False  # two map-valid differing addresses need owner review
        # Mangled house/street: same spoken box plus same actual complaint.
        # Without both anchors, only a modest spelling repair at same house.
        if bx1 and bx1==bx2 and n1 and not FALLBACK.match(n1) and n1.casefold()==n2.casefold() and a[2]==b[2]:
            return SequenceMatcher(None,a[1],b[1]).ratio()>=0.65
        return bool(a[0] and a[0]==b[0] and a[2]==b[2] and
                    SequenceMatcher(None,a[1],b[1]).ratio()>=0.72)
    if a[2]!=b[2] and not primary.get('area_defaulted'):
        return False
    if a[0] and a[0]!=b[0]:
        return False
    return bool(a[1] and a[1]==b[1])

def needs_fdny_review(hit, text, held_reason=''):
    if held_reason:
        return True
    if not hit or not hit.get('nature'):
        return True
    return bool(FALLBACK.match(hit['nature']) or not hit.get('cross') or
                complaint_lost(text,hit['nature']))
