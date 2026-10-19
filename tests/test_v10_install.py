"""Installer must reject unsafe archives before touching application data."""
import json
import tempfile
import unittest
from pathlib import Path
from install_historical_catalogue import INDEX, MANIFEST, install, validate


class InstallHistoricalCatalogueTests(unittest.TestCase):
    def fixture(self, source):
        source.mkdir(parents=True, exist_ok=True)
        (source / INDEX).write_text(json.dumps({
            "records": {"260G-AAA": {"sku": "260G-AAA", "name": "Treadmill",
                                     "evidence_only": True}},
            "aliases": {"OLD-260G": ["260G-AAA"]}
        }), encoding="utf-8")
        (source / MANIFEST).write_text(json.dumps({
            "unique_skus": 1, "alias_codes": 1,
            "worksheets": [{"year": y, "status": "read"} for y in range(2020, 2027)]
        }), encoding="utf-8")

    def test_valid_install_preserves_other_application_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, dest = root / "input", root / "appdata"
            self.fixture(source)
            dest.mkdir()
            (dest / "catalog.json").write_text("unchanged")
            (dest / INDEX).write_text("old-version")
            report = install(source, dest)
            self.assertEqual(report["unique_skus"], 1)
            self.assertEqual((dest / "catalog.json").read_text(), "unchanged")
            self.assertTrue(json.loads((dest / INDEX).read_text())["records"])
            self.assertEqual(len(list((dest / "historical_backups").glob("*.bak"))), 1)

    def test_unapproved_rrp_rejected_and_existing_index_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, dest = root / "input", root / "appdata"
            self.fixture(source)
            payload = json.loads((source / INDEX).read_text())
            payload["records"]["260G-AAA"]["rrp"] = 12345
            (source / INDEX).write_text(json.dumps(payload))
            dest.mkdir()
            (dest / INDEX).write_text("keep-original")
            with self.assertRaisesRegex(ValueError, "Unapproved price"):
                install(source, dest)
            self.assertEqual((dest / INDEX).read_text(), "keep-original")

    def test_alias_target_missing_or_year_incomplete_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "input"
            self.fixture(root)
            data = json.loads((root / INDEX).read_text())
            data["aliases"]["OLD-260G"] = ["UNVERIFIED"]
            (root / INDEX).write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "points to a missing"):
                validate(root)
            self.fixture(root)
            manifest = json.loads((root / MANIFEST).read_text())
            manifest["worksheets"] = [x for x in manifest["worksheets"] if x["year"] != 2021]
            (root / MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "2021"):
                validate(root)


if __name__ == "__main__":
    unittest.main()
