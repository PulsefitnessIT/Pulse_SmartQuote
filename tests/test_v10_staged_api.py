"""Check that stage dragging saves whole machine groups and rejects invalid dates."""
import os,tempfile,unittest
from pathlib import Path
os.environ['SMARTQUOTE_AUTH']='off'
import main
from fastapi.testclient import TestClient

class StageDateEndpoints(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.saved=main.DB
  main.DB=Path(self.temp.name)/'stage_test.db'
  self.client=TestClient(main.app)
  q=main.defaults()
  q.update(id='date-test',customer='Customer',site='Site',contract_start='2027-01-01',
           contract_end='2027-12-31',assets=[
    {'id':'a','code':'100H-AAB','qty':1,'name':'Machine A'},
    {'id':'b','code':'200H-AAB','qty':1,'name':'Machine B'}])
  main.persist(q);self.url='/api/quotes/date-test'
 def tearDown(self):
  self.client.close();main.DB=self.saved;self.temp.cleanup()
 def test_bulk_assignment(self):
  self.assertEqual(self.client.post(self.url+'/stages',json={'start_date':'2027-07-01'}).status_code,200)
  reply=self.client.post(self.url+'/stages/assign',json={'asset_ids':['a','b'],'start_date':'2027-07-01'})
  self.assertEqual(reply.status_code,200)
  self.assertTrue(all(a['cover_start']=='2027-07-01' for a in main.getq('date-test')['assets']))
  self.assertEqual(self.client.delete(self.url+'/stages/2027-07-01').status_code,409)
 def test_unauthorised_date_rejected(self):
  self.assertEqual(self.client.post(self.url+'/stages/assign',json={'asset_ids':['a'],'start_date':'2027-08-01'}).status_code,400)
  self.assertFalse(main.getq('date-test')['assets'][0].get('cover_start'))
