import base64, unittest, uuid
from fastapi.testclient import TestClient
import main
from engine import match_asset, price_line, BY_SKU

class WorkflowV4Tests(unittest.TestCase):
 def setUp(self):
  self.c=TestClient(main.app)
  self.id=self.c.post('/api/quotes').json()['quote']['id']
  self.base='/api/quotes/'+self.id
 def test_current_sku_without_service_mapping_is_estimated_not_TBC(self):
  resp=self.c.get('/api/catalog/search',params={'q':'260G-ACC'}).json()['results'][0]
  self.assertEqual(resp['price_origin'],'calculated-estimate')
  self.assertAlmostEqual(resp['monthly_packages']['Gold'],27.84,places=2)
  self.assertEqual(resp['rate_group'],'Treadmill / Elliptical')
 def test_resolving_alternative_without_mapping_prices_the_line(self):
  d=self.c.post(self.base+'/manual',json={'name':'Old rack','sku':'','qty':2}).json()
  aid=d['quote']['assets'][0]['id']
  d=self.c.post(self.base+'/resolve',json={'asset_id':aid,'option':{'sku':'867H-AAA'}})
  self.assertEqual(d.status_code,200,d.text)
  self.assertEqual(d.json()['summary']['priced_rows'],1)
  self.assertGreater(d.json()['summary']['annual'],0)
  self.assertEqual(d.json()['summary']['lines'][0]['price']['basis'],'calculated-estimate')
  self.assertFalse(d.json()['summary']['ready'])
 def test_calculated_estimate_requires_no_separate_approval(self):
  d=self.c.post(self.base+'/manual',json={'sku':'867H-AAA','qty':1}).json()
  self.assertGreater(d['summary']['annual'],0)
  self.c.put(self.base,json={'customer':'Test centre','site':'Test site'})
  self.assertTrue(self.c.get(self.base).json()['summary']['ready'])
  doc=self.c.get(self.base+'/pdf')
  self.assertEqual(doc.status_code,200)
  self.assertTrue(doc.content.startswith(b'%PDF'))
 def test_master_upload_preview_not_live_until_apply(self):
  sku='ZZV4-'+uuid.uuid4().hex[:7].upper()
  csvdata=f'Product Code,Description,Current RRP,Model\n{sku},Verified test machine,5000.00,ZZV4\n'.encode()
  resp=self.c.post('/api/catalog/admin/import/preview',json={'filename':'new_master.csv','content_base64':base64.b64encode(csvdata).decode()})
  self.assertEqual(resp.status_code,200,resp.text)
  data=resp.json()
  self.assertEqual(data['counts']['New'],1)
  self.assertFalse(any(x['sku']==sku for x in self.c.get('/api/catalog/search',params={'q':sku}).json()['results']))
  before=self.c.post('/api/catalog/admin/import/apply',json={'stage_id':data['stage_id'],'operator':'Test Data Owner','reason':'New source master provided for testing','acknowledge':False})
  self.assertEqual(before.status_code,400)
  after=self.c.post('/api/catalog/admin/import/apply',json={'stage_id':data['stage_id'],'operator':'Test Data Owner','reason':'New source master provided for testing','acknowledge':True})
  self.assertEqual(after.status_code,200,after.text)
  self.assertEqual(after.json()['updated'],1)
  search=self.c.get('/api/catalog/search',params={'q':sku})
  self.assertEqual(search.json()['results'][0]['rrp'],5000.0)
  self.assertGreater(search.json()['results'][0]['monthly_packages']['Gold'],0)
 def test_duplicate_master_rows_flag_conflict(self):
  code='TEST-CONFLICT-V4'
  csvdata=f'Product Code,Description,Current RRP\n{code},Test machine,2000.00\n{code},Test machine,2800.00\n'.encode()
  d=self.c.post('/api/catalog/admin/import/preview',json={'filename':'conflict.csv','content_base64':base64.b64encode(csvdata).decode()}).json()
  self.assertEqual(d['counts']['Conflict'],2)
  self.assertNotIn('New',d['counts'])
 def test_single_catalogue_edit_invalidates_open_quote(self):
  sku='ZZV4-'+uuid.uuid4().hex[:8].upper()
  add=self.c.post('/api/catalog/admin/item',json={'item':{'sku':sku,'name':'Prototype rack system','rrp':1600,'model':'ZZV4','rate_group_override':'Standard Equipment','coverage_override':'Approved for maintenance'},'operator':'Test Catalogue Owner','reason':'Pricing and coverage confirmed for regression test'})
  self.assertEqual(add.status_code,200,add.text)
  q=self.c.post(self.base+'/manual',json={'sku':sku,'qty':1})
  self.assertEqual(q.status_code,200,q.text)
  self.c.put(self.base,json={'customer':'Test centre','site':'Test site'})
  a=self.c.get(self.base)
  self.assertTrue(a.json()['summary']['ready'])
  change=self.c.put('/api/catalog/admin/item/'+sku,json={'item':{'sku':sku,'name':'Prototype rack system','rrp':2000,'model':'ZZV4','rate_group_override':'Standard Equipment','coverage_override':'Approved for maintenance'},'operator':'Test Catalogue Owner','reason':'Revised verified source RRP after approval'})
  self.assertEqual(change.status_code,200,change.text)
  fresh=self.c.get(self.base).json()
  self.assertTrue(fresh['summary']['ready'])
  self.assertGreater(fresh['summary']['annual'],a.json()['summary']['annual'])
 def test_download_managed_source(self):
  r=self.c.get('/api/catalog/admin/export.csv')
  self.assertEqual(r.status_code,200,r.text[:200] if r.status_code!=200 else '')
  self.assertIn('monthly_gold',r.text[:500])
  self.assertIn('260G-ACC',r.text)

if __name__=='__main__':unittest.main()
