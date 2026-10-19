"""V5: reproduce coordinator workflow without renewal, review or approval gates."""
import unittest,base64
from pathlib import Path
from fastapi.testclient import TestClient
from main import app

class QuickQuoteV5Tests(unittest.TestCase):
 def setUp(self):
  self.c=TestClient(app)
  self.base='/api/quotes/'+self.c.post('/api/quotes').json()['quote']['id']

 def test_reselected_unknown_prices_quote_and_pdf_without_approval(self):
  r=self.c.post(self.base+'/manual',json={'name':'Unknown storage rack','qty':1}).json()
  aid=r['quote']['assets'][0]['id']
  self.assertEqual(r['summary']['priced_rows'],0)
  chosen=self.c.post(self.base+'/resolve',json={'asset_id':aid,'option':{'sku':'866H-AAB'}})
  self.assertEqual(chosen.status_code,200,chosen.text)
  self.assertEqual(chosen.json()['summary']['priced_rows'],1)
  self.assertGreater(chosen.json()['summary']['monthly'],0)
  self.assertTrue(any('calculated' in s.lower() for s in chosen.json()['summary']['advisories']))
  r=self.c.put(self.base,json={'customer':'Test leisure centre','site':'Building 1'})
  self.assertEqual(r.status_code,200,r.text)
  self.assertTrue(r.json()['summary']['ready'],r.json()['summary']['issues'])
  self.assertEqual(r.json()['quote']['status'],'Ready to generate')
  pdf=self.c.get(self.base+'/pdf')
  self.assertEqual(pdf.status_code,200,pdf.text[:200] if pdf.status_code!=200 else '')
  self.assertIn('QUOTE.pdf',pdf.headers['content-disposition'])
  self.assertTrue(pdf.content.startswith(b'%PDF'))

 def test_matching_legacy_equipment_price_no_second_gate(self):
  a=self.c.post(self.base+'/manual',json={'name':'Old treadmill','sku':'R260G-5.00DRPW','qty':1})
  self.assertEqual(a.status_code,200)
  self.assertEqual(a.json()['summary']['priced_rows'],1)
  self.c.put(self.base,json={'customer':'Trial customer','site':'Test facility'})
  self.assertTrue(self.c.get(self.base).json()['summary']['ready'])

 def test_sample_spreadsheet_unpriced_only_raises_missing_price(self):
  f=Path(__file__).resolve().parents[1]/'samples'/'Pulse_Messy_Asset_List_Sample.xlsx'
  self.assertTrue(f.exists())
  d=self.c.post(self.base+'/import',json={'filename':f.name,'content_base64':base64.b64encode(f.read_bytes()).decode()})
  self.assertEqual(d.status_code,200,d.text)
  out=d.json()
  self.assertEqual(len(out['quote']['assets']),6)
  self.assertGreater(out['summary']['priced_rows'],0)
  self.assertTrue(all(('unresolved' in x or 'choose a machine' in x or 'Enter the customer' in x or 'no usable price' in x) for x in out['summary']['issues']),out['summary']['issues'])

 def test_missing_price_stays_draft(self):
  self.c.post(self.base+'/manual',json={'name':'Machine with no identifier','qty':1})
  d=self.c.put(self.base,json={'customer':'Test centre','site':'Site A'}).json()
  self.assertFalse(d['summary']['ready'])
  self.assertEqual(d['summary']['priced_rows'],0)
  pdf=self.c.get(self.base+'/pdf')
  self.assertEqual(pdf.status_code,200)
  self.assertIn('DRAFT.pdf',pdf.headers['content-disposition'])

 def test_discount_below_minimum_stays_blocked(self):
  self.c.post(self.base+'/manual',json={'sku':'260G-AAS','qty':1})
  r=self.c.put(self.base,json={'customer':'T','site':'A','discount':60})
  self.assertEqual(r.status_code,200)
  self.assertFalse(r.json()['summary']['ready'])
  self.assertTrue(any('minimum' in i.lower() for i in r.json()['summary']['issues']))

 def test_legacy_approval_endpoint_is_not_required(self):
  r=self.c.post(self.base+'/approve',json={})
  self.assertEqual(r.status_code,410)

if __name__=='__main__':unittest.main()
