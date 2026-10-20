"""Prevents reintroducing a missing requirements.txt into Windows downloads."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile

import build_v10_pilot
import startup_manager

ROOT = Path(__file__).resolve().parents[1]


class WindowsStartupTests(unittest.TestCase):
    def test_github_pilot_contains_installer_and_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'download.zip'
            report = build_v10_pilot.build(output)
            for required in ('start_windows.bat', 'startup_manager.py',
                             'requirements.txt', 'requirements-test.txt',
                             'GET_STARTED_WINDOWS.txt', 'main.py'):
                self.assertIn(required, report['sha256'])
                with ZipFile(output) as archive:
                    self.assertEqual(archive.read('SmartQuote_V10/' + required),
                                     (ROOT / required).read_bytes())

    def test_do_not_bundle_customer_data_or_private_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'download.zip'
            build_v10_pilot.build(archive)
            with ZipFile(archive) as z:
                self.assertFalse(any('.venv/' in n for n in z.namelist()))
                self.assertFalse(any('smartquote_local.db' in n for n in z.namelist()))

    def test_missing_requirements_has_clear_instruction_before_pip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(startup_manager.SetupError) as cm:
                startup_manager.validate_source(root)
            self.assertIn('requirements.txt', str(cm.exception))
            self.assertIn('Extract All', str(cm.exception))

    def test_fingerprint_changes_when_requirements_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'requirements.txt'
            path.write_text('fastapi>=0.1\n', encoding='utf-8')
            first = startup_manager.requirements_fingerprint(tmp)
            path.write_text('fastapi>=0.2\n', encoding='utf-8')
            self.assertNotEqual(first, startup_manager.requirements_fingerprint(tmp))

    def test_healthy_server_check_does_not_trust_unrelated_port(self):
        with mock.patch.object(startup_manager.urllib.request, 'urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(
                json.dumps({'ok': True, 'name': 'Not SmartQuote'}).encode())
            self.assertFalse(startup_manager.smartquote_running())


if __name__ == '__main__':
    unittest.main()
