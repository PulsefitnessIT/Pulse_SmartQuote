"""V8 regression: realistic legacy maintenance agreement renewals."""
from __future__ import annotations
import base64, os, unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app
import engine

PDF=Path('/mnt/data/Active North Yorkshire - Skipton Leisure & Wellbeing Maintenance Agreement c7323 - 1 YEAR with option to extend for a further year - 2025 - R1(1).pdf')

def old_asset(code,name,qty=1,console=''):
    return {'code':code,'model':code,'name':name,'qty':qty,'console':console,'site':'Sample Leisure','serial':'SN0102',
            'source_row':2,'source_sheet':'Agreement page 3','prior_contract_ref':'SAMPLE-OLD-1'}

class HistoricPricingTests(unittest.TestCase):
    def test_model_code_produces_traceable_reference_price(self):
        a=engine.match_asset(old_asset('305H','Shoulder Press with Console',1,'Console - model not specified'))
        self.assertEqual(a['match_type'],'Historic family RRP estimate')
        self.assertEqual(a['selected']['reference_model'],'305H')
        self.assertEqual(a['selected']['price_origin'],'historic-family-estimate')
        self.assertEqual(a['selected']['sku'],'')  # No invented exact SKU
        p=engine.price_line(a,'Standard','Gold',0)
        self.assertIsNotNone(p)
        self.assertEqual(p['unit'],engine.money(a['selected']['rrp']*0.03))

    def test_non_agreement_asset_is_not_automatically_assigned_historic_sku(self):
        a=old_asset('305H','Shoulder Press with Console')
        a.pop('prior_contract_ref')
        m=engine.match_asset(a)
        self.assertIsNone(m['selected'])

    def test_smith_bench_included_not_no_bench(self):
        m=engine.match_asset(old_asset('875H','Counterbalanced Smith Machine incl. Bench'))
        self.assertIsNotNone(m['selected'])
        p=engine.BY_SKU[m['selected']['reference_sku']]
        self.assertIn('incl',p['name'].lower())
        self.assertNotIn('not included',p['name'].lower())

    def test_rack_quoted_without_adding_platform(self):
        m=engine.match_asset(old_asset('866H','Half Rack',2))
        p=engine.BY_SKU[m['selected']['reference_sku']]
        self.assertNotIn('platform',p['name'].lower())

    def test_ski_erg_floor_variant_and_serial_kept(self):
        a=old_asset('Skierg5Floor','Skierg PM5 Floor')
        m=engine.match_asset(a)
        self.assertIn('floor mounted',engine.BY_SKU[m['selected']['reference_sku']]['name'].lower())
        self.assertEqual(m['serial'],'SN0102')
        self.assertEqual(m['code'],'Skierg5Floor')

    def test_legacy_fusion_console_is_not_claimed_to_be_exact(self):
        m=engine.match_asset(old_asset('260G-6.0','Fusion Run 3 with 19" monitor',7,'19" monitor'))
        self.assertEqual(m['selected']['reference_model'],'260G')
        self.assertIn('NOT an exact equivalent',m['selected']['reason'])
        self.assertEqual(m['console'],'19" monitor')
        self.assertFalse(m['selected']['sku'])

    def test_unpriced_models_are_not_given_false_prices(self):
        for code,desc in [('270G-6.0','Fusion Lateral Trainer with 19" monitor'),('WattBPro','Watt Bike Pro')]:
            a=engine.match_asset(old_asset(code,desc))
            self.assertIsNone(a['selected'],code)
            self.assertIsNone(engine.price_line(a,'Standard','Platinum',0),code)

    def test_if_current_catalogue_variant_is_exact_it_stays_exact(self):
        sku='260G-AAS'
        a=old_asset(sku,'Club Line Treadmill 10 inch')
        m=engine.match_asset(a)
        self.assertEqual(m['match_type'],'Exact SKU')
        self.assertEqual(m['selected']['sku'],sku)

    @unittest.skipUnless(PDF.exists(),'Original customer PDF not installed with application')
    def test_full_real_agreement_api_and_existing_quote_upgrade(self):
        with patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'}):
            client=TestClient(app)
            created=client.post('/api/quotes').json()['quote']['id']
            base='/api/quotes/'+created
            raw=base64.b64encode(PDF.read_bytes()).decode()
            d=client.post(base+'/agreement-import',json={'filename':PDF.name,'content_base64':raw}).json()
            self.assertEqual(d['import_report']['lines'],31)
            self.assertEqual(d['summary']['units'],55)
            self.assertEqual(d['summary']['priced_rows'],29)
            self.assertEqual(d['summary']['estimated_rows'],28)
            self.assertEqual(d['quote']['assets'][0]['code'],'751H')
            self.assertEqual(d['quote']['assets'][0]['serial'],'20404, 20461, 20474, 20475')
            self.assertEqual(d['quote']['renewal']['previous_annual'],'£14,212.43')
            self.assertFalse(d['summary']['ready'])
            self.assertTrue(any('same-price extension' in issue for issue in d['summary']['issues']))
            # Simulate a quote previously imported by V7 with old candidate-only rows.
            import main
            original=main.getq(created)
            downgrade=next(a for a in original['assets'] if a['code']=='305H')
            downgrade['selected']=None
            downgrade['candidates']=[]
            original['engine_version']=7
            main.persist(original)
            loaded=client.get(base).json()
            reloaded=next(a for a in loaded['quote']['assets'] if a['code']=='305H')
            self.assertEqual(reloaded['selected']['price_origin'],'historic-family-estimate')
            # Still a draft with two truly unsupported machines; importantly no total issue.
            r=client.get(base+'/pdf')
            self.assertEqual(r.status_code,200)
            self.assertTrue(r.content.startswith(b'%PDF'))

if __name__=='__main__':unittest.main()
