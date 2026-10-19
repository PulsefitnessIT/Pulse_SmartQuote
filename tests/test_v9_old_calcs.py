"""V9 regression for old calculation source, provenance and quote rules."""
import os,unittest
from pathlib import Path
from historical_calcs import parse_old_calcs,merge_old_calcs
from engine import match_asset,calc_quote
OLD=Path('/mnt/data/Active North Yorkshire - Skipton Leisusre & Wellbeing Hub (Craven Leisure) Calcs c7323 - 2025 - R1.xls')

class OldCalcTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if OLD.exists():cls.parsed=parse_old_calcs(OLD.name,OLD.read_bytes())
 def base(self):return {'assets':[],'files':[],'warnings':[],'customer':'North Yorkshire Council','site':'Skipton Leisure','tier':'Platinum','discount':0,'term':1,'visits':1}
 @unittest.skipUnless(OLD.exists(),'User-supplied previous calculation not present')
 def test_31_historical_lines_55_machines(self):
  self.assertEqual((self.parsed['line_count'],self.parsed['machine_count']),(31,55))
 @unittest.skipUnless(OLD.exists(),'User-supplied previous calculation not present')
 def test_reconcile_original_price_source(self):
  d=self.parsed
  self.assertAlmostEqual(d['source_line_sum_unrounded'],9788.1725,places=3)
  self.assertEqual(d['previous_quote_annual'],14212.43)
  self.assertAlmostEqual(round(d['source_line_sum_unrounded']*1.2*1.1*1.1,2),14212.43,places=2)
 @unittest.skipUnless(OLD.exists(),'User-supplied previous calculation not present')
 def test_230h_nonstandard_special_charge_is_identified(self):
  item=next(x for x in self.parsed['lines'] if x['code']=='230H')
  self.assertEqual(round(item['historic_annual_unit']-item['historic_rrp']*item['historic_percent']/100,2),79.2)
 @unittest.skipUnless(OLD.exists(),'User-supplied previous calculation not present')
 def test_old_calcs_first_creates_all_31_rows(self):
  q=self.base();r=merge_old_calcs(q,self.parsed,match_asset)
  self.assertEqual(r['added'],31);self.assertEqual(len(q['assets']),31)
  self.assertEqual(calc_quote(q)['units'],55)
 @unittest.skipUnless(OLD.exists(),'User-supplied previous calculation not present')
 def test_agreement_first_matches_exact_historic_codes(self):
  q=self.base()
  for x in self.parsed['lines']:
   q['assets'].append(match_asset({'id':x['code'],'code':x['code'],'name':x['description'],
           'qty':x['qty'],'site':'Skipton Leisure','serial':'SN-'+x['code'],
           'prior_contract_ref':'C15001/7323','source_row':x['source_row']}))
  r=merge_old_calcs(q,self.parsed,match_asset)
  self.assertEqual((r['matched'],r['added'],r['unmatched_codes']),(31,0,[]))
  self.assertEqual(q['assets'][0]['serial'],'SN-751H')
 @unittest.skipUnless(OLD.exists(),'User-supplied previous calculation not present')
 def test_historic_only_rrp_does_not_permit_live_quote(self):
  q=self.base();merge_old_calcs(q,self.parsed,match_asset)
  result=calc_quote(q)
  self.assertEqual(result['priced_rows'],31)
  self.assertFalse(result['ready'])
  self.assertTrue(any('historical only' in x for x in result['issues']))
  for x in q['assets']:
   if x['code']=='WattBPro':self.assertTrue(x.get('historic_rrp'))

if __name__=='__main__':unittest.main()
