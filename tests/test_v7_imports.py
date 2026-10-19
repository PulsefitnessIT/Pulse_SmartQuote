"""V7 tests against the two real customer-uploaded examples."""
import base64,os,secrets,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app
import engine,security
from agreement_import import read_agreement_pdf

ROOT=Path('/mnt/data')
KA=ROOT/'Kit at KA Leisure Sites -  MASTER.xlsx'
AGREEMENT=ROOT/'Active North Yorkshire - Skipton Leisure & Wellbeing Maintenance Agreement c7323 - 1 YEAR with option to extend for a further year - 2025 - R1.pdf'

class V7ActualCustomerFiles(unittest.TestCase):
 def setUp(self):
  self.client=TestClient(app);self.patch=patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'});self.patch.start()
  self.quote=self.client.post('/api/quotes').json()['quote']['id'];self.base=f'/api/quotes/{self.quote}'
 def tearDown(self):self.patch.stop()
 def request_upload(self,file,path):
  return self.client.post(self.base+path,json={'filename':file.name,'content_base64':base64.b64encode(file.read_bytes()).decode()})
 @unittest.skipUnless(KA.exists(),"User source file not available in installed package")
 def test_ka_sheet_all_150_rows_and_serials(self):
  rows=engine.ingest(KA.name,KA.read_bytes())['assets']
  self.assertEqual(len(rows),150)
  self.assertEqual(rows[0]['serial'],'7310')
  self.assertEqual(rows[0]['site'],'Garnock')
  self.assertTrue(any(a['site']=='West Kilbride' and 'Relocated to' in a['site_status'] for a in rows))
  self.assertTrue(any(a['qty_issue'] for a in rows))
 @unittest.skipUnless(KA.exists(),"User source file not available in installed package")
 def test_ka_full_api_upload(self):
  r=self.request_upload(KA,'/import')
  self.assertEqual(r.status_code,200,r.text[:400]);d=r.json()
  self.assertEqual(d['import_report']['added'],150)
  self.assertEqual(d['summary']['rows'],150)
  self.assertGreater(d['summary']['priced_rows'],0)
 @unittest.skipUnless(AGREEMENT.exists(),"User source file not available in installed package")
 def test_existing_agreement_extraction_is_complete(self):
  r=read_agreement_pdf(AGREEMENT.read_bytes(),AGREEMENT.name)
  self.assertEqual(r['report']['lines'],31)
  self.assertEqual(r['report']['units'],55)
  self.assertEqual(r['report']['previous_total'],'£14,212.43')
  self.assertTrue(r['contract']['agreement_length'].startswith('1 Year'))
  self.assertEqual(r['assets'][0]['serial'],'20404, 20461, 20474, 20475')
  self.assertEqual(r['assets'][-1]['serial'],'507671008623')
 @unittest.skipUnless(AGREEMENT.exists(),"User source file not available in installed package")
 def test_agreement_renewal_only_confirmed_after_extension_checked(self):
  r=self.request_upload(AGREEMENT,'/agreement-import')
  self.assertEqual(r.status_code,200,r.text[:300]);d=r.json()
  self.assertEqual(d['quote']['tier'],'Platinum')
  self.assertEqual(d['quote']['contract_ref'],'C15001/7323')
  self.assertEqual(len(d['quote']['assets']),31)
  self.assertTrue(d['quote']['renewal']['fixed_price_extension'])
  self.assertTrue(any('same-price extension' in x for x in d['summary']['issues']))
  d=self.client.put(self.base,json={'renewal_option_checked':True}).json()
  self.assertFalse(any('same-price extension' in x for x in d['summary']['issues']))
  self.assertEqual(d['summary']['units'],55)
  self.assertFalse(d['summary']['ready']) # ambiguous legacy machines must be resolved
 def test_bulk_selection_only_affects_identical_at_same_site(self):
  text='Equipment,Qty,Site,Model Code,SerialNumber\nRower,1,Site A,,123\nRower,1,Site A,,124\nRower,1,Site B,,125\n'
  r=self.client.post(self.base+'/import',json={'filename':'test.csv','content_base64':base64.b64encode(text.encode()).decode()})
  self.assertEqual(r.status_code,200,r.text)
  q=r.json()['quote'];opt=engine.search_products('rower')[0]
  r=self.client.post(self.base+'/resolve',json={'asset_id':q['assets'][0]['id'],'option':opt,'apply_to_similar':True})
  self.assertEqual(r.status_code,200,r.text)
  rows=r.json()['quote']['assets'];self.assertEqual(rows[0]['selected']['sku'],opt['sku'])
  self.assertEqual(rows[1]['selected']['sku'],opt['sku'])
  self.assertIsNone(rows[2]['selected'])
  self.assertEqual(rows[1]['serial'],'124')
 def test_admin_creates_and_deactivates_local_user(self):
  admin='admin_'+secrets.token_hex(4);person='coord_'+secrets.token_hex(4)
  security.add_user(admin,'Temporary strong admin password!','admin')
  with patch.dict(os.environ,{'SMARTQUOTE_AUTH':'on'}):
   login=self.client.post('/api/auth/login',json={'username':admin,'password':'Temporary strong admin password!'}).json()
   headers={'Authorization':'Bearer '+login['token']}
   r=self.client.post('/api/users',headers=headers,json={'username':person,'role':'coordinator','password':'Strong coordinator password!!!'})
   self.assertEqual(r.status_code,200,r.text)
   users=self.client.get('/api/users',headers=headers).json()['users']
   self.assertTrue(any(u['username']==person for u in users))
   self.assertEqual(self.client.post('/api/users',headers=headers,json={'username':person,'role':'coordinator','password':'Strong coordinator password!!!'}).status_code,400)
   r=self.client.put('/api/users/'+person+'/status',headers=headers,json={'active':False})
   self.assertEqual(r.status_code,200,r.text)
   self.assertEqual(self.client.post('/api/auth/login',json={'username':person,'password':'Strong coordinator password!!!'}).status_code,401)
   self.assertEqual(self.client.put('/api/users/'+admin+'/status',headers=headers,json={'active':False}).status_code,400)

if __name__=='__main__':unittest.main()
