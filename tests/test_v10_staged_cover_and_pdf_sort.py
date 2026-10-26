"""Staged quotation and PDF order smoke checks."""
import unittest
from datetime import date
from staged_contracts import pro_rata,machine_sort_key,valid_contract
from asset_intelligence import grouped_assets
import engine

class StageRules(unittest.TestCase):
 def test_inclusive_and_leap(self):
  self.assertEqual(pro_rata(600,date(2027,7,1),date(2027,12,31)),302.47)
  self.assertEqual(pro_rata(366,date(2028,1,1),date(2028,12,31)),366.0)
 def test_natural_code_order(self):
  codes=['300H-A','20A-A','100C-A']
  self.assertEqual([x['code'] for x in sorted(({'code':x} for x in codes),key=machine_sort_key)],['20A-A','100C-A','300H-A'])
 def test_staged_quote_total(self):
  q={'tier':'Gold','term':1,'customer':'Example','site':'Site','visits':1,
     'contract_start':'2027-01-01','contract_end':'2027-12-31',
     'assets':[{'id':'a','code':'300H-A','name':'Machine','qty':1,'manual_annual_unit':600,'manual_price_source':'Contract-approved written rate'},
               {'id':'b','code':'20A-A','name':'Machine','qty':1,'manual_annual_unit':600,'manual_price_source':'Contract-approved written rate','cover_start':'2027-07-01'}]}
  summary=engine.calc_quote(q)
  self.assertEqual(summary['annual'],1200)
  self.assertEqual(summary['term_total'],902.47)
  self.assertEqual(len(grouped_assets(q['assets'])),2)
 def test_invalid_period(self):
  with self.assertRaises(ValueError):valid_contract('2027-12-31','2027-01-01')
