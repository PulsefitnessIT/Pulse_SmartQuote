"""Realistic mixed-header and reversible grouping regressions (no customer data)."""
import csv
import io
import unittest
from asset_intelligence import normalize_asset, grouped_assets
from engine import ingest, match_asset, price_line, search_historical


class MessyAssetTests(unittest.TestCase):
    @staticmethod
    def asset_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Name', 'Make', 'Model', 'Description', 'Install Date',
                         'Serial Number', 'Correct Serial Number'])
        writer.writerows([
            ['Demo Club', '0', '0', 'PF00108 - Run - Low Impact Elevation Treadmill',
             '44900', '260G-08652.', ''],
            ['Demo Club', '0', '0', 'PF00109 - Run - Low Impact Elevation Treadmill',
             '44900', '260G-09244', ''],
            ['Demo Club', '224B-AAB', 'Group Cycle', 'Group Cycle',
             '44951', '224B-808222', ''],
            ['Demo Club', '224B-AAB', 'Group Cycle', 'Group Cycle',
             '44951', '224B-808253', ''],
            ['Demo Club', '290D', '290D', '290D', '', '430869116', ''],
            ['Demo Club', '290E', '290E', '290E', '', '430869117', ''],
            ['Demo Club', '0', '0', 'PF00090 - Functional Rig', '', '0', ''],
            ['Demo Club', '751G-AAQ', 'Adjustable Incline Bench',
             'Adjustable Incline Bench', '44951', 'bad-serial', 'corrected-serial'],
        ])
        return output.getvalue().encode('utf-8')

    def test_corrects_misplaced_sku_and_explains_family_source(self):
        imported = ingest('messy_mclub.csv', self.asset_csv())
        assets = imported['assets']
        self.assertEqual(len(assets), 8)
        self.assertEqual(assets[0]['asset_tag'], 'PF00108')
        self.assertEqual(assets[0]['model'], '260G')
        self.assertFalse(assets[0]['code'])
        self.assertEqual(assets[0]['source_cells']['name'],
                         'PF00108 - Run - Low Impact Elevation Treadmill')
        self.assertEqual(assets[2]['code'], '224B-AAB')
        self.assertEqual(assets[2]['model'], '224B')
        self.assertEqual(assets[-1]['serial'], 'corrected-serial')
        self.assertEqual(assets[-1]['original_serial'], 'bad-serial')
        self.assertEqual(assets[-1]['source_cells']['install_date'], '44951')

    def test_groups_without_losing_source_serial_or_quantity(self):
        raw = ingest('messy_mclub.csv', self.asset_csv())['assets']
        matches = [match_asset(x) for x in raw]
        totals = {a['id']: price_line(a, 'Standard', 'Gold', 0) for a in matches}
        groups = grouped_assets(matches, totals)
        self.assertEqual(len(groups), 6)
        treadmill = next(g for g in groups if g['representative']['model'] == '260G')
        self.assertEqual(treadmill['qty'], 2)
        self.assertEqual([x['asset_tag'] for x in treadmill['assets']],
                         ['PF00108', 'PF00109'])
        self.assertEqual(len(treadmill['source_rows']), 2)
        cycle = next(g for g in groups if g['representative']['model'] == '224B')
        self.assertEqual(cycle['qty'], 2)
        self.assertIsNone(cycle['price'])  # No verified RRP, so never invent one.
        self.assertEqual(sum(g['qty'] for g in groups), len(raw))

    def test_never_groups_different_sites_or_console_versions(self):
        base = {'id':'1','name':'Upright Cycle','code':'','model':'240G',
                'site':'Newcastle','console':'Console 5','qty':1,'serial':'SER1'}
        b = {**base,'id':'2','site':'Stoke','serial':'SER2'}
        c = {**base,'id':'3','console':'Console 6','serial':'SER3'}
        self.assertEqual(len(grouped_assets([base,b,c])), 3)

    def test_catalogue_history_is_identity_only(self):
        result = search_historical('THIS-IS-NOT-A-MODEL-777', limit=6)
        self.assertTrue(result['evidence_only'])
        self.assertEqual(result['results'], [])


if __name__ == '__main__':
    unittest.main()
