"""FDNY live incident UPDATE proposals. Shadow only: no sender dependency."""
import json
import re
import time
import hashlib
from pathlib import Path

MAX_AGE=2*3600
FRESH=180

def normalized_address(s):
    return re.sub(r'\s+',' ',(s or '').strip().lower())

def ledger_path(directory):return Path(directory)/'fdny_incident_ledger.json'

def load(directory):
    p=ledger_path(directory)
    if not p.exists():return {}
    return json.loads(p.read_text())

def save(directory,ledger):
    p=ledger_path(directory);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(ledger,sort_keys=True));tmp.replace(p)

def register(directory,hit,call):
    """Only caller's successfully posted verified incident may register."""
    address=hit.get('address',''); box=hit.get('box_heard') or ''
    borough=re.search(r',\s*(Brooklyn|Queens|Manhattan|Bronx|Staten Island),\s*NY$',address,re.I)
    if not box or not borough or not re.match(r'^\d+[A-Za-z-]*\s+',address):return
    ledger=load(directory)
    key=box+'|'+normalized_address(address)
    old=ledger.get(key,{})
    ledger[key]=dict(old,box=box,address=address,borough=borough.group(1).title(),
                     initial_ts=old.get('initial_ts',float(call.get('ts') or time.time())),
                     last_ts=float(call.get('ts') or time.time()),source_call_id=str(call.get('id','')),
                     original_post_id=hit.get('outbound_message_id',''),
                     fingerprints=old.get('fingerprints',[]),stage=old.get('stage','initial'))
    save(directory,ledger)

def proposal(directory,call,text,clip_url='',now=None):
    now=time.time() if now is None else now
    ts=float(call.get('ts') or 0)
    escalation=bool(re.search(r'\b(?:10[- ]75|1075)\b',text,re.I))
    battalion=bool(re.search(r'\bbattalion\s+\d+\b',text,re.I))
    row={'mode':'shadow_only','release':False,'source_call_id':str(call.get('id','')),'ts':ts,
         'heard':text,'recording':clip_url,'reason':'not a scoped update'}
    if not escalation and not battalion:return row
    if re.search(r"\b(?:another|different|second|separate)\s+(?:box|job|incident|address)\b",text,re.I):
        return dict(row,reason='multiple incident language')
    if re.search(r"\b(?:no|not|cancel(?:led)?|negative)\b.{0,24}\b(?:10[- ]75|1075)\b|\b(?:10[- ]75|1075)\b.{0,24}\b(?:cancel(?:led)?|negative)\b",text,re.I):
        return dict(row,reason='negated escalation')
    if not 0<=now-ts<=FRESH:return dict(row,reason='stale or future update')
    boxes=set(m.group(1).zfill(4) for m in re.finditer(r'\bbox\s*[,;:]?\s*(\d{2,4})(?!\d)',text,re.I))
    if len(boxes)!=1:return dict(row,reason='missing or multiple spoken box anchors')
    box=next(iter(boxes));ledger=load(directory)
    candidates=[(k,r) for k,r in ledger.items() if r['box']==box and 0<=ts-r.get('initial_ts',r['last_ts'])<=MAX_AGE]
    boroughs=set(re.findall(r'\b(Brooklyn|Queens|Manhattan|Bronx|Staten Island)\b',text,re.I))
    if boroughs:
        candidates=[(k,r) for k,r in candidates if {b.lower() for b in boroughs}=={r['borough'].lower()}]
    # A newly spoken house must agree with the stored verified incident.
    houses=set(re.findall(r'\b(\d{1,5}(?:-\d+)?)\s+(?:[A-Za-z0-9]+\s+){1,3}(?:Street|Avenue|Road|Place)\b',text,re.I))
    if len(houses)>1:return dict(row,reason='multiple spoken houses')
    if houses:
        candidates=[(k,r) for k,r in candidates if houses=={r['address'].split()[0]}]
        import detect
        parsed=detect.analyze(text,'fdny')
        if not parsed: return dict(row,reason='spoken full address could not be paired')
        if re.match(r'^\d+\s+',parsed.get('address','')):
            candidates=[(k,r) for k,r in candidates if normalized_address(parsed['address'])==normalized_address(r['address'])]
    if len(candidates)!=1:return dict(row,reason='incident anchor ambiguous or absent')
    key,incident=candidates[0]
    if not escalation and not boroughs:return dict(row,reason='subsequent report missing spoken borough')
    if battalion and not escalation and incident.get('stage')!='10-75':return dict(row,reason='battalion report before10-75 anchor')
    if re.search(r'\b(?:no|not|cancel|negative)\s+(?:a\s+)?(?:10[- ]75|1075)\b',text,re.I):return dict(row,reason='negated escalation')
    # Preserve source words, not inferred tactical facts. This remains a
    # proposal requiring transcript/audio concordance before activation.
    detail=re.sub(r'\s+',' ',text).strip()
    fingerprint=hashlib.sha256((key+'|'+detail.lower()).encode()).hexdigest()
    if fingerprint in incident.get('fingerprints',[]):return dict(row,reason='repeated update fingerprint')
    title='UPDATE - 10-75'
    row.update(incident_key=key,address=incident['address'],box=box,
               original_post_id=incident.get('original_post_id',''),fingerprint=fingerprint,
               would_post=f'*{title}*\n\n{incident["address"]}\nBox {box}\n\nHeard battalion/dispatch report: {detail}\n\nFDNY {incident["borough"]} Dispatch',
               reason='candidate update; shadow only, audio/detail review required')
    incident['stage']='10-75';incident['last_ts']=ts
    incident['fingerprints']=(incident.get('fingerprints',[])+[fingerprint])[-100:]
    save(directory,ledger)
    return row

def audit(directory,call,text,clip_url=''):
    row=proposal(directory,call,text,clip_url)
    p=Path(directory)/'fdny_update_shadow.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
    return row
