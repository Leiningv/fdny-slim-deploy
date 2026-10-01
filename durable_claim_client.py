"""Opt-in durable FDNY processing claims. Fail closed when configured."""
import os
import aiohttp

def configured():
    return os.environ.get('FDNY_DURABLE_CLAIMS','0')=='1'

class Client:
    def __init__(self):
        self.url=os.environ.get('FDNY_CLAIM_URL','').rstrip('/')
        self.secret=os.environ.get('FDNY_CLAIM_SECRET','')
    async def _post(self,path,payload):
        if not self.url.startswith('https://') or not self.secret:
            raise RuntimeError('claim_configuration_missing')
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as s:
            async with s.post(self.url+path,json=payload,headers={'Authorization':'Bearer '+self.secret},allow_redirects=False) as r:
                if r.status!=200:raise RuntimeError('claim_receipt_unavailable')
                return await r.json()
    async def claim(self,cid,owner):return await self._post('/claim',{'id':cid,'owner':owner})
    async def finish(self,cid,token,outcome):return await self._post('/finish',{'id':cid,'token':token,'outcome':outcome})
