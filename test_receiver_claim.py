import unittest
from unittest.mock import AsyncMock
from receiver_claim import process_claimed
class Client:
 def __init__(self):
  self.claim=AsyncMock(return_value={'id':'100-223669','durable':True,'status':'claimed','token':'t'})
  self.finish=AsyncMock(return_value={'id':'100-223669','durable':True,'status':'complete'})
class Tests(unittest.IsolatedAsyncioTestCase):
 async def test_complete(self):
  c=Client();h=AsyncMock(return_value='sent');r=await process_claimed({'id':'100-223669'},c,'render',h);self.assertTrue(r['durable']);h.assert_awaited_once();c.finish.assert_awaited_once_with('100-223669','t','sent')
 async def test_unverified_blocks(self):
  c=Client();c.claim.return_value={'ok':True};h=AsyncMock();r=await process_claimed({'id':'100-223669'},c,'render',h);h.assert_not_awaited();self.assertEqual(r['status'],'unverified_claim')
 async def test_duplicate_blocks(self):
  c=Client();c.claim.return_value={'id':'100-223669','durable':True,'status':'duplicate'};h=AsyncMock();await process_claimed({'id':'100-223669'},c,'render',h);h.assert_not_awaited()
 async def test_uncertain_blocks(self):
  c=Client();c.claim.return_value={'id':'100-223669','durable':True,'status':'uncertain'};h=AsyncMock();await process_claimed({'id':'100-223669'},c,'render',h);h.assert_not_awaited()
 async def test_network_failure_blocks(self):
  c=Client();c.claim.side_effect=TimeoutError;h=AsyncMock();await process_claimed({'id':'100-223669'},c,'render',h);h.assert_not_awaited()
 async def test_handle_exception_not_completed_or_retried(self):
  c=Client();h=AsyncMock(side_effect=RuntimeError);r=await process_claimed({'id':'100-223669'},c,'render',h);self.assertEqual(r['status'],'uncertain');c.finish.assert_not_awaited();h.assert_awaited_once()
 async def test_unknown_handle_result_not_completed(self):
  c=Client();h=AsyncMock(return_value=None);r=await process_claimed({'id':'100-223669'},c,'render',h);self.assertEqual(r['status'],'uncertain');c.finish.assert_not_awaited()
 async def test_lost_completion_not_reprocessed(self):
  c=Client();c.finish.side_effect=TimeoutError;h=AsyncMock(return_value='suppressed');r=await process_claimed({'id':'100-223669'},c,'render',h);self.assertEqual(r['status'],'completion_unavailable');h.assert_awaited_once()
