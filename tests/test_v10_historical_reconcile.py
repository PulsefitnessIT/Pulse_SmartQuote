"""Guardrail coverage for combining physical historical masters and recovered newer-year snapshots."""
import json
import tempfile
import unittest
from pathlib import Path
from historical_master import source_info
from historical_reconcile import reconcile
from install_historical_catalogue import validate


def dump(path, obj):
    path.write_text(json.dumps(obj), encoding='utf-8')


class HistoricalReconcileTests(unittest.TestCase):
    def fixture(self, root):
        physical, recovered = root / 'physical', root / 'recovered'
        physical.mkdir(); recovered.mkdir()
        dump(physical / 'historical_catalogue_index.json', {
            'records': {
                '260G-AAS': {'sku':'260G-AAS','name':'2024 treadmill','model':'260G','console':'5.0','year':2024,'rev':'t','evidence_only':True},
                '2021-ONLY': {'sku':'2021-ONLY','name':'Original 2021 bike','year':2021,'rev':'n','evidence_only':True},
            }, 'aliases': {'OLD-260G': ['260G-AAS']}
        })
        dump(physical / 'historical_equipment_master.json',{
            '260G-AAS': {'provenance':[{'year':2021,'revision':'n','sheet':'Assembled Database','source':'2021.n.xlsx','row':3},
                                       {'year':2024,'revision':'t','sheet':'Assembled Database','source':'2024.t.xlsx','row':10}]},
            '2021-ONLY': {'provenance':[{'year':2021,'revision':'n','sheet':'Assembled Database','source':'2021.n.xlsx','row':6}]},
        })
        dump(physical / 'historical_catalogue_manifest.json', {
            'source_files':2,'unique_skus':2,'snapshots':3,
            'worksheets':[{'file':'2021.n.xlsx','year':2021,'revision':'n','sheet':'Assembled Database','status':'read','equipment_rows':2},
                          {'file':'2024.t.xlsx','year':2024,'revision':'t','sheet':'Assembled Database','status':'read','equipment_rows':1}]})
        dump(recovered / 'historical_catalogue_index.json', {
            'records': {
                '260G-AAS': {'sku':'260G-AAS','name':'2026 treadmill','model':'260G','console':'6','year':2026,'rev':'w','evidence_only':True,
                             'provenance':[{'year':2024,'revision':'unlettered','source':'2024.csv','row':10},{'year':2026,'revision':'w','source':'2026.w.xlsx','row':20}]},
                'LEGACY-ONLY': {'sku':'LEGACY-ONLY','name':'Discontinued','year':2022,'rev':'r','first_seen':2020,'evidence_only':True,
                                'provenance':[{'year':2022,'revision':'r','source':'2022.r.csv','row':11}]},
            }, 'aliases': {'OLD-260G':['260G-AAS'], 'OLD-LEGACY':['LEGACY-ONLY']}})
        dump(recovered / 'historical_catalogue_manifest.json', {
            'unique_skus':2,'snapshots':5,
            'worksheets':[{'file':'2024.csv','year':2024,'status':'read','equipment_rows':2},
                          {'file':'2026.w.xlsx','year':2026,'revision':'w','status':'read','equipment_rows':3}]})
        return physical,recovered

    def test_combine_preserves_recent_config_and_raw_2021(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); p,r=self.fixture(root)
            report=reconcile(p,r,root/'output')
            idx=json.loads((root/'output/historical_catalogue_index.json').read_text())
            self.assertEqual(report['unique_skus'],3)
            self.assertEqual(idx['records']['260G-AAS']['console'],'6')
            self.assertEqual(idx['records']['260G-AAS']['first_seen'],2021)
            self.assertIn('2021:n',idx['records']['260G-AAS']['source_revisions'])
            self.assertIn('2026:w',idx['records']['260G-AAS']['source_revisions'])
            self.assertEqual(idx['records']['2021-ONLY']['year'],2021)
            self.assertIn('LEGACY-ONLY',idx['records'])
            self.assertFalse(report['archive_review_status'].lower()=='approved')
            self.assertEqual(report['reconciliation']['recovered_only_unique_skus'],1)
            self.assertEqual(report['reconciliation']['new_only_unique_skus'],1)
            self.assertEqual([x for x in report['worksheets'] if x.get('year')==2024][0]['file'],'2024.t.xlsx')
            self.assertNotIn('rrp',idx['records']['260G-AAS'])
            # 2025 absence is checked by installer, not silently fabricated.
            with self.assertRaisesRegex(ValueError,'2020'):
                validate(root/'output')

    def test_reject_approved_price_leakage(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p,r=self.fixture(root)
            val=json.loads((r/'historical_catalogue_index.json').read_text());val['records']['260G-AAS']['rrp']=9900
            dump(r/'historical_catalogue_index.json',val)
            with self.assertRaisesRegex(ValueError,'identity-only'):
                reconcile(p,r,root/'output')

    def test_reject_incorrect_provenance(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p,r=self.fixture(root)
            val=json.loads((p/'historical_equipment_master.json').read_text());val.pop('2021-ONLY')
            dump(p/'historical_equipment_master.json',val)
            with self.assertRaisesRegex(ValueError,'provenance'):
                reconcile(p,r,root/'output')

    def test_parenthesised_versions_keep_original_revision(self):
        self.assertEqual(source_info(Path('2020 - Master - Transition_Iss.a(1).xlsx')),(2020,'a'))
        self.assertEqual(source_info(Path('2022 - Master - Transition_Iss.p.xlsx')),(2022,'p'))
        self.assertEqual(source_info(Path('CH - 2020 - Master - Transition_Iss.i.xlsx')),(2020,'i'))


if __name__=='__main__':unittest.main()
