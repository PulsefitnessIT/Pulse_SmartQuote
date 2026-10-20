"""Guided catalogue matching: never infer a new SKU/RRP from a family or alias."""
import csv
import io
import os
import unittest

os.environ.setdefault('SMARTQUOTE_AUTH','off')
from fastapi.testclient import TestClient
import engine
import main
from smart_candidates import family_code


class SmartReviewTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_family_parser_keeps_revision(self):
        self.assertEqual(family_code('250G-0'), ('250G', True))
        self.assertEqual(family_code('250G'), ('250G', False))
        self.assertEqual(family_code('224B-AAB'), ('', False))
        self.assertEqual(family_code('not a model'), ('', False))

    def test_legacy_suffix_offers_review_not_automated_price(self):
        raw={'id':'review-test-1','code':'','model':'250G-0',
             'name':'R-Cycle - Recumbent Cycle','console':'','qty':1}
        result=engine.match_asset(raw)
        self.assertIsNone(result['selected'])
        self.assertEqual(result['match_type'],'Model candidate')
        report=engine.review_candidates(result)
        self.assertTrue(report['operator_confirmation_required'])
        self.assertEqual(report['source_variant'],'250G-0')
        self.assertTrue(report['candidates'])
        self.assertTrue(all(v['operator_confirmation_required'] for v in report['candidates']))
        self.assertTrue(any('Legacy model suffix' in ', '.join(v['review_flags'])
                            for v in report['candidates']))

    def test_discontinued_cycle_does_not_auto_price_new_model(self):
        original={'id':'review-test-2','code':'224B-AAB','model':'224B',
                  'name':'Group Cycle','site':'Demo site','qty':1}
        matched=engine.match_asset(original)
        self.assertIsNone(matched['selected'])
        self.assertIsNone(engine.price_line(matched,'Standard','Gold',0))
        report=engine.review_candidates(matched)
        self.assertEqual(report['model_family'],'224B')
        self.assertTrue(any(c.get('service_key','').startswith('224B |') and not c['rrp']
                            for c in report['candidates']))
        self.assertTrue(any('Different/current model' in c['reason']
                            for c in report['candidates']))
        self.assertTrue(all(c['operator_confirmation_required'] for c in report['candidates']))

    def test_stable_exact_sku_and_approved_rrp_not_modified(self):
        original=engine.BY_SKU['260G-AAS'].copy()
        asset=engine.match_asset({'id':'review-test-3','code':'260G-AAS','qty':3})
        self.assertEqual(asset['selected']['rrp'],9373.16)
        self.assertEqual(engine.price_line(asset,'Standard','Gold',0)['annual'],1054.47)
        report=engine.review_candidates(asset)
        self.assertEqual(report['candidates'][0]['sku'],'260G-AAS')
        self.assertEqual(engine.BY_SKU['260G-AAS'],original)

    def test_api_group_review_and_csv_are_nonmutating(self):
        q=self.client.post('/api/quotes').json()['quote']
        root=f"/api/quotes/{q['id']}"
        data=('Name,Make,Model,Description,Serial Number\n'
              'Demo Club,224B-AAB,Group Cycle,Group Cycle,CY-001\n'
              'Demo Club,224B-AAB,Group Cycle,Group Cycle,CY-002\n').encode()
        import base64
        up=self.client.post(root+'/import',json={'filename':'group.csv',
                                    'content_base64':base64.b64encode(data).decode()})
        self.assertEqual(up.status_code,200,up.text)
        assets=up.json()['quote']['assets']
        self.assertEqual(len(assets),2)
        before=self.client.get(root).json()['summary']['annual']
        review=self.client.get(root+'/match-review/'+assets[0]['id'])
        self.assertEqual(review.status_code,200,review.text)
        self.assertEqual(review.json()['group']['quantity'],2)
        self.assertEqual(len(review.json()['group']['serials']),2)
        self.assertFalse(review.json()['already_priced'])
        self.assertTrue(review.json()['candidates'])
        csv_response=self.client.get(root+'/matching-report.csv')
        self.assertEqual(csv_response.status_code,200,csv_response.text)
        records=list(csv.DictReader(io.StringIO(csv_response.text.removeprefix('\ufeff'))))
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['Machine quantity'],'2')
        self.assertIn('CY-001',records[0]['Serial numbers'])
        self.assertIn('CY-002',records[0]['Serial numbers'])
        self.assertEqual(self.client.get(root).json()['summary']['annual'],before)

    def test_unknown_spreadsheet_columns_preserved_for_roundtrip(self):
        import base64
        q=self.client.post('/api/quotes').json()['quote']
        path=f"/api/quotes/{q['id']}"
        payload=('Name,Make,Model,Description,Serial Number,Vendor Note,Internal Ref\n'
                 'Demo Club,224B-AAB,Group Cycle,Group Cycle,SER-ABC,Needs workshop review,=1+1\n'
                 'Demo Club,224B-AAB,Group Cycle,Group Cycle,SER-DEF,Keep note,REF2\n').encode()
        response=self.client.post(path+'/import',json={'filename':'export.csv',
            'content_base64':base64.b64encode(payload).decode()})
        self.assertEqual(response.status_code,200,response.text)
        originals=response.json()['quote']['assets'][0]['source_raw_columns']
        self.assertTrue(any(x['header']=='Vendor Note' and x['value']=='Needs workshop review' for x in originals))
        self.assertTrue(any(x['header']=='Internal Ref' and x['value']=='=1+1' for x in originals))
        data=self.client.get(path+'/asset-register.csv')
        self.assertEqual(data.status_code,200)
        table=list(csv.DictReader(io.StringIO(data.text.removeprefix('\ufeff'))))
        self.assertEqual(len(table),2)
        self.assertEqual(table[0]['Original column 6 - Vendor Note'],'Needs workshop review')
        self.assertEqual(table[0]['Original column 7 - Internal Ref'],"'=1+1")
        self.assertEqual(table[0]['Active serial'],'SER-ABC')
        self.assertEqual(table[1]['Active serial'],'SER-DEF')
        self.assertEqual(len(response.json()['quote']['assets']),2)

    def test_csv_formula_injection_escaped(self):
        for value in ('=CMD()', '+2+3', '-1+1','@SUM(A1:A2)', '\t=HYPERLINK()'):
            self.assertTrue(main._safe_csv(value).startswith("'"))
        self.assertEqual(main._safe_csv('Pulse Fitness'),'Pulse Fitness')

if __name__=='__main__':
    unittest.main()
