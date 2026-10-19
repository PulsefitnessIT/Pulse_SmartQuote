"""A distributed pilot must be self-contained and exclude private local databases."""
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from build_v10_pilot import build, verify, PREFIX


class PilotPackageTests(unittest.TestCase):
    def test_clean_package_and_hash_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "pilot.zip"
            report = build(output)
            self.assertTrue(output.exists())
            self.assertIn("CONTROLLED INTERNAL PILOT", report["release_class"])
            self.assertIn("static/pulse_logo.png", report["sha256"])
            self.assertEqual(verify(output)["sha256"], report["sha256"])
            with ZipFile(output) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), len(set(names)))
                self.assertIn(PREFIX + "READ_THIS_FIRST.txt", names)


if __name__ == "__main__":
    unittest.main()
