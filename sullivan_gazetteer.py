"""Read-only Sullivan road rescue audit. Deliberately cannot release a post."""
import asyncio
import base64
import difflib
import gzip
import hashlib
import heapq
import math
import json
import re
from functools import lru_cache
from pathlib import Path

SOURCE = 'https://gis.sullivanny.gov/arcgis/rest/services/911_Addressing_Data/MapServer'

def norm(s):
    s = re.sub(r'\b(?:road|rd)\b', 'rd', s.lower())
    s = re.sub(r'\b(?:lane|ln)\b', 'ln', s)
    return re.sub(r'[^a-z0-9 ]', ' ', s).strip()

def distance(a,b):
    return math.hypot((a[0]-b[0])*85000,(a[1]-b[1])*111000)

def corridor(road, junctions, point):
    """Unique heard junctions and exact house close to their road path."""
    if any(len(j)!=1 for j in junctions): return False, 'junction ambiguous'
    start,end=junctions[0][0],junctions[1][0]
    queue=[(0,start)]; dist={start:0}; parent={}
    while queue:
        cost,node=heapq.heappop(queue)
        if cost!=dist[node]: continue
        if node==end: break
        for nxt,weight in road['edges'].get(node,{}).items():
            new=cost+weight
            if new < dist.get(nxt,float('inf')):
                dist[nxt]=new;parent[nxt]=node;heapq.heappush(queue,(new,nxt))
    if end not in dist or not 20<=dist[end]<=5000: return False,'no bounded road path'
    path=[end]
    while path[-1]!=start:path.append(parent[path[-1]])
    def segment_gap(a,b):
        ax,ay=(a[0]-point[0])*85000,(a[1]-point[1])*111000
        bx,by=(b[0]-point[0])*85000,(b[1]-point[1])*111000
        dx,dy=bx-ax,by-ay
        t=max(0,min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0
        return math.hypot(ax+t*dx,ay+t*dy)
    gap=min(segment_gap(a,b) for a,b in zip(path,path[1:]))
    return gap<=25, {'path_length_m':round(dist[end],1),'house_path_gap_m':round(gap,1),'path_nodes':path}

@lru_cache(maxsize=1)
def roads():
    p = Path(__file__).with_name('sullivan_roads.b64')
    raw = base64.b64decode(p.read_text(), validate=True)
    d = json.loads(gzip.decompress(raw))
    grouped = {}
    for f in d['features']:
        a = f['attributes']; name = a.get('FULLNAME') or ''
        # Keep disconnected/locality variants separate; shared county is not locality.
        loc = a.get('PSTLCITYLeft') or a.get('PSTLCITYRight') or ''
        key = (name, loc)
        r = grouped.setdefault(key, {'name': name, 'locality': loc, 'ids': [], 'aliases': set(), 'nodes': set(), 'edges': {}})
        r['ids'].append(a['OBJECTID'])
        r['aliases'].update(norm(a.get('Alias'+str(i)) or '') for i in range(1,6))
        if a.get('CTYROUTE'): r['aliases'].add(norm('County Road '+a['CTYROUTE']))
        for path in f.get('geometry', {}).get('paths', []):
            points=[(round(x,6),round(y,6)) for x,y,*_ in path]
            r['nodes'].update(points)
            for a,b in zip(points,points[1:]):
                dist=distance(a,b)
                r['edges'].setdefault(a,{})[b]=dist
                r['edges'].setdefault(b,{})[a]=dist
    return d, hashlib.sha256(raw).hexdigest(), list(grouped.values())

def candidates(heard, catalog):
    n = norm(heard); digits = re.findall(r'\d+[a-z]?', n)
    out=[]
    for r in catalog:
        if not r['name'] or not r['locality']: continue
        aliases={norm(r['name'])} | r['aliases']
        scores=[difflib.SequenceMatcher(None,n,a).ratio() for a in aliases if a and re.findall(r'\d+[a-z]?',a)==digits]
        score=max(scores,default=0)
        if score >= .78: out.append((r,round(score,3)))
    return out

def heard_parts(hit):
    text=hit.get('excerpt') or ''
    m=re.search(r'\b(\d{1,5})\s+([A-Za-z][A-Za-z -]+?\b(?:Road|Rd|Lane|Ln|Street|St))\b',text,re.I)
    cross=re.search(r'\bcross streets?\s*(?:are|to|is)?\s+(.+?)(?:[.;]|$)',text,re.I)
    return (m.group(1),m.group(2),[p.strip() for p in re.split(r'\s+and\s+|\s*&\s*',cross.group(1))]) if m and cross else ('','',[])

async def shadow(hit, session):
    audit={'mode':'shadow_only','release':False,'source':SOURCE,'heard':hit.get('excerpt',''),'address':hit.get('address',''),'nature':hit.get('nature','')}
    if not hit.get('nature') or hit.get('nature','').lower() == 'unknown problem':
        return dict(audit,reason='no specific complaint')
    import audio_review
    if audio_review.mixed(hit.get('excerpt',''),'zello-sullivan'):
        return dict(audit,reason='mixed incident')
    house,heard,crosses=heard_parts(hit)
    audit.update(house=house,heard_road=heard,heard_crosses=crosses,candidates=[])
    if not house or not crosses or len(crosses)>2:
        return dict(audit,reason='missing exact house or independent crosses')
    try:
        d,sha,catalog=roads()
        audit.update(version=d['version'],gazetteer_sha256=sha,retrieved_at=d['retrieved_at'])
        import datetime
        if (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(d['retrieved_at'])).days>30:
            return dict(audit,reason='gazetteer stale')
        survivors=[]
        for r,score in candidates(heard,catalog):
            row={'canonical':r['name'],'locality':r['locality'],'ids':r['ids'],'score':score,'junctions':[]}
            for c in crosses:
                matches=[other for other in catalog if norm(c) in ({norm(other['name'])}|other['aliases'])]
                junctions=set().union(*(r['nodes'] & o['nodes'] for o in matches)) if matches else set()
                row['junctions'].append({'heard':c,'nodes':sorted(junctions)})
            if not all(j['nodes'] for j in row['junctions']):
                row['reason']='cross not an exact alias at a shared road node'
            else:
                # Exact county address point, not an address-range guess.
                name=r['name'].replace("'","''")
                where=f"ADDRNUM = '{house}' AND FULLNAME = '{name}'"
                async with session.get(SOURCE+'/0/query',params={'where':where,'outFields':'OBJECTID,ADDRNUM,FULLNAME,PSTLCITY,MUNICIPALITY','returnGeometry':'true','outSR':'4326','f':'json'}) as rsp:
                    pts=(await rsp.json()).get('features',[]) if rsp.status==200 else []
                pts=[p for p in pts if (p['attributes'].get('PSTLCITY') or '').lower()==r['locality'].lower()]
                row['exact_house_records']=pts
                if len(pts)!=1:row['reason']='exact house/locality ambiguous or absent'
                elif len(crosses)==2:
                    geo=pts[0].get('geometry',{})
                    good,proof=corridor(r,[j['nodes'] for j in row['junctions']],(geo.get('x',0),geo.get('y',0)))
                    row['corridor_proof']=proof
                    row['reason']='shadow two-cross evidence complete' if good else 'house corridor unproven'
                    if good:survivors.append(row)
                else:
                    row['reason']='shadow evidence complete for one cross; existing gates still required'
                    survivors.append(row)
            audit['candidates'].append(row)
        places={rr['locality'].lower() for rr in catalog if rr['locality']}
        heard_places={place for place in places if re.search(r'\b'+re.escape(place)+r'\b',hit.get('excerpt',''),re.I)}
        if heard_places:
            survivors=[row for row in survivors if heard_places=={row['locality'].lower()}]
        audit['heard_localities']=sorted(heard_places)
        audit['single_survivor']=len(survivors)==1
        audit['reason']='single candidate shadow match; no release' if len(survivors)==1 else 'zero or multiple complete candidates; hold'
    except Exception as exc:
        audit['reason']='lookup unavailable: '+type(exc).__name__
    return audit

async def audit_hold(hit, directory):
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            record=await asyncio.wait_for(shadow(hit,session),timeout=15)
    except Exception as exc:
        record={'mode':'shadow_only','release':False,'reason':type(exc).__name__,'heard':hit.get('excerpt','')}
    p=Path(directory)/'sullivan_gazetteer_shadow.jsonl'
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a') as f:f.write(json.dumps(record,sort_keys=True)+'\n')
    return record
