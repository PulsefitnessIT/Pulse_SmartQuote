"""Staff-first equipment register and customer-facing agreement schedule regression."""
import os
import unittest
from unittest import mock
import fitz
from fastapi.testclient import TestClient
import engine as E
import main
from asset_intelligence import grouped_assets
from staff_price_guides import guide
from quote_pdf import create_quote_pdf

class ContractFirstTests(unittest.TestCase):
    def test_unconfigured_smith_machine_gets_a_source_based_default(self):
        g=guide({'code':'875G','name':'Smith Machine','model':'875G','console':''})
        self.assertEqual(g['standard_reference']['example_sku'],'875G-AAA')
        self.assertEqual(g['standard_reference']['rrp'],5637.57)
        self.assertEqual(g['standard_reference']['basis'],'STANDARD_FAMILY_REFERENCE_UNVERIFIED')

    def test_console_equipped_bike_must_not_inherit_unconfigured_default(self):
        self.assertIsNone(guide({'code':'240G','name':'Upright Cycle'})['standard_reference'])
        self.assertIsNone(guide({'code':'560G','name':'Leg Extension','console':'7-inch tactile-key'})['standard_reference'])

    def test_special_variant_does_not_auto_reference_base_sku(self):
        self.assertIsNone(guide({'code':'560G','name':'IFI Inclusive Leg Extension'})['standard_reference'])
        self.assertIsNone(guide({'code':'867H','name':'Rack with Platform'})['standard_reference'])

    def test_notes_are_preserved_and_different_notes_do_not_group(self):
        a={'id':'a','code':'875G','name':'Smith Machine','model':'875G','site':'Test site','qty':1,'serial':'SN123','contract_note':'Includes bench'}
        b={**a,'id':'b','serial':'SN124'}
        c={**a,'id':'c','serial':'SN125','contract_note':'Other fittings'}
        grouped=grouped_assets([a,b,c])
        self.assertEqual(len(grouped),2)
        self.assertEqual(grouped[0]['serials'],['SN123','SN124'])
        self.assertEqual(grouped[0]['qty'],2)

    def test_customer_pdf_equipment_schedule_hides_unit_costs_and_keeps_serials(self):
        q=main.defaults()
        q.update({'customer':'Example Parish Council','site':'Example Recreation Centre',
                  'billing_address':'A Road','delivery_address':'B Road','approval_note':'Test only'})
        base={'code':'875G','model':'875G','name':'Counterbalanced Smith Machine',
              'site':'Example Recreation Centre','qty':1,'excluded':False,'contract_note':'Bench included'}
        q['assets']=[{**base,'id':'x1','serial':'SIM-X100'},
                     {**base,'id':'x2','serial':'SIM-X101'}]
        raw=create_quote_pdf(q)
        doc=fitz.open(stream=raw,filetype='pdf')
        first=doc[0].get_text()
        self.assertIn('Serial Number',first)
        self.assertIn('875G',first)
        self.assertIn('SIM-X100',first)
        self.assertIn('SIM-X101',first)
        self.assertIn('Bench included',first)
        self.assertNotIn('Unit Price',first)
        self.assertNotIn('source row',first.lower())
        self.assertIn('ANNUAL',first.upper())
        doc.close()

    def test_new_console_controls_are_explicitly_compact(self):
        from pathlib import Path
        css=(main.ROOT/'static/style.css').read_text()
        js=(main.ROOT/'static/app.js').read_text()
        self.assertIn('.staff-quick-price input[type=radio]',css)
        self.assertIn('width:17px!important',css)
        self.assertIn('technical-asset-details',js)
        self.assertIn('staffApplyStandard',js)

class DraftStandardReferenceAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth=mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'})
        cls.auth.start();cls.client=TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close();cls.auth.stop()

    def test_standard_reference_only_as_draft_and_original_sku_unchanged(self):
        qid=self.client.post('/api/quotes').json()['quote']['id']
        q=main.getq(qid)
        for i in range(2):
            q['assets'].append(E.match_asset({'id':f'smith-{i}','name':'Smith Machine','code':'875G',
                 'model':'875G','site':'Example gym','serial':f'SIM{i}','qty':1,'source_row':i+2,
                 'source_sheet':'Synthetic','console':'','excluded':False}))
        main.persist(q)
        g=self.client.get(f'/api/quotes/{qid}/quick-price/smith-0').json()
        self.assertEqual(g['standard_reference']['example_sku'],'875G-AAA')
        info={'asset_id':'smith-0','example_sku':'875G-AAA','console_key':'not-listed',
              'acknowledge_guide_only':True,'standard_unconfirmed':True,
              'console_verified':False,'apply_to_similar':True}
        ok=self.client.post(f'/api/quotes/{qid}/quick-price',json=info)
        self.assertEqual(ok.status_code,200,ok.text[:500])
        q=ok.json()['quote'];self.assertEqual(len(q['assets']),2)
        for a in q['assets']:
            self.assertEqual(a['code'],'875G')
            self.assertEqual(a['selected']['sku'],'')
            self.assertEqual(a['selected']['reference_sku'],'875G-AAA')
            self.assertTrue(a['guide_reference']['standard_unconfirmed'])
        self.assertFalse(ok.json()['summary']['ready'])
        # Backend refuses to use a standard default for a CV console-bearing SKU.
        q2=main.getq(qid);q2['assets'][0]['console']='7-inch tactile-key';main.persist(q2)
        bad=self.client.post(f'/api/quotes/{qid}/quick-price',json=info)
        self.assertEqual(bad.status_code,400)

    def test_group_note_propagates_only_to_identical_same_site_machines(self):
        qid=self.client.post('/api/quotes').json()['quote']['id']
        q=main.getq(qid)
        for i,site in enumerate(('Centre A','Centre A','Centre B')):
            q['assets'].append(E.match_asset({'id':f'note-{i}','code':'875G','model':'875G',
                    'name':'Smith Machine','site':site,'serial':f'SERIAL-{i}',
                    'qty':1,'excluded':False}))
        main.persist(q)
        ok=self.client.put(f'/api/quotes/{qid}/assets/note-0',json={
            'contract_note':'Includes adjustable bench','note_to_same_group':True})
        self.assertEqual(ok.status_code,200,ok.text[:300])
        assets=ok.json()['quote']['assets']
        self.assertEqual(assets[0]['contract_note'],'Includes adjustable bench')
        self.assertEqual(assets[1]['contract_note'],'Includes adjustable bench')
        self.assertEqual(assets[2].get('contract_note',''),'')
        self.assertEqual(len(grouped_assets(assets)),2)

    def test_contract_note_roundtrip(self):
        qid=self.client.post('/api/quotes').json()['quote']['id']
        q=main.getq(qid)
        q['assets']=[E.match_asset({'id':'noted','code':'875G','model':'875G','name':'Smith Machine',
                   'site':'Sample','qty':1,'serial':'SIM-NOTE','excluded':False})]
        main.persist(q)
        response=self.client.put(f'/api/quotes/{qid}/assets/noted',json={'contract_note':'Bench and attachments included'})
        self.assertEqual(response.status_code,200,response.text[:400])
        self.assertEqual(response.json()['quote']['assets'][0]['contract_note'],'Bench and attachments included')

if __name__=='__main__':unittest.main()
