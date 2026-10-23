"""Dated Sage Sales Price fallback: master priority, category rules, annual refresh."""
import csv,io,os,tempfile,unittest
from unittest.mock import patch
import engine,sage_price_source as sage
from test_v10_invoice_full_pricing_coverage import equipment,quote
ROWS=[
 ['200C-AAB','StepMill','Cardiovascular Equipment','14710.75'],
 ['314H-AEP','Pec Deck','Strength Equipment','9591.43'],
 ['305H-AEP','Shoulder Press','Strength Equipment','9202.21'],
 ['SC240MA-AAA','Body Composition','Service & Labour','4000'],
 ['PART-567','Drive Belt','CV Parts','250'],
 ['WRONG-1','Some console','Strength Equipment','0'],
 ['BENCH-123','Flat Bench','Free Weight Benches & Racks','1000']]
def csvfile(rows=ROWS):
 buf=io.StringIO();w=csv.writer(buf)
 w.writerow(['Code','Name','Product Group Description','Sales Price']);w.writerows(rows)
 return buf.getvalue().encode('utf-8')
def priced(code,name):
 a=engine.match_asset({'id':code,'code':code,'model':code.split('-')[0],
  'name':name,'source_description':name,'make':'Pulse Fitness','invoice_ref':'SYNTHETIC',
  'qty':1,'source_row':1})
 return engine.calc_quote({'assets':[a],'customer':'Test','site':'Test','tier':'Gold','visits':1})
class SageFallbackTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,{'SMARTQUOTE_SAGE_DB':self.tmp.name+'/pilot.db'})
  self.env.start();sage.active.cache_clear()
 def tearDown(self):
  sage.active.cache_clear();self.env.stop();self.tmp.cleanup()
 def install(self):return sage.install('Sage.csv',csvfile(),'2026-10-23','Pricing Manager')
 def test_import_filters_parts_and_retains_review_date(self):
  result=self.install()
  self.assertEqual(result['usable_rows'],4)
  self.assertEqual(result['review_due'],'2027-10-23')
  self.assertIsNone(sage.lookup('PART-567'))
  self.assertIsNone(sage.lookup('SC240MA-AAA'))
 def test_unknown_master_pec_deck_prices_automatically(self):
  self.install();s=priced('314H-AEP','Premium Pec Deck')
  p=s['lines'][0]['price']
  self.assertEqual(p['rrp'],9591.43)
  self.assertEqual(p['unit'],287.74)
  self.assertEqual(p['basis'],'sage-static-fallback')
  self.assertFalse(p['review_required'])
  self.assertEqual(s['sage_fallback_rows'],1)
 def test_stepmill_uses_specific_rate_not_standard(self):
  self.install();p=priced('200C-AAB','StepMill')['lines'][0]['price']
  self.assertEqual(p['rate'],0.038)
  self.assertEqual(p['unit'],engine.money(14710.75*.038))
 def test_master_always_wins_over_sage(self):
  self.install();p=engine.calc_quote(quote([equipment('305H-AEP',1)]))['lines'][0]['price']
  self.assertEqual(p['rrp'],9011.14)
  self.assertNotEqual(p['basis'],'sage-static-fallback')
 def test_invoice_selling_price_and_non_equipment_never_price(self):
  self.install();a=engine.match_asset({'id':'x','code':'SC240MA-AAA',
    'name':'Body Composition Analyser','invoice_unit_sale_price':45000,'qty':1})
  p=engine.calc_quote({'assets':[a],'customer':'Test','site':'Test','tier':'Gold','visits':1})
  self.assertIsNone(p['lines'][0]['price'])
 def test_reimport_keeps_history(self):
  self.install()
  sage.install('Sage-2026-update.csv',csvfile([*ROWS[:2],['305H-AEP','Shoulder Press','Strength Equipment','9300'],*ROWS[3:]]),'2026-10-22','Manager')
  import sqlite3
  with sqlite3.connect(sage.database()) as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM sage_price_snapshots').fetchone()[0],2)
 def test_wrong_format_cannot_overwrite_active_snapshot(self):
  self.install()
  with self.assertRaises(ValueError):sage.install('bad.csv',b'wrong,headers,here,test\n1,2,3,4','2026-10-23')
  self.assertEqual(sage.status()['usable_rows'],4)
if __name__=='__main__':unittest.main()
