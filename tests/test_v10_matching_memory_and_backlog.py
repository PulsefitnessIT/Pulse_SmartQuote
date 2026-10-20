"""Matching memory is an audited human suggestion, not an automatic SKU or price."""
import base64
import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('SMARTQUOTE_AUTH','off')
from fastapi.testclient import TestClient
import engine
import main
import matching_memory as memory
from catalogue_gaps import analyse
from asset_intelligence import grouped_assets
from catalogue_readiness import evaluate


class MatchingMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'pilot.sqlite'
        self.mem_patch=patch.object(memory,'DB',self.db)
        self.quote_patch=patch.object(main,'DB',self.db)
        self.mem_patch.start();self.quote_patch.start()
        self.addCleanup(self.mem_patch.stop);self.addCleanup(self.quote_patch.stop)
        self.client=TestClient(main.app)

    def source(self,site='Newcastle',serial='0001',console='',model='260G-0'):
        return {'name':'Low Impact Elevation Treadmill', 'code':'', 'model':model,
                'make':'Pulse Fitness', 'site':site, 'serial':serial,
                'console':console,'qty':1}

    def test_signature_excludes_site_and_serial_not_machine_variant(self):
        self.assertEqual(memory.fingerprint(self.source())[0],
                         memory.fingerprint(self.source(site='London',serial='9999'))[0])
        self.assertNotEqual(memory.fingerprint(self.source())[0],
                            memory.fingerprint(self.source(console='Console 5'))[0])
        self.assertNotEqual(memory.fingerprint(self.source())[0],
                            memory.fingerprint(self.source(model='260G'))[0])
        with self.assertRaisesRegex(ValueError,'original product code or model'):
            memory.fingerprint({'name':'Generic exercise bike'})

    def test_only_explicit_manager_verification_creates_rule(self):
        source=self.source()
        original=engine.BY_SKU['260G-AAS'].copy()
        self.assertIsNone(memory.recall(source,0))
        recorded=memory.remember(source,'260G-AAS','Pricing Manager',
                         'Physical identification and verified console photograph.',0)
        self.assertTrue(recorded['created'])
        recalled=memory.recall(self.source(site='Manchester',serial='ANOTHER'),0)
        self.assertEqual(recalled['sku'],'260G-AAS')
        self.assertTrue(recalled['operator_confirmation_required'])
        self.assertTrue(recalled['identity_only'])
        self.assertEqual(recalled['catalogue_option']['rrp'],original['rrp'])
        self.assertTrue(memory.recall(source,1)['stale'])
        self.assertEqual(engine.BY_SKU['260G-AAS'],original)
        # Conflicting current catalogues require revocation, not last-writer-wins.
        with self.assertRaisesRegex(ValueError,'DIFFERENT'):
            memory.remember(source,'260G-ACA','Pricing Manager',
                            'Second investigation with recorded source evidence',0)
        with self.assertRaisesRegex(ValueError,'revocation reason'):
            memory.revoke(recorded['rule_id'],'Pricing Manager','wrong')
        memory.revoke(recorded['rule_id'],'Pricing Manager','Previous catalogue identification incorrect')
        self.assertIsNone(memory.recall(source,0))
        self.assertEqual(memory.all_rules()[0]['status'],'revoked')

    def test_quote_resolution_and_repeat_import_never_autoselect(self):
        q1=self.client.post('/api/quotes').json()['quote']
        body=('Name,Make,Model,Description,Serial Number\n'
              'Demo Club,0,260G-0,Low Impact Elevation Treadmill,CY-001\n'
              'Demo Club,0,260G-0,Low Impact Elevation Treadmill,CY-002\n').encode()
        def imp(q):
            return self.client.post('/api/quotes/'+q['id']+'/import',json={
                'filename':'import.csv','content_base64':base64.b64encode(body).decode()})
        first=imp(q1)
        self.assertEqual(first.status_code,200,first.text)
        assets=first.json()['quote']['assets']
        self.assertIsNone(assets[0]['selected'])
        route='/api/quotes/'+q1['id']+'/resolve'
        unauthorized=patch.object(main,'actor',lambda _: {'username':'readonly','role':'coordinator'})
        with unauthorized:
            rejected=self.client.post(route,json={'asset_id':assets[0]['id'],
              'option':{'sku':'260G-AAS'},'remember_match':True,
              'review_evidence':'Verified physical machine with serial and photo'})
            self.assertEqual(rejected.status_code,403)
        selected=self.client.post(route,json={'asset_id':assets[0]['id'],
              'option':{'sku':'260G-AAS'},'remember_match':True,'apply_to_similar':True,
              'review_evidence':'Verified exact SKU and console against physical source label'})
        self.assertEqual(selected.status_code,200,selected.text)
        self.assertEqual(len(memory.all_rules()),1)
        self.assertEqual(len(selected.json()['quote']['assets']),2)
        q2=self.client.post('/api/quotes').json()['quote']
        newer=imp(q2)
        self.assertEqual(newer.status_code,200)
        newer_asset=newer.json()['quote']['assets'][0]
        self.assertIsNone(newer_asset['selected'])
        report=self.client.get('/api/quotes/'+q2['id']+'/match-review/'+newer_asset['id'])
        self.assertEqual(report.status_code,200,report.text)
        saved=report.json()['reviewed_match']
        self.assertEqual(saved['sku'],'260G-AAS')
        self.assertTrue(saved['operator_confirmation_required'])
        self.assertEqual(self.client.get('/api/quotes/'+q2['id']).json()['summary']['annual'],0.0)
        history=self.client.get('/api/catalog/admin/matching-memory')
        self.assertEqual(history.status_code,200)
        self.assertEqual(history.json()['active'],1)

    def test_backlog_order_and_escaped_export(self):
        q={'id':'q0','quote_no':'SQ-TEST-1','customer':'=C8','site':'Test Facility',
           'tier':'Gold','level':'Standard','discount':0,'visits':1,'term':1,
           'assets':[engine.match_asset({'id':'t1','name':'Group Cycle','model':'224B',
                        'code':'224B-AAB','site':'Test Facility','qty':20}),
                     engine.match_asset({'id':'t2','name':'Low Impact Treadmill','model':'260G-0',
                        'site':'Test Facility','qty':4})]}
        result=analyse([q]);self.assertEqual(result['counts']['unpriced_units'],24)
        self.assertEqual(result['counts']['unpriced_groups'],2)
        self.assertEqual(result['items'][0]['units'],20)
        self.assertEqual(main._safe_csv(result['items'][0]['customer']),"'=C8")
        # Quote-created test register has no rows until specifically imported.
        self.assertEqual(self.client.get('/api/catalog/admin/matching-gaps').status_code,200)
        result=self.client.get('/api/catalog/admin/matching-gaps.csv')
        self.assertEqual(result.status_code,200)
        self.assertIn('Original description',result.text)

    def test_mclub_import_coverage_uses_actual_source_rows(self):
        path=Path('/mnt/data/M Club Newcastle.xlsx')
        if not path.is_file():self.skipTest('Private sample workbook not mounted in CI')
        assets=engine.ingest('M Club Newcastle.xlsx',path.read_bytes())['assets']
        self.assertEqual(len(assets),165)
        quote={'id':'mclub','quote_no':'TEST','tier':'Gold','level':'Standard','discount':0,
               'term':1,'visits':1,'assets':[engine.match_asset(a) for a in assets]}
        result=analyse([quote])
        self.assertEqual(result['counts']['total_units'],165)
        self.assertGreater(result['counts']['unpriced_units'],0)
        self.assertEqual(result['counts']['priced_units']+result['counts']['unpriced_units'],165)

    def test_anonymised_165_row_complex_register_regression(self):
        """CI-safe regression for an M Club shaped file: no private serials/site."""
        buff=io.StringIO(newline='');w=csv.writer(buff)
        w.writerow(['Name','Make','Model','Description','Serial Number','Vendor comments'])
        idx=0
        def add(qty,make,model,description,prefix='SER'):
            nonlocal idx
            for _ in range(qty):
                idx+=1
                # Synthetic asset tags and serials, not real customer identifiers.
                w.writerow(['Example Site',make,model,
                            f'PF{900000+idx} - {description}',
                            f'{prefix}-SIMULATED-{idx:04d}',f'Dummy ref {idx}'])
        add(21,'224B-AAB','Group Cycle','Group Cycle','224B')
        add(14,'0','0','Run - Low Impact Elevation Treadmill','260G')
        add(7,'0','0','Elliptical Cross-Trainer','280G')
        add(6,'0','0','Upright Cycle','240G')
        # 68 distinct equipment types, 49 with two machines and 19 singletons.
        for ix in range(68):
            add(2 if ix<49 else 1,'0','0',f'Synthetic Specialised Equipment Type {ix+1:03d}')
        parsed=engine.ingest('Synthetic_Mixed_CRM_Export.csv',buff.getvalue().encode())
        self.assertEqual(len(parsed['assets']),165)
        groups=grouped_assets(parsed['assets'])
        self.assertEqual(len(groups),72)
        self.assertEqual(sum(g['qty'] for g in groups),165)
        self.assertEqual(max(g['qty'] for g in groups),21)
        self.assertEqual(len({a['serial'] for a in parsed['assets']}),165)
        self.assertTrue(all(a['source_raw_columns'] for a in parsed['assets']))

    def test_metadata_only_source_does_not_meet_year_requirement(self):
        # Synthetic archive: regression must remain valid after the missing
        # physical 2021 n workbook is integrated into real deployments.
        import json
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            data.mkdir()
            (data/'historical_catalogue_index.json').write_text(json.dumps({
                'records': {'SYN-001':{'sku':'SYN-001','evidence_only':True}},'aliases':{}}))
            (data/'historical_catalogue_manifest.json').write_text(json.dumps({
                'unique_skus':1,'alias_codes':0,'archive_review_status':'Not approved',
                'worksheets':[{'year':y,'status':'read','equipment_rows':0 if y==2021 else 1,
                               'metadata_only':y==2021} for y in range(2020,2027)]}))
            result=evaluate(tmp)
            self.assertIn(2021,result['historical']['metadata_only_years'])
            self.assertNotIn(2021,result['historical']['source_years'])
            self.assertFalse(result['historical']['archive_ready'])
            self.assertTrue(any('Metadata-only' in x for x in result['warnings']))

if __name__=='__main__':unittest.main()