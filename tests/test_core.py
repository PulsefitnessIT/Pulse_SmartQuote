"""Run from project root: python -m unittest discover -s tests -v"""
import unittest,io,zipfile
from engine import ingest,match_asset,calc_quote,price_line,DUPLICATE_CODES,PRICING

class SmartQuoteTests(unittest.TestCase):
 def test_real_sku_match(self):
  a=match_asset({'id':'1','code':'260G-AAS','qty':3,'source_row':2})
  self.assertEqual(a['selected']['name'].split()[0],'Club')
  self.assertEqual(a['selected']['rrp'],9373.16)
  self.assertEqual(a['selected']['rate_group'],'Treadmill / Elliptical')
 def test_quantity_and_rate(self):
  a=match_asset({'id':'1','code':'260G-AAS','qty':3,'source_row':2})
  self.assertEqual(price_line(a,'Standard','Gold',0)['annual'],1054.47)
  self.assertEqual(price_line(a,'Standard','Gold',0)['unit']*3,price_line(a,'Standard','Gold',0)['annual'])
  self.assertEqual(price_line(a,'Standard','Silver',0)['annual'],843.57)
 def test_provisional_source_price_is_quotable_without_second_review(self):
  a=match_asset({'id':'1','code':'260G-AAS','qty':3,'source_row':2})
  q={'customer':'Riverside','site':'A','assets':[a],'tier':'Gold','level':'Standard','term':1}
  self.assertTrue(calc_quote(q)['ready'])
 def test_manager_approval_release(self):
  a=match_asset({'id':'1','code':'260G-AAS','qty':3,'source_row':2})
  q={'customer':'Riverside','site':'A','assets':[a],'tier':'Gold','level':'Standard','term':1,'approver':'Quality Manager','pricing_approved':True,'line_reviews_approved':True}
  self.assertTrue(calc_quote(q)['ready'])
 def test_duplicates_are_unquotable(self):
  self.assertIn('280G-ABS',DUPLICATE_CODES)
  self.assertIsNone(match_asset({'code':'280G-ABS'})['selected'])
 def test_csv_messy_header(self):
  t=b'Random export title\nMachine, Units, Product Code, Serial Number\nTreadmill, 3, 260G-AAS, SN1\nTOTAL,3,,\n'
  d=ingest('weird.csv',t)
  self.assertEqual(len(d['assets']),1)
  self.assertEqual(d['assets'][0]['qty'],3)
 def test_no_name_or_code_header(self):
  with self.assertRaises(ValueError):ingest('bad.csv',b'Unknown Field, Price, Cost\nFoo,100,50\n')
 def test_unknown_equipment_not_priced(self):
  self.assertIsNone(match_asset({'code':'MADE-UP-999','model':'ZZZZ'})['selected'])
 def test_source_tiers(self):
  self.assertEqual(PRICING['tiers'],{'Silver':.8,'Gold':1.,'Platinum':1.3})

if __name__=='__main__':unittest.main()
