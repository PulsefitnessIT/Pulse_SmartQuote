"""V10 integration checks independent of unreleased historical bulk data."""
import unittest
from unittest.mock import patch
import engine

class HistoricalEvidenceTests(unittest.TestCase):
    def test_identity_lookup_falls_back_safely_without_archive(self):
        self.assertIsNone(engine.historical_identity('MADEUP-UNKNOWN-99'))

    def test_exact_and_old_alias_never_return_rrp(self):
        original={'260G-AAS':{'sku':'260G-AAS','name':'Treadmill',
                    'model':'260G','console':'Cirrus V4','status':'Active',
                    'year':2026,'first_seen':2020,'source':'2026 master'}}
        models={'260G':['260G-AAS']}
        aliases={'OLD-260G':['260G-AAS']}
        with patch.object(engine,'HISTORIC_V10_RECORDS',original), \
             patch.object(engine,'HISTORIC_V10_MODELS',models), \
             patch.object(engine,'HISTORIC_V10_ALIASES',aliases):
            exact=engine.historical_identity('260G-AAS')
            self.assertEqual(exact['basis'],'Exact historical SKU')
            self.assertTrue(exact['evidence_only'])
            self.assertNotIn('rrp',exact['variants'][0])
            old=engine.historical_identity('OLD-260G')
            self.assertIn('NOT an approved replacement',old['basis'])
            self.assertNotIn('rrp',old['variants'][0])
            family=engine.historical_identity('260G')
            self.assertIn('Model family',family['basis'])

    def test_v9_price_is_unchanged(self):
        asset=engine.match_asset({'id':'s1','code':'260G-AAS','qty':3,'source_row':1})
        self.assertEqual(asset['selected']['rrp'],9373.16)
        self.assertEqual(engine.price_line(asset,'Standard','Gold',0)['annual'],1054.47)

if __name__=='__main__':
    unittest.main()
