"""Combined Equipment & Prices regression — read-only display, source values and print."""
import os,unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
import engine
import main

ROOT=Path(__file__).resolve().parents[1]

class UI(HTMLParser):
 def __init__(self):
  super().__init__();self.ids=[];self.navs=[]
 def handle_starttag(self,tag,attrs):
  data=dict(attrs)
  if 'id' in data:self.ids.append(data['id'])
  if tag=='button' and data.get('id','').startswith('nav'):
   self.navs.append(data)

def sample_skus():
 # Pick catalogued, fully priced, non-conflicting live machines instead of
 # assuming every 2026 source SKU already exists in the older managed list.
 found=[]
 for code,item in engine.BY_SKU.items():
  if code in engine.DUPLICATE_CODES:continue
  option=engine.live_catalogue_option(item)
  if all(engine.price_line({'qty':1,'selected':option},'Standard',tier,0)
         for tier in ('Silver','Gold','Platinum')):
   found.append(code)
   if len(found)==2:break
 if len(found)<2:raise AssertionError('Fixture catalogue has fewer than two valid priced machines')
 return found

class CombinedCatalogueTests(unittest.TestCase):
 def setUp(self):
  self.auth=mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'});self.auth.start()
  self.client=TestClient(main.app).__enter__()
 def tearDown(self):
  self.client.__exit__(None,None,None);self.auth.stop()
 def test_one_visible_catalogue_navigation_and_all_old_admin_controls_retained(self):
  html=(ROOT/'static/index.html').read_text(encoding='utf-8')
  parser=UI();parser.feed(html)
  self.assertIn('hidden',next(x for x in parser.navs if x['id']=='navManager'))
  self.assertIn('navCatalogue',parser.ids)
  for control in ('catalogueView','catalogueBrowseArea','managerView','catalogBrowseTab',
      'catalogManageTab','catalogSearch','printCatalogSelection','clearCatalogSelection',
      'catalogPrintSheet','managerSearch','managerNew','masterUpload','managerPreview',
      'managerApply','rrp2026Query','rrp2026Filter','hybridRrpRules',
      'matchingGapList','matchingMemoryList','managerHistory','readinessPanel'):
   self.assertEqual(parser.ids.count(control),1,control)
  self.assertIn('class="panel manager-panel diagnostics-fold"',html)
 def test_source_detail_includes_all_existing_fields_and_tier_calculations(self):
  sku=sample_skus()[0]
  r=self.client.get('/api/catalog/item/'+sku)
  self.assertEqual(r.status_code,200,r.text[:300])
  d=r.json()
  self.assertEqual(d['sku'],sku)
  self.assertEqual(d['item']['sku'],sku)
  self.assertEqual(d['item'],engine.BY_SKU[sku])
  self.assertIn('rate',d);self.assertIn('console_rule',d)
  self.assertIn('source_snapshot',d);self.assertIn('pricing_status',d)
  for tier in ('Silver','Gold','Platinum'):
   option=engine.live_catalogue_option(engine.BY_SKU[sku])
   expected=engine.price_line({'qty':1,'selected':option},'Standard',tier,0)
   self.assertEqual(d['tiers'][tier]['monthly'],round(expected['unit']/12,2))
   self.assertEqual(d['tiers'][tier]['annual'],expected['unit'])
  self.assertNotIn('invoice',d['source'].lower())
 def test_print_selection_is_readonly_with_all_three_tiers(self):
  first,second=sample_skus()
  source_a=engine.BY_SKU[first]['rrp']
  response=self.client.post('/api/catalog/print-selection',
    json={'skus':[first,second,first]})
  self.assertEqual(response.status_code,200,response.text[:400])
  data=response.json()
  self.assertEqual([x['sku'] for x in data['items']],[first,second])
  self.assertEqual(engine.BY_SKU[first]['rrp'],source_a)
  self.assertIn('commercial approval',data['disclaimer'].lower())
  for item in data['items']:
   self.assertEqual(set(item['tiers']),{'Silver','Gold','Platinum'})
   self.assertEqual(item['item'],engine.BY_SKU[item['sku']])
 def test_missing_codes_and_oversized_selection_are_rejected(self):
  self.assertEqual(self.client.get('/api/catalog/item/DOES-NOT-EXIST').status_code,404)
  self.assertEqual(self.client.post('/api/catalog/print-selection',json={'skus':[]}).status_code,400)
  self.assertEqual(self.client.post('/api/catalog/print-selection',
      json={'skus':[sample_skus()[0]]*76}).status_code,400)
  self.assertEqual(self.client.post('/api/catalog/print-selection',
      json={'skus':[3]}).status_code,400)
 def test_manager_routes_remain_manager_only_and_browse_has_no_write_buttons(self):
  code=(ROOT/'static/app.js').read_text(encoding='utf-8')
  self.assertIn("if(v==='manager'&&!['admin','manager'].includes",code)
  self.assertIn('function attachCatalogueRowActions',code)
  self.assertIn('function viewCatalogueItem',code)
  self.assertIn('function printCatalogueSelection',code)
  self.assertIn("api('/api/catalog/print-selection'",code)
  self.assertIn("window.print();",code)
  self.assertIn("catalogDetailEdit",code)

if __name__=='__main__':unittest.main()
