"""Policy approved by user; no autonomous price/configuration approval."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('SMARTQUOTE_AUTH','off')
from fastapi.testclient import TestClient
import hybrid_rrp as H
import main
import engine


class HybridPolicyTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.addCleanup(self.dir.cleanup)
        db=Path(self.dir.name)/'pilot.sqlite'
        for module in (main,H):
            p=patch.object(module,'DB',db);p.start();self.addCleanup(p.stop)
        self.client=TestClient(main.app)
        self.first={'username':'pricing.manager','role':'manager'}
        self.second={'username':'commercial.director','role':'admin'}

    def proposal(self,**updates):
        record={'legacy_code':'260G-0','basis':'current_equivalent',
                'current_sku':'260G-AAS','console':'Console 5 (Series 2)',
                'evidence':'Checked 2026 master item code and photograph of actual installed console.',
                'reason':'Verified model and console against original factory specification sheet.'}
        record.update(updates)
        return record

    def test_policy_is_approved_but_individual_rrps_and_quotes_are_not(self):
        self.assertEqual(H.POLICY['default_basis'],'current_equivalent')
        self.assertFalse(H.POLICY['automatic_price_application'])
        self.assertTrue(H.POLICY['approved_policy'])
        result=self.client.get('/api/catalog/admin/hybrid-rrp')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['rules'],[])
        self.assertIn('no SKU',result.json()['policy']['authorisation_scope'])

    def test_two_people_must_sign_and_registered_rule_never_mutates_quote(self):
        q=self.client.post('/api/quotes').json()['quote']
        raw={'id':'aa','name':'Run Treadmill','model':'260G-0','code':'260G-0','qty':1,'source_row':1}
        before=engine.match_asset(raw)
        self.assertIsNone(before['selected'])
        with patch.object(main,'actor',lambda _:self.first):
            r=self.client.post('/api/catalog/admin/hybrid-rrp/propose',json=self.proposal())
            self.assertEqual(r.status_code,200,r.text)
            rule=r.json()['id']
            self.assertEqual(self.client.post('/api/catalog/admin/hybrid-rrp/'+rule+'/approve',
                  json={'note':'Checked against current product and physical console.', 'acknowledge':True}).status_code,409)
        self.assertEqual(H.suggest(before,0)['status'],'unmapped')
        with patch.object(main,'actor',lambda _:self.second):
            approved=self.client.post('/api/catalog/admin/hybrid-rrp/'+rule+'/approve',
                         json={'note':'Verified against master RRP and installed physical console.', 'acknowledge':True})
            self.assertEqual(approved.status_code,200,approved.text)
        suggestion=H.suggest(before,main.admin.revision())
        self.assertEqual(suggestion['current_equivalent']['sku'],'260G-AAS')
        self.assertTrue(suggestion['requires_operator_confirmation'])
        self.assertFalse(suggestion['automatic_price_application'])
        self.assertIsNone(before['selected'])
        self.assertEqual(self.client.get('/api/quotes/'+q['id']).json()['summary']['annual'],0)
        self.assertEqual(H.suggest(before,main.admin.revision()+1)['status'],'stale')
        duplicate=self.client.post('/api/catalog/admin/hybrid-rrp/propose',json=self.proposal())
        self.assertEqual(duplicate.status_code,400)

    def test_bad_equivalences_and_unverified_console_are_rejected(self):
        for update in ({'current_sku':'DOES-NOT-EXIST'},
                       {'current_sku':'260G-AAS','console':'No Console / N/A'},
                       {'current_sku':'260G-0'},
                       {'exception_rrp':500},
                       {'evidence':'No proof'}):
            r=self.client.post('/api/catalog/admin/hybrid-rrp/propose',json=self.proposal(**update))
            self.assertEqual(r.status_code,400,(update,r.text))
        self.assertFalse(H.rules())

    def test_legacy_exception_expiry_double_review_and_revocation(self):
        payload=self.proposal(basis='legacy_exception',current_sku='',console='Unconfirmed',
                   exception_rrp=4850,expires_on='2027-01-31')
        with patch.object(main,'actor',lambda _:self.first):
            r=self.client.post('/api/catalog/admin/hybrid-rrp/propose',json=payload)
            self.assertEqual(r.status_code,200,r.text)
            rule=r.json()['id']
            self.assertEqual(self.client.post('/api/catalog/admin/hybrid-rrp/'+rule+'/approve',
              json={'acknowledge':False,'note':'Valid approval note longer than twenty characters.'}).status_code,400)
        with patch.object(main,'actor',lambda _:self.second):
            ok=self.client.post('/api/catalog/admin/hybrid-rrp/'+rule+'/approve',
              json={'acknowledge':True,'note':'Physically and commercially verified exception source document.'})
            self.assertEqual(ok.status_code,200,ok.text)
        evidence=H.suggest({'code':'260G-0'},main.admin.revision())
        self.assertEqual(evidence['basis'],'legacy_exception')
        self.assertEqual(evidence['exception_rrp_evidence_only'],4850)
        self.assertFalse(evidence['automatic_price_application'])
        with patch.object(main,'actor',lambda _:self.first):
            removed=self.client.post('/api/catalog/admin/hybrid-rrp/'+rule+'/revoke',
              json={'reason':'Machine specification changed after physical site verification.'})
            self.assertEqual(removed.status_code,200,removed.text)
        self.assertEqual(H.suggest({'code':'260G-0'},0)['status'],'unmapped')
        self.assertEqual(H.rules()[0]['status'],'revoked')
        with H._db() as c:
            events=[row[0] for row in c.execute('SELECT action FROM legacy_rrp_policy_audit ORDER BY at')]
        self.assertEqual(set(events),{'PROPOSED','APPROVED','REVOKED'})

    def test_role_blocking_coordinator_and_source_identity_before_selected_code(self):
        with patch.object(main,'actor',lambda _: {'username':'contracts.coord','role':'coordinator'}):
            self.assertEqual(self.client.post('/api/catalog/admin/hybrid-rrp/propose',json=self.proposal()).status_code,403)
        first=H.propose(self.proposal(),self.first['username'],0)
        H.approve(first['id'],self.second['username'],0,'Independently verified console and RRP from source master.')
        guessed={'source_cells':{'code':'260G-0','model':'260G-0'},'code':'260G-AAS','model':'260G'}
        self.assertEqual(H.suggest(guessed,0)['current_equivalent']['sku'],'260G-AAS')
        self.assertEqual(H.suggest({'code':'260G'},0)['status'],'unmapped')

if __name__=='__main__':unittest.main()
