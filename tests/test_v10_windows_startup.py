"""Prevents reintroducing a missing requirements.txt into Windows downloads."""
import contextlib
import os
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

    def test_old_v9_server_is_not_mistaken_for_v10(self):
        with mock.patch.object(startup_manager.urllib.request, 'urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(
                json.dumps({'ok': True, 'name': 'Pulse Fitness SmartQuote',
                            'version': 'V9 pilot'}).encode())
            self.assertFalse(startup_manager.smartquote_running())

    def test_other_v10_installation_is_not_mistaken_for_this_one(self):
        with mock.patch.object(startup_manager.urllib.request, 'urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(
                json.dumps({'ok': True, 'name': 'Pulse Fitness SmartQuote',
                            'version': 'V10 internal pilot', 'api_contract': 10,
                            'instance_id': 'different-install'}).encode())
            self.assertFalse(startup_manager.smartquote_running())

    def test_healthy_same_installation_is_recognized(self):
        with mock.patch.object(startup_manager.urllib.request, 'urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(
                json.dumps({'ok': True, 'name': 'Pulse Fitness SmartQuote',
                            'version': 'V10 internal pilot', 'api_contract': 10,
                            'instance_id': startup_manager.instance_id()}).encode())
            self.assertTrue(startup_manager.smartquote_running())

    def test_busy_v9_port_moves_v10_to_next_available(self):
        def legacy_or_other(port, root=None):
            return False
        with mock.patch.object(startup_manager, 'smartquote_running', side_effect=legacy_or_other), \
             mock.patch.object(startup_manager, 'port_in_use', side_effect=lambda port: port == 8765):
            self.assertEqual(startup_manager.choose_port(ports=(8765,8766)), (8766,False))

    def test_busy_ports_have_actionable_error(self):
        with mock.patch.object(startup_manager, 'smartquote_running', return_value=False), \
             mock.patch.object(startup_manager, 'port_in_use', return_value=True):
            with self.assertRaises(startup_manager.SetupError) as cm:
                startup_manager.choose_port(ports=(8765,8766))
            self.assertIn('Close older SmartQuote', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
