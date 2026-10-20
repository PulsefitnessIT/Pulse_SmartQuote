"""Regression for auditable 2026 source RRP evidence; no live repricing."""
import csv
import io
import os
import unittest
from unittest.mock import patch
os.environ.setdefault('SMARTQUOTE_AUTH','off')

from fastapi.testclient import TestClient
import engine
import main
import rrp_reconciliation as R


class RrpReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client=TestClient(main.app)
        cls.rows=R.reconcile(engine.CAT,engine.DUPLICATE_CODES)

    def test_exact_master_source_and_coverage(self):
        source=R.source()
        self.assertEqual(source['source_file'],'Full Master Price List 24-08-2026.xlsx')
        self.assertEqual(source['source_sha256'],'fbc544db9365f6b47cd37fb3e085e5c75acc03042eff5d6f820ffa55f80b3433')
        self.assertEqual(len(source['rows']),4640)
        self.assertEqual(len(self.rows),4632)
        self.assertFalse(R.summary(self.rows)['commercial_approved'])
        self.assertFalse(R.summary(self.rows)['write_enabled'])
        self.assertTrue(all(not ({'sell_price','supplier_cost','purchase_price'} & set(x)) for x in source['rows']))

    def test_every_source_price_conflict_is_flagged_and_not_promoted(self):
        conflicted={x['sku']:x for x in self.rows if x['status']=='source_price_conflict'}
        self.assertEqual(set(conflicted),{'189G-AAB','280G-ABS','314H-ABH','385H-ACE'})
        self.assertEqual(conflicted['280G-ABS']['source_prices'],[9720.75,9941.80])
        self.assertIsNone(conflicted['280G-ABS']['source_rrp'])
        self.assertEqual(len(conflicted['314H-ABH']['sources']),2)
        self.assertEqual(R.summary(self.rows)['status_counts']['source_price_conflict'],4)

    def test_existing_source_rrp_variance_visible_without_mutating_source_catalogue(self):
        original=dict(engine.BY_SKU['260G-ABZ'])
        row=next(x for x in self.rows if x['sku']=='260G-ABZ')
        self.assertEqual(row['source_rrp'],9053.01)
        self.assertEqual(row['live_rrp'],8877.87)
        self.assertEqual(row['difference_gbp'],175.14)
        self.assertEqual(row['status'],'rrp_difference')
        self.assertEqual(engine.BY_SKU['260G-ABZ'],original)
        self.assertFalse(row['commercial_approved'])
        self.assertEqual(row['sources'][0]['column'],'BA')

    def test_negative_price_differences_are_signed(self):
        self.assertEqual(R._signed_difference(R._money(100), R._money(105.50)), -5.50)
        negative=[row for row in self.rows if row['difference_gbp'] is not None and row['difference_gbp'] < 0]
        # Negative differences must remain visible to the pricing reviewer, not be clamped to zero.
        if negative:
            self.assertTrue(all(x['source_rrp'] < x['live_rrp'] for x in negative))

    def test_unknown_console_family_never_selects_a_single_variant(self):
        family=R.family(self.rows,'260G')
        self.assertEqual(family['total'],77)
        self.assertTrue(family['must_confirm_exact_variant'])
        self.assertGreater(family['max_unapproved_rrp'],family['min_unapproved_rrp'])
        self.assertTrue(any(x['sku']=='260G-AAS' for x in family['items']))
        self.assertIn('Confirm',family['notice'])
        with self.assertRaises(ValueError):R.family(self.rows,'260G; DROP TABLE inventory')

    def test_legacy_group_cycle_exact_variant_remains_source_evidence(self):
        item=next(x for x in self.rows if x['sku']=='224B-AAB')
        self.assertEqual(item['source_rrp'],2278.92)
        self.assertEqual(item['model'],'224B')
        self.assertEqual(item['sources'][0]['sheet'],'Main Gym')
        self.assertFalse(item['commercial_approved'])

    def test_filtered_manager_search_and_bounded_paging(self):
        d=R.search(self.rows,'260G','rrp_difference',0,5)
        self.assertEqual(len(d['items']),5)
        self.assertTrue(all(x['model']=='260G' and x['status']=='rrp_difference' for x in d['items']))
        self.assertEqual(len(R.search(self.rows,limit=100000)['items']),100)
        with self.assertRaises(ValueError):R.search(self.rows,status='approved')

    def test_csv_injection_protected_and_review_export_never_approves(self):
        csvtext=R.export_csv([{
            'sku':'=1+1','model':'260G','name':'@IMPORT','console':'-UNCONFIRMED',
            'source_rrp':12.5,'live_rrp':12,'difference_gbp':.5,'status':'rrp_difference',
            'sources':[{'sheet':'=evil','row':'7'}]
        }])
        values=list(csv.reader(io.StringIO(csvtext.lstrip('\ufeff'))))[1]
        self.assertEqual(values[0],"'=1+1")
        self.assertEqual(values[2],"'@IMPORT")
        self.assertEqual(values[3],"'-UNCONFIRMED")
        self.assertTrue(values[8].startswith("'=evil"))
        self.assertEqual(values[-1],'NO')

    def test_manager_api_and_staff_read_only_source_reference(self):
        r=self.client.get('/api/catalog/admin/rrp-2026/summary')
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['distinct_source_skus'],4632)
        r=self.client.get('/api/catalog/admin/rrp-2026/search',params={'q':'280G-ABS'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['items'][0]['status'],'source_price_conflict')
        self.assertEqual(len(r.json()['items'][0]['sources']),2)
        r=self.client.get('/api/catalog/admin/rrp-2026/family/260G')
        self.assertEqual(r.status_code,200)
        self.assertTrue(r.json()['must_confirm_exact_variant'])
        r=self.client.get('/api/catalog/rrp-evidence',params={'q':'260G-AAS'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['items'][0]['source_rrp'],9548.30)
        self.assertEqual(self.client.get('/api/catalog/admin/rrp-2026/search',params={'status':'approved'}).status_code,400)
        r=self.client.get('/api/catalog/admin/rrp-2026/reconciliation.csv')
        self.assertEqual(r.status_code,200)
        self.assertIn('rrp_difference',r.text)
        self.assertIn('Source has commercial approval',r.text)

    def test_hybrid_pricing_control_has_no_duplicate_api_endpoints(self):
        paths=[(route.path,tuple(sorted(getattr(route,'methods',())))) for route in main.app.routes]
        for path in ('/api/catalog/admin/hybrid-rrp','/api/catalog/admin/hybrid-rrp/propose'):
            self.assertEqual(sum(x[0]==path for x in paths),1)

    def test_manager_api_is_not_open_to_coordinators(self):
        with patch.object(main.security,'enabled',return_value=True),patch.object(main.security,'identify',return_value={'role':'coordinator','username':'test'}):
            r=self.client.get('/api/catalog/admin/rrp-2026/summary',headers={'Authorization':'Bearer test'})
            self.assertEqual(r.status_code,403)
            r=self.client.get('/api/catalog/rrp-evidence',params={'q':'260G'},headers={'Authorization':'Bearer test'})
            self.assertEqual(r.status_code,200)

if __name__=='__main__':unittest.main()
