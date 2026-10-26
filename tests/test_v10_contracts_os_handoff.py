"""Fictional cross-platform accepted-quote export regression tests."""
import unittest
from contracts_os_transfer import SCHEMA,from_accepted_pdf_snapshot

def make():
 q={'id':'fictional-quote-id','quote_no':'SQ-TEST-1','customer':'Example Council','site':'Sample Centre',
   'account_ref':'DEMO-ACC','contact':'Demo Person','contact_email':'test@example.invalid',
   'contract_start':'2027-01-01','contract_end':'2027-12-31','tier':'Gold','term':1,
   'visits':1,'pricing_approved':True,'portal_password':'NEVER EXPORT',
   'assets':[
     {'id':'a','code':'100H-AAA','name':'Demo strength machine','model':'100H',
      'qty':1,'serial':'SERIAL-A','selected':{'rrp':10000}},
     {'id':'b','code':'200G-AAB','name':'Demo bike','model':'200G',
      'qty':2,'serial':'SERIAL-B','cover_start':'2027-07-01'}]}
 s={'annual':900.0,'term_total':751.23,'lines':[
      {'id':'a','price':{'annual':600.0,'basis':'catalogue'}},
      {'id':'b','price':{'annual':300.0,'basis':'sage-static-fallback'}}],
    'staged':{'lines':[{'id':'a','period_charge':600.0},{'id':'b','period_charge':151.23}]}}
 return q,s

class TransferContractTests(unittest.TestCase):
 def test_accepted_snapshot_and_staged_dates(self):
  q,s=make();d=from_accepted_pdf_snapshot(q,s,2,'f'*64)
  self.assertEqual(d['schema_version'],SCHEMA)
  self.assertEqual(d['source_revision'],'pdf-v2')
  self.assertEqual(d['pricing']['term_total'],751.23)
  self.assertEqual(d['equipment'][1]['first_period_total'],151.23)
  self.assertEqual(d['equipment'][1]['cover_start'],'2027-07-01')
  self.assertEqual(d['equipment'][1]['serial_numbers'],['SERIAL-B'])
  self.assertEqual(d['customer']['sage_account_ref'],'DEMO-ACC')
  self.assertEqual(d['customer']['sicon_site_ref'],'')
  self.assertNotIn('NEVER EXPORT',str(d))
 def test_pilot_snapshot_never_commercially_approved(self):
  q,s=make()
  self.assertFalse(from_accepted_pdf_snapshot(q,s,1,'f'*64,pilot_snapshot=True)['pricing']['commercially_approved'])
 def test_annual_price_mismatch_refused(self):
  q,s=make();s['annual']=901
  with self.assertRaisesRegex(ValueError,'differs'):from_accepted_pdf_snapshot(q,s,1,'f'*64)
 def test_missing_source_code_refused(self):
  q,s=make();q['assets'][0].pop('code')
  with self.assertRaisesRegex(ValueError,'item code'):from_accepted_pdf_snapshot(q,s,1,'f'*64)
 def test_no_archived_pdf_refused(self):
  q,s=make()
  with self.assertRaisesRegex(ValueError,'issued PDF'):from_accepted_pdf_snapshot(q,s,1,'')
 if __name__=='__main__':unittest.main()
