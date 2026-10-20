"""Tests for identity-only V10 historical master importer."""
import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from historical_master import (
    build_master, field_indexes, prepare_record, source_info, valid_alias,
    xlsx_sheets,
)


class HistoricalMasterTests(unittest.TestCase):
    def test_version_and_year(self):
        year, revision = source_info(Path("2022 - Master Input - Transition_Iss.r.csv"))
        self.assertEqual((year, revision), (2022, "r"))
        self.assertEqual(source_info(Path("2024 - Master.csv")), (2024, ""))

    def test_header_layout_variants(self):
        layouts = [
            ["SKU Code", "Product Name (Short Description)", "Model No.\nPart Code", "Console\nAnalysis Code 6"],
            ["Code", "Old SKU", "Model No.", "Stock Item Name", "Console", "Status:\nActive/Inactive"],
            ["Stock Item Code\nSKU Code", "Stock Item Name\nProduct Name (Short Description)"],
        ]
        for headers in layouts:
            result = field_indexes(headers)
            self.assertIn("sku", result)
            self.assertIn("name", result)
        self.assertEqual(field_indexes(layouts[1])["old_sku"], 1)
        self.assertEqual(field_indexes(layouts[1])["console"], 4)

    def test_invalid_numeric_alias(self):
        self.assertFalse(valid_alias("0"))
        self.assertFalse(valid_alias("25"))
        self.assertTrue(valid_alias("R260G-5.00DRPW"))

    def test_source_preserves_identity_not_rrp(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            a = folder / "2023 - Master Input - Transition_Iss.a.csv"
            b = folder / "2024 - Master Input - Transition_Iss.csv"
            headers = ["Code", "Old SKU", "Model No.", "Stock Item Name", "Console", "Status: Active/Inactive"]
            for file, rows in (
                (a, [["260G-AAA", "0", "260G", "Treadmill", "Console 6", "Active"],
                     ["270G-AAA", "R270G-V3", "270G", "Lateral Trainer", "Console 6", "Inactive"]]),
                (b, [["260G-AAA", "0", "260G", "Treadmill", "Cirrus V4", "Active"],
                     ["270G-AAA", "R270G-V3", "270G", "Lateral Trainer", "Console 6", "Inactive"]]),
            ):
                with file.open("w", encoding="utf-8", newline="") as out:
                    writer = csv.writer(out)
                    writer.writerow(["Assembled Database"])
                    writer.writerow(headers)
                    writer.writerows(rows)
            report = build_master([b, a], folder / "out")
            self.assertEqual(report["unique_skus"], 2)
            self.assertEqual(report["snapshots"], 4)
            record = json.loads((folder / "out/historical_equipment_master.json").read_text())
            self.assertEqual(record["260G-AAA"]["console"], "Cirrus V4")
            self.assertEqual(record["260G-AAA"]["pricing_status"], "IDENTITY ONLY - NO APPROVED RRP")
            self.assertEqual(len(record["260G-AAA"]["provenance"]), 2)
            aliases = json.loads((folder / "out/historical_aliases.json").read_text())
            self.assertNotIn("0", aliases)
            self.assertEqual(aliases["R270G-V3"], ["270G-AAA"])
            changes = json.loads((folder / "out/historical_review.json").read_text())
            self.assertTrue(any(x["type"] == "changed_field" and x["field"] == "console" for x in changes))

    def test_suppliers_are_not_equipment_skus(self):
        # Master revision j has a genuine "Suppliers" sheet with 231 supplier
        # account numbers. Matching those as gym assets would be unsafe.
        from unittest.mock import patch
        source = Path('2020 - Master Input - Transition_Iss.j.xlsx')
        sheets = [
            ('Suppliers', iter([['Code','Stock Item Name'],
                                ['00000001','Dummy Supplier Account']])),
            ('Assembled Database',iter([['Code','Stock Item Name'],
                                        ['260G-AAS','Run - Treadmill']]))]
        with tempfile.TemporaryDirectory() as temp, patch('historical_master.read_sheets',return_value=iter(sheets)):
            result=build_master([source],Path(temp)/'archive')
            self.assertEqual(result['unique_skus'],1)
            idx=json.loads((Path(temp)/'archive/historical_catalogue_index.json').read_text())
            self.assertIn('260G-AAS',idx['records'])
            self.assertNotIn('00000001',idx['records'])
            self.assertTrue(any(r.get('reason')=='Non-equipment supplier accounts sheet'
                                for r in result['worksheets']))

    def test_duplicate_conflict_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "2020 - Master.csv"
            source.write_text("SKU Code,Stock Item Name\n230H-AAA,Air Bike\n230H-AAA,Other Bike\n", encoding="utf-8")
            build_master([source], Path(tmp) / "out")
            issues = json.loads((Path(tmp) / "out/historical_review.json").read_text())
            self.assertTrue(any(x["type"] == "conflicting_duplicate_in_source" for x in issues))

    def test_no_unapproved_pricing_field_from_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "2022 - Master.csv"
            source.write_text("Code,Stock Item Name,RRP\n260G-AAS,Treadmill,999999\n", encoding="utf-8")
            build_master([source], Path(tmp) / "out")
            record = json.loads((Path(tmp) / "out/historical_equipment_master.json").read_text())
            self.assertNotIn("rrp", record["260G-AAS"])


if __name__ == "__main__":
    unittest.main()
