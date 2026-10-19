"""Non-destructive preflight tests with small synthetic identity-only fixtures."""
import json
import tempfile
import unittest
from pathlib import Path
from catalogue_readiness import evaluate


class CatalogueReadinessTests(unittest.TestCase):
    def test_empty_checkout_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            result = evaluate(temp)
            self.assertFalse(result["automated_preflight_passes"])
            self.assertFalse(result["historical"]["index_loaded"])
            self.assertFalse(result["commercial"]["approved"])

    def test_consistent_full_coverage_needs_explicit_price_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            data.mkdir()
            (data / "historical_catalogue_index.json").write_text(json.dumps({
                "records": {"260G-AAA": {"sku": "260G-AAA", "evidence_only": True}},
                "aliases": {"R260G": ["260G-AAA"]}
            }), encoding="utf-8")
            (data / "historical_catalogue_manifest.json").write_text(json.dumps({
                "unique_skus": 1, "alias_codes": 1,
                "worksheets": [{"year": y, "status": "read"} for y in range(2020, 2027)]
            }), encoding="utf-8")
            provisional = evaluate(temp, {"pricing_status": "Provisional; not approved"})
            self.assertTrue(provisional["historical"]["archive_ready"])
            self.assertFalse(provisional["commercial"]["approved"])
            self.assertFalse(provisional["automated_preflight_passes"])
            approved = evaluate(temp, {"pricing_status": "Approved"})
            self.assertTrue(approved["automated_preflight_passes"])

    def test_missing_year_mismatched_manifest_and_ambiguous_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            data.mkdir()
            (data / "historical_catalogue_index.json").write_text(json.dumps({
                "records": {"A-01": {}, "B-02": {}},
                "aliases": {"OLD-ONE": ["A-01", "B-02"]}
            }), encoding="utf-8")
            (data / "historical_catalogue_manifest.json").write_text(json.dumps({
                "unique_skus": 7, "alias_codes": 1,
                "worksheets": [{"year": 2026, "status": "read"}, {"year": 2020, "status": "failed"}]
            }), encoding="utf-8")
            report = evaluate(temp, {"pricing_status": "Approved"})
            self.assertEqual(report["historical"]["ambiguous_alias_codes"], 1)
            self.assertEqual(report["historical"]["failed_worksheets"], 1)
            self.assertFalse(report["historical"]["manifest_consistent"])
            self.assertFalse(report["automated_preflight_passes"])

    def test_malformed_index_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            data.mkdir()
            (data / "historical_catalogue_index.json").write_text("{bad", encoding="utf-8")
            self.assertFalse(evaluate(temp, {"pricing_status": "Approved"})["historical"]["index_loaded"])


if __name__ == "__main__":
    unittest.main()
