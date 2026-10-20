"""Whole-quote RRP protection: anonymised product-code examples, no private customer data."""
import unittest
import engine
from staff_price_guides import _index
from contract_pricing_preview import source_sku_reference

CODES=('260G-ABB','280G-AAZ','230H-AAA','240G-AAN','250G-AAN',
 '200C-AAB','205C-AAB','211F-AAB','290D-AAA','SC240MA-AAA',
 '305H-AEP','310H-AEP','314H-AEP','325H-ACL','342H-AAO','382H-ACL',
 '447H-AEP','560H-AEP','562H-AEP','576H-AEP','605H-ACL',
 '347H-AAB','302H-AAI','307H-AAI','377H-AAI','444H-AAI','572H-AAI','573H-AAI',
 '186G-AAC','650G-AAQ','665G-AAQ','751G-AAQ','785G-AAQ','800G-AAB',
 '820G-AAQ','830G-AAQ','866H-AAB','875G-AAQ','866H-ZZW','38-610-AAA','224B-AAB')
SPEC='1x100kg Weight Stack Tower with 10.1" Touchscreen Console in Sand Black with Black / Carbon Fibre Upholstery Red Stitching (NFC Compatible)(110V/220V)'

def equipment(code,i):
 model=code.split('-')[0];rows=_index().get(model,{}).get(code,[])
 desc=rows[0]['name'] if rows else {'314H-AEP':'Premium Pec Deck (Independent Arm) '+SPEC,
     '200C-AAB':'Premium StepMill with ST22.2 Console in Black',
     'SC240MA-AAA':'Body Composition Analyser',
     '38-610-AAA':'Club Line Tire Flip Machine'}.get(code,'Unknown equipment')
 return engine.match_asset({'id':f'DEMO-{i}','code':code,'model':model,
     'name':desc,'source_description':desc,'make':'Pulse Fitness',
     'invoice_ref':'SYNTHETIC','qty':21 if code=='224B-AAB' else 1,
     'serial':f'SYN-{i}','site':'Synthetic Site','source_row':i+1})

def quote(items):
 return {'assets':items,'tier':'Gold','discount':0,'term':1,'visits':1,
         'customer':'Synthetic Company','site':'Synthetic Site'}

class CompleteInvoicePricing(unittest.TestCase):
 def test_every_included_sku_is_priced_or_explicitly_flagged(self):
  self.assertEqual(len(CODES),41)
  items=[equipment(code,i) for i,code in enumerate(CODES)]
  summary=engine.calc_quote(quote(items))
  self.assertEqual(summary['priced_rows'],39)
  self.assertGreaterEqual(summary['source_rrp_reconciled_rows'],20)
  self.assertEqual({x['code'] for x in summary['pricing_exceptions']},{'200C-AAB','SC240MA-AAA'})
  missing={x['id'] for x in summary['pricing_exceptions']}
  for item,line in zip(items,summary['lines']):
   if line['price'] is None:self.assertIn(item['id'],missing)
   else:self.assertGreater(line['price']['annual'],0)
  self.assertFalse(summary['ready'])
 def test_group_cycles_have_documented_source_rrp_draft(self):
  item=equipment('224B-AAB',2)
  self.assertEqual(source_sku_reference(item)['rrp'],2278.92)
  result=engine.calc_quote(quote([item]))
  self.assertEqual(result['lines'][0]['price']['annual'],1435.77)
  self.assertFalse(result['ready'])
 def test_historical_sale_value_must_not_be_used_as_rrp(self):
  item=equipment('200C-AAB',1);item['invoice_unit_sale_price']='10072.43'
  result=engine.calc_quote(quote([item]))
  self.assertIsNone(result['lines'][0]['price'])
  self.assertEqual(result['pricing_exceptions'][0]['code'],'200C-AAB')
 def test_explicit_wrong_console_cannot_override_source(self):
  item=equipment('305H-AEP',1)
  item['name']=item['source_description']='Shoulder Press with 7" tactile key console'
  self.assertIsNone(source_sku_reference(item))
  self.assertTrue(engine.calc_quote(quote([item]))['pricing_exceptions'])

if __name__=='__main__':unittest.main()
