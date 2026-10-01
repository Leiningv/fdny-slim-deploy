"""Private receiver adapter. All network calls injected; no live credentials."""
from dataclasses import dataclass
@dataclass(frozen=True)
class Decision:
    process: bool
    token: str = ''
    status: str = 'unavailable'

async def claim_call(call, client, owner):
    cid=str(call.get('id') or call.get('filename') or '')
    if not cid or not owner:
        return Decision(False,status='invalid')
    try:
        receipt=await client.claim(cid,owner)
    except Exception:
        return Decision(False,status='claim_unavailable')
    if not isinstance(receipt,dict) or receipt.get('id')!=cid or receipt.get('durable') is not True:
        return Decision(False,status='unverified_claim')
    status=receipt.get('status')
    if status=='claimed' and isinstance(receipt.get('token'),str) and receipt['token']:
        return Decision(True,receipt['token'],'claimed')
    return Decision(False,status=status if status in ('duplicate','uncertain') else 'unverified_claim')

async def process_claimed(call,client,owner,handle):
    decision=await claim_call(call,client,owner)
    if not decision.process:
        return {'id':str(call.get('id') or call.get('filename') or ''),'status':decision.status,'processed':False}
    cid=str(call.get('id') or call.get('filename'))
    try:
        outcome=await handle(call)
    except Exception:
        # Preserve the outstanding claim. Completion is UNKNOWN after an
        # exception because the outbound send may already have happened.
        return {'id':cid,'status':'uncertain','processed':True}
    if outcome not in ('sent','suppressed','no_hit'):
        return {'id':cid,'status':'uncertain','processed':True}
    try:
        receipt=await client.finish(cid,decision.token,outcome)
    except Exception:
        return {'id':cid,'status':'completion_unavailable','processed':True}
    if not isinstance(receipt,dict) or receipt.get('durable') is not True or receipt.get('id')!=cid or receipt.get('status') not in ('complete','duplicate'):
        return {'id':cid,'status':'unverified_completion','processed':True}
    return {'id':cid,'status':'complete','outcome':outcome,'durable':True,'processed':True}
