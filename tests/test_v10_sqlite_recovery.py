"""Recovery bridge must preserve identity evidence without publishing RRPs."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from recover_v10_sqlite import recover


class RecoverSQLiteTests(unittest.TestCase):
    def test_recovery_filters_numeric_aliases_and_retains_lineage(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "equipment.sqlite"
            c = sqlite3.connect(db)
            c.executescript("""
                CREATE TABLE source_files(id INTEGER PRIMARY KEY,year INTEGER,revision TEXT,name TEXT);
                CREATE TABLE observations(sku TEXT,row_number INTEGER,old_sku TEXT,source_id INTEGER);
                CREATE TABLE equipment(sku TEXT PRIMARY KEY,name TEXT,model TEXT,console TEXT,status TEXT,
                    end_of_life TEXT,product_group TEXT,category TEXT,last_observed_year INTEGER,
                    last_source TEXT,pricing_status TEXT);
                CREATE TABLE alias_evidence(alias TEXT,sku TEXT);
            """)
            c.executemany("INSERT INTO source_files VALUES(?,?,?,?)", [
                (1, 2020, "b", "2020 b.csv"), (2, 2021, "n", "2021 n.csv"),
                (3, 2026, "w", "2026 w.xlsx")])
            c.executemany("INSERT INTO observations VALUES(?,?,?,?)", [
                ("260G-AAA", 9, "0", 1), ("260G-AAA", 18, "OLD-260G", 3)])
            c.execute("INSERT INTO equipment VALUES(?,?,?,?,?,?,?,?,?,?,?)", [
                "260G-AAA", "Treadmill", "260G", "Cirrus", "Active", "",
                "CV", "Cardio", 2026, "2026 w.xlsx", "unapproved"])
            c.executemany("INSERT INTO alias_evidence VALUES(?,?)", [
                ("1", "260G-AAA"), ("OLD-260G", "260G-AAA")])
            c.commit()
            c.close()
            manifest = recover(db, Path(folder) / "out")
            self.assertEqual(manifest["unique_skus"], 1)
            self.assertEqual(manifest["alias_codes"], 1)
            self.assertEqual(manifest["skipped_unusable_alias_links"], 1)
            self.assertEqual(manifest["archive_review_status"], "Not approved")
            index = json.loads((Path(folder) / "out" /
                                "historical_catalogue_index.json").read_text())
            sku = index["records"]["260G-AAA"]
            self.assertEqual(sku["first_seen"], 2020)
            self.assertEqual(len(sku["provenance"]), 2)
            self.assertTrue(sku["evidence_only"])
            self.assertNotIn("rrp", sku)
            self.assertNotIn("pricing_status", sku)
            self.assertEqual(index["aliases"]["OLD-260G"], ["260G-AAA"])


if __name__ == "__main__":
    unittest.main()
