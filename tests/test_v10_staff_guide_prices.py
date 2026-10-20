"""Console-first guide price acceptance tests, using synthetic staff data only."""
import os
import unittest
from unittest import mock
from fastapi.testclient import TestClient
import engine as E
import staff_price_guides as G
import main

class GuideSourceTests(unittest.TestCase):
    def test_strength_family_without_explicit_console_has_indicative_price(self):
        result=G.guide({'code':'560G','name':'Leg Extension'},'Gold',0)
        self.assertEqual(result['status'],'GUIDE_ONLY')
        self.assertEqual(result['model'],'560G')
        self.assertEqual(result['min_monthly_unit'],14.83)
        self.assertGreaterEqual(len(result['bands']),2)
        base=next(x for x in result['bands'] if x['key']=='not-listed')
        self.assertEqual(base['min_rrp'],5931.60)
        self.assertTrue(any(x['key']=='7-key' for x in result['bands']))

    def test_cv_missing_console_shows_different_configurations(self):
        result=G.guide({'code':'240G','name':'Upright Cycle'})
        self.assertTrue(any(x['key']=='18-touch' for x in result['bands']))
        self.assertTrue(any(x['key']=='7-key' for x in result['bands']))
        self.assertTrue(result['console_unconfirmed'])

    def test_source_reference_is_not_pretended_to_be_exact_machine(self):
        a={'code':'615G','name':'Rotary Torso'}
        src=G.guide(a)
        entry=src['bands'][0]['prices'][0]
        data,band,price=G.picked(a,entry['example_sku'],src['bands'][0]['key'])
        self.assertEqual(price['rrp'],entry['rrp'])
        with self.assertRaises(ValueError):G.picked(a,'615G-XX-DUMMY','not-listed')
        with self.assertRaises(ValueError):G.picked(a,entry['example_sku'],'unknown')

    def test_unsupported_manufacturer_or_missing_model_is_not_estimated(self):
        self.assertIsNone(G.guide({'name':'PL Wide Chest Press'}))
        self.assertIsNone(G.guide({'code':'560G','name':'Leg Extension','make':'Technogym'}))

class GuidedQuoteAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patcher=mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'})
        cls.patcher.start();cls.client=TestClient(main.app)
    @classmethod
    def tearDownClass(cls):
        cls.client.close();cls.patcher.stop()

    def new_quote(self):
        q=self.client.post('/api/quotes').json()['quote'];return q['id']

    def attach_test_rows(self,qid):
        q=main.getq(qid)
        for i in range(3):
            a={'id':f'synthetic-guide-{i}','code':'560G','name':'560G - Leg Extension','model':'560G',
                'console':'','site':'Demo gym','source_row':i+2,'source_sheet':'Synthetic','qty':1,
                'serial':str(1000+i),'excluded':False,'manual_annual_unit':None}
            q['assets'].append(E.match_asset(a))
        main.persist(q);return q

    def test_guide_preview_apply_bulk_and_customer_issuance_blocked(self):
        qid=self.new_quote();self.attach_test_rows(qid)
        aid='synthetic-guide-0'
        resp=self.client.get(f'/api/quotes/{qid}/quick-price/{aid}')
        self.assertEqual(resp.status_code,200,resp.text[:200]);src=resp.json()
        self.assertEqual(src['min_monthly_unit'],14.83)
        band=next(x for x in src['bands'] if x['key']=='not-listed')
        entry=band['prices'][0]
        path=f'/api/quotes/{qid}/quick-price'
        base={'asset_id':aid,'example_sku':entry['example_sku'],
              'console_key':band['key'],'acknowledge_guide_only':True,
              'console_verified':True,'apply_to_similar':True}
        bad=self.client.post(path,json={**base,'console_verified':False})
        self.assertEqual(bad.status_code,400)
        bad=self.client.post(path,json={**base,'example_sku':'560G-FAKE'})
        self.assertEqual(bad.status_code,400)
        good=self.client.post(path,json=base)
        self.assertEqual(good.status_code,200,good.text[:400]);q=good.json()['quote']
        self.assertEqual(len(q['assets']),3)
        self.assertEqual(sum(a['selected']['price_origin']=='staff-guided-estimate' for a in q['assets']),3)
        self.assertEqual(len({a['serial'] for a in q['assets']}),3)
        for asset in q['assets']:
            self.assertEqual(asset['code'],'560G')
            self.assertFalse(asset['selected']['sku'])
            self.assertEqual(asset['guide_reference']['rrp'],entry['rrp'])
        summary=good.json()['summary']
        self.assertEqual(summary['priced_rows'],3)
        self.assertFalse(summary['ready'])
        self.assertTrue(any('provisional family RRP' in w for w in summary['issues']))

    def test_cannot_replace_confirmed_machine_with_silent_estimate(self):
        qid=self.new_quote()
        q=main.getq(qid)
        q['assets']=[{'id':'fixed-row','code':'560G-AAA','name':'Leg Extension',
            'selected':{'sku':'560G-AAA','rrp':1000,'rate_group':'Standard Equipment','eligible':'Yes'},
            'source_row':1,'qty':1,'site':'Demo gym','model':'560G'}]
        main.persist(q)
        band=G.guide(q['assets'][0])['bands'][0]
        bad=self.client.post(f'/api/quotes/{qid}/quick-price',json={
            'asset_id':'fixed-row','example_sku':band['prices'][0]['example_sku'],
            'console_key':band['key'],'acknowledge_guide_only':True,'console_verified':True})
        self.assertEqual(bad.status_code,409)

if __name__=='__main__':unittest.main()
