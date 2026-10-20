"""Contract table sorts, sensible controls, and full source-description guide prices."""
import os,unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
import engine as eng, main
from contract_pricing_preview import exact_config_from_description,draft_reference

DESC='Premium StepMill with 18.5" (Cirrus V4) Touchscreen Console, Apple/Samsung Watch Connectivity, Content Mirroring & Wireless Charging in Sand Black (TRAKK Compatible)(110V/220V)'

class DescriptionPricingTests(unittest.TestCase):
 def test_mclub_stepmill_reordered_features_exact_source_rrp(self):
  a={'id':'demo','code':'','model':'200H','name':DESC,'source_description':DESC,'make':'StepMill','qty':2,'serial':'SYNTH-1'}
  m=exact_config_from_description(a)
  self.assertIsNotNone(m)
  self.assertEqual(m['reference_sku'],'200H-AAF')
  self.assertEqual(m['rrp'],11544.77)
  q={'assets':[eng.match_asset(a)],'tier':'Gold','discount':0,'term':1,'visits':1,'customer':'Sample','site':'Sample'}
  summary=eng.calc_quote(q)
  price=summary['lines'][0]['price']
  self.assertTrue(price['annual']>0)
  self.assertEqual(price['preview_confidence'],'exact_source_configuration')
  self.assertEqual(price['basis'],'staff-guided-estimate')
  self.assertFalse(summary['ready'])
  self.assertEqual(q['assets'][0].get('selected'),None)
  self.assertTrue(any('provisional' in s.lower() for s in summary['issues']))
 def test_different_source_features_cannot_be_assumed(self):
  self.assertIsNone(exact_config_from_description({'model':'200H','name':'StepMill'}))
  self.assertIsNone(exact_config_from_description({'model':'200H','name':'Premium StepMill with 18.5 touchscreen'}))
  self.assertIsNone(exact_config_from_description({'model':'200H','name':DESC,'make':'Stairmaster'}))
  wrong={ 'model':'200H','name':DESC.replace('200H','200H'),'make':'StepMill','console':''}
  wrong['name']=wrong['name'].replace('Content Mirroring','Content Mirroring & EGYM')
  different=exact_config_from_description(wrong)
  self.assertTrue(different is None or different['rrp']!=11544.77)
 def test_strength_baseline_automatic_draft_but_not_approved(self):
  a={'id':'smith','model':'875G','code':'875G','name':'Smith Machine','make':'Pulse Fitness','qty':2,'site':'Example'}
  self.assertEqual(draft_reference(a)['reference_sku'],'875G-AAA')
  q={'assets':[eng.match_asset(a)],'tier':'Gold','discount':0,'term':1,'visits':1,'customer':'Example','site':'Example'}
  price=eng.calc_quote(q)['lines'][0]['price'];self.assertEqual(price['basis'],'staff-guided-estimate')
  self.assertEqual(price['reference_sku'],'875G-AAA')
  self.assertEqual(price['qty'],2)
  self.assertFalse(eng.calc_quote(q)['ready'])

 def test_exact_console_strength_skus_get_draft_prices_not_bare_guides(self):
  specs=[
   ('305H-AEP','Premium Shoulder Press (Converging Axis)',9011.14,270.33,'305H-AEP'),
   ('310H-AEP','Premium Chest Press (Converging Axis)',8948.58,268.46,'310H-AEP'),
   ('314H-AEP','Premium Pec Deck (Independent Arm)',9438.75,283.16,'314H-AEX')]
  suffix=' 1x100kg Weight Stack Tower with 10.1" Touchscreen Console in Sand Black with Black / Carbon Fibre Upholstery Red Stitching (NFC Compatible)(110V/220V)'
  for code,label,rrp,annual,reference in specs:
   with self.subTest(code=code):
    original={'id':code,'code':code,'model':code.split('-')[0],'name':label+suffix,'qty':1,'serial':'DEMO-'+code,'make':'Pulse Fitness'}
    asset=eng.match_asset(original)
    q={'assets':[asset],'tier':'Gold','discount':0,'term':1,'visits':1,'customer':'Demo','site':'Demo'}
    line=eng.calc_quote(q)['lines'][0]['price']
    self.assertIsNotNone(line)
    self.assertEqual(line['rrp'],rrp)
    self.assertEqual(line['annual'],annual)
    self.assertEqual(line['reference_sku'],reference)
    if code in ('305H-AEP','310H-AEP'):
     self.assertEqual(line['basis'],'source-rrp-calculated')
     self.assertFalse(line['review_required'])
    else:
     self.assertEqual(line['basis'],'staff-guided-estimate')
     self.assertTrue(line['review_required'])
    self.assertFalse(eng.calc_quote(q)['ready'])
    self.assertEqual(asset['code'],code)
    self.assertIsNone(asset.get('selected'))

 def test_sku_requires_consistent_console_details_and_legacy_pec_deck_is_not_mislabeled(self):
  from contract_pricing_preview import source_sku_reference,draft_reference
  self.assertIsNone(source_sku_reference({'code':'305H-AEP','model':'305H','name':'Shoulder Press with 7" tactile key console'}))
  self.assertIsNone(draft_reference({'code':'314H-AEP','model':'314H','name':'Premium Pec Deck'}))
  self.assertIsNone(source_sku_reference({'code':'305H-AEP','model':'305H','name':'Premium Shoulder Press 1x100kg with 10.1" touchscreen console','make':'Technogym'}))
  src=draft_reference({'code':'314H-AEP','model':'314H','name':'Premium Pec Deck (Independent Arm) 1x100kg Weight Stack Tower with 10.1" Touchscreen Console in Sand Black with Carbon Fibre Upholstery Red Stitching (NFC Compatible)'})
  self.assertEqual(src['confidence'],'unique_strength_spec_price')
  self.assertNotEqual(src['reference_sku'],'314H-AEP')

class StaffUiTests(unittest.TestCase):
 def test_headers_have_sort_buttons_for_all_six_columns(self):
  html=(Path(__file__).resolve().parents[1]/'static/index.html').read_text()
  for key in ['machine','description','qty','unit','annual','status']:
   self.assertIn('data-asset-sort="'+key+'"',html)
 def test_checkboxes_before_editor_save_actions_and_normal_sized(self):
  js=(Path(__file__).resolve().parents[1]/'static/app.js').read_text()
  css=(Path(__file__).resolve().parents[1]/'static/style.css').read_text()
  self.assertIn("querySelector('.editor-actions').insertAdjacentHTML('beforebegin'",js)
  self.assertIn('scope-checkbox-row',css)
  self.assertIn('aria-sort',js)
 def test_repriced_rows_accessible_through_draft_review_filter(self):
  js=(Path(__file__).resolve().parents[1]/'static/app.js').read_text()
  self.assertIn("basis==='staff-guided-estimate'",js)
  self.assertIn('sortEquipmentGroups',js)

if __name__=='__main__':unittest.main()
