"""Opt-in exact Google intersection lookup. No sends, setup or billing actions."""
import asyncio,os,re,time
import aiohttp

BOROUGHS={'Brooklyn','Queens','Manhattan','Bronx','Staten Island'}
SUFFIX={'ave':'avenue','st':'street','rd':'road','blvd':'boulevard','pkwy':'parkway','dr':'drive','ln':'lane','ct':'court','pl':'place','ter':'terrace'}

def canon(s):
 s=s.lower().strip()
 s=re.sub(r'\b(\d+)(?:st|nd|rd|th)\b',r'\1',s)
 for a,b in SUFFIX.items():s=re.sub(r'\b'+a+r'\b',b,s)
 return re.sub(r'\s+',' ',s)

def query(address):
 bits=[x.strip() for x in address.split(',')]
 if len(bits)!=3 or bits[1] not in BOROUGHS or bits[2]!='NY':return None
 roads=re.split(r'\s+&\s+|\s+and\s+',bits[0],flags=re.I)
 if len(roads)!=2:return None
 for road in roads:
  if not re.fullmatch(r"(?:[A-Za-z0-9][A-Za-z0-9' -]* )?(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Parkway|Pkwy|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Terrace|Ter)",road,re.I):return None
  if re.match(r'^\d+\s+(?:[A-Za-z]|\d)',road):return None # no house substitution
 if canon(roads[0])==canon(roads[1]):return None
 return roads,bits[1],f'{roads[0]} and {roads[1]}, {bits[1]}, NY'

def exact_result(address,payload):
 q=query(address)
 if not q or payload.get('status')!='OK':return None
 roads,borough,_=q;matches=[]
 for r in payload.get('results',[]):
  if r.get('partial_match') or 'intersection' not in r.get('types',[]):continue
  components=r.get('address_components',[])
  corners=[c.get('long_name','') for c in components if 'intersection' in c.get('types',[])]
  areas=[c.get('long_name','') for c in components if 'political' in c.get('types',[])]
  if borough not in areas or 'New York' not in areas:continue
  if len(corners)!=1:continue
  sides=re.split(r'\s+&\s+|\s+and\s+',corners[0],flags=re.I)
  if len(sides)!=2 or {canon(x) for x in sides}!={canon(x) for x in roads}:continue
  g=r.get('geometry',{});p=g.get('location',{})
  if g.get('location_type') not in ('GEOMETRIC_CENTER','ROOFTOP'):continue
  lat,lon=p.get('lat'),p.get('lng')
  if isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and 40.48<=lat<=40.94 and -74.26<=lon<=-73.70:matches.append((lat,lon))
 return matches[0] if len(matches)==1 else None

async def lookup(address,timeout=1.5):
 q=query(address);key=os.environ.get('GOOGLE_GEOCODING_API_KEY','')
 if os.environ.get('GOOGLE_EXACT_INTERSECTION_FALLBACK','0')!='1' or not q or not key:return None
 async def request():
  async with aiohttp.ClientSession() as s:
   async with s.get('https://maps.googleapis.com/maps/api/geocode/json',params={'address':q[2],'key':key},timeout=aiohttp.ClientTimeout(total=timeout)) as r:
    if r.status!=200:return None
    return exact_result(address,await r.json())
 try:return await asyncio.wait_for(request(),timeout=timeout)
 except Exception:return None # never log URL/key or turn a failed check into a pass
