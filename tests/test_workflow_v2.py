import unittest
from fastapi.testclient import TestClient
from engine import match_asset,calc_quote
from main import app
from io import BytesIO

class WorkflowV2Tests(unittest.TestCase):
 def setUp(self):
  self.client=TestClient(app)
  self.q=self.client.post('/api/quotes').json()['quote']
  self.id=self.q['id']
  self.base=f'/api/quotes/{self.id}'
 def test_add_blank_manual_edit_and_preview(self):
  r=self.client.post(self.base+'/manual',json={'sku':'','qty':1})
  self.assertEqual(r.status_code,200,r.text)
  item=r.json()['quote']['assets'][0];aid=item['id']
  edit={'name':'Uncatalogued fixed exercise machine','model':'TEST MODEL','qty':2,'manual_annual_unit':175.25,'manual_price_source':'Signed commercial authorisation TEST-777','display_name':'Cardio machine - verified rate','serial':'ABC1-ABC2'}
  r=self.client.put(f'{self.base}/assets/{aid}',json=edit)
  self.assertEqual(r.status_code,200,r.text)
  data=r.json();self.assertEqual(data['summary']['annual'],350.50)
  self.assertEqual(data['quote']['assets'][0]['display_name'],'Cardio machine - verified rate')
  self.assertFalse(data['summary']['ready'])
  r=self.client.put(self.base,json={'customer':'Leidos Supply Ltd','site':'3 RSME Regiment','billing_address':'8 Monarch Court\nBristol','delivery_address':'Gibraltar Barracks\nCamberley','customer_ref':'654351','account_ref':'00001482'})
  self.assertEqual(r.status_code,200,r.text)
  self.assertTrue(r.json()['summary']['ready'])
  pdf=self.client.get(self.base+'/pdf')
  self.assertEqual(pdf.status_code,200,pdf.text[:200] if pdf.status_code!=200 else '')
  self.assertTrue(pdf.content.startswith(b'%PDF'))
 def test_exclusion_and_bad_reason(self):
  q=self.client.post(self.base+'/manual',json={'sku':'','qty':1}).json()['quote']
  aid=q['assets'][0]['id']
  r=self.client.put(f'{self.base}/assets/{aid}',json={'excluded':True,'exclusion_reason':'Not in contract scope'})
  self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(r.json()['summary']['excluded_rows'],1)
  self.assertEqual(r.json()['summary']['annual'],0)
  self.assertIn('Include at least one machine',str(r.json()['summary']['issues']))
 def test_selected_catalogue_retained_when_editing_qty(self):
  q=self.client.post(self.base+'/manual',json={'sku':'260G-AAS','qty':1}).json()['quote']
  a=q['assets'][0];aid=a['id']
  opt=a['selected']
  self.assertTrue(opt)
  r=self.client.post(self.base+'/resolve',json={'asset_id':aid,'option':opt})
  self.assertEqual(r.status_code,200,r.text)
  before=r.json()['quote']['assets'][0]
  r=self.client.put(f'{self.base}/assets/{aid}',json={'name':before['name'],'code':before['code'],'model':before['model'],'console':before['console'],'make':before['make'],'qty':4,'display_name':'Renamed for customer'})
  self.assertEqual(r.status_code,200,r.text)
  after=r.json()['quote']['assets'][0]
  self.assertEqual(after['match_type'],'Reviewed catalogue choice')
  self.assertEqual(after['qty'],4)
  self.assertEqual(after['selected']['sku'],'260G-AAS')
 def test_csv_import_then_resolve_conflict_by_exclusion(self):
  import base64
  contents=b'Machine,Units,Product Code,Serial Number\nTreadmill,3,260G-AAS,SN1\nIssue machine,1,305H-AGC,SN2\n'
  r=self.client.post(self.base+'/import',json={'filename':'messy.csv','content_base64':base64.b64encode(contents).decode()})
  self.assertEqual(r.status_code,200,r.text)
  data=r.json();self.assertEqual(len(data['quote']['assets']),2)
  self.assertEqual(data['quote']['assets'][1]['match_type'],'Conflicting duplicate SKU')
  aid=data['quote']['assets'][1]['id']
  r=self.client.put(f'{self.base}/assets/{aid}',json={'excluded':True,'exclusion_reason':'Customer declined maintenance coverage'})
  self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(r.json()['summary']['excluded_rows'],1)
  self.assertEqual(r.json()['summary']['priced_rows'],1)
 def test_invalid_manual_price_rejected(self):
  aid=self.client.post(self.base+'/manual',json={'sku':'','qty':1}).json()['quote']['assets'][0]['id']
  self.assertEqual(self.client.put(f'{self.base}/assets/{aid}',json={'manual_annual_unit':-100}).status_code,400)
  self.assertEqual(self.client.put(f'{self.base}/assets/{aid}',json={'qty':0}).status_code,400)

if __name__=='__main__':unittest.main()
