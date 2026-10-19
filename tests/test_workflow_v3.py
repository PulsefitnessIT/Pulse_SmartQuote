import unittest
from fastapi.testclient import TestClient
from engine import match_asset,search_products,price_line,sku_option,BY_SKU,calc_quote,display_console
from main import app

class WorkflowV3Tests(unittest.TestCase):
 def setUp(self):
  self.client=TestClient(app)
  self.q=self.client.post('/api/quotes').json()['quote']
  self.base='/api/quotes/'+self.q['id']
 def test_rowing_unknown_has_real_source_recommendations_but_not_auto_price(self):
  a=match_asset({'name':'Rowing machine unknown','code':'','model':'','make':'','qty':2,'id':'a'})
  self.assertIsNone(a['selected'])
  self.assertGreaterEqual(len(a['candidates']),2)
  self.assertTrue(all('rower' in x['name'].lower() for x in a['candidates']))
  self.assertEqual(a['match_confidence'],0)
  self.assertIn('confirm',a['issues'][0].lower())
 def test_description_first_search_and_monthly_prices(self):
  r=self.client.get('/api/catalog/search',params={'q':'rowing machine'})
  self.assertEqual(r.status_code,200,r.text)
  self.assertTrue(any('Rower' in s['name'] for s in r.json()['results']))
  r=self.client.get('/api/catalog/search',params={'q':'260G-AAS'})
  option=r.json()['results'][0]
  self.assertEqual(option['sku'],'260G-AAS')
  self.assertEqual(option['monthly_packages']['Gold'],round(price_line({'selected':sku_option(BY_SKU['260G-AAS']),'qty':1},'Standard','Gold',0)['unit']/12,2))
  self.assertTrue(all(k in option['monthly_packages'] for k in ['Silver','Gold','Platinum']))
 def test_source_bad_console_no_longer_shown_as_no_console(self):
  p=BY_SKU['260G-ACD'];self.assertEqual(p['console'],'No Console / N/A')
  display=display_console(p)
  self.assertEqual(display['label'],'7" Tactile Key Console')
  self.assertEqual(display['status'],'description_only')
  r=self.client.get('/api/catalog/search',params={'q':'260G-ACD'})
  v=r.json()['results'][0]
  self.assertEqual(v['console_display'],'7" Tactile Key Console')
  self.assertGreater(v['monthly_packages']['Gold'],0)
  self.assertEqual(v['price_origin'],'calculated-estimate')
 def test_add_machine_by_description_make_without_sku(self):
  r=self.client.post(self.base+'/manual',json={'name':'Concept2 indoor rower','make':'Concept2','qty':3})
  self.assertEqual(r.status_code,200,r.text)
  a=r.json()['quote']['assets'][0]
  self.assertEqual(a['qty'],3);self.assertEqual(a['make'],'Concept2')
  self.assertIsNone(a['selected']);self.assertGreaterEqual(len(a['candidates']),1)
 def test_unknown_and_conflicted_product_code_can_be_captured_without_guess(self):
  for sku in ['ABC123-OLD','38-326-AAA']:
   r=self.client.post(self.base+'/manual',json={'name':'Storage rack','sku':sku,'qty':1})
   self.assertEqual(r.status_code,200,r.text)
   a=r.json()['quote']['assets'][-1]
   self.assertIsNone(a['selected'])
  self.assertEqual(r.json()['quote']['assets'][-1]['match_type'],'Conflicting duplicate SKU')
 def test_hidden_price_band_cannot_change_prices(self):
  q={'level':'Minimum','tier':'Gold','discount':0,'term':1,'visits':1,'customer':'Test','site':'Test','assets':[match_asset({'name':'Treadmill','code':'260G-AAS','qty':1,'id':'a'})]}
  s=calc_quote(q)
  expected=price_line(q['assets'][0],'Standard','Gold',0)['annual']
  self.assertEqual(s['annual'],expected)
  r=self.client.put(self.base,json={'level':'Minimum','discount':5})
  self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(r.json()['quote']['level'],'Standard')

if __name__=='__main__':unittest.main()
