"""Tests for offline Windows portable launcher; safe to run on Linux CI."""
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import windows_portable

class PortableLaunchTests(unittest.TestCase):
    def test_requires_complete_catalogue_and_ui(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with self.assertRaisesRegex(RuntimeError, 'Missing:'):
                windows_portable.validate_portable_directory(p)
            for file in ('data/catalog.json', 'data/pricing.json', 'static/index.html'):
                target=p/file;target.parent.mkdir(parents=True, exist_ok=True);target.write_text('{}')
            self.assertEqual(windows_portable.validate_portable_directory(p),p)

    def test_frozen_uses_executable_dir_not_temp(self):
        with patch.object(windows_portable.sys,'frozen',True,create=True), patch.object(windows_portable.sys,'executable',r'C:\Pulse\SmartQuote\Pulse_SmartQuote_V10.exe'):
            self.assertEqual(windows_portable.installation_directory(),Path(r'C:\Pulse\SmartQuote\Pulse_SmartQuote_V10.exe').resolve().parent)

    def test_cli_error_is_actionable(self):
        with patch.object(windows_portable,'serve',side_effect=RuntimeError('Incomplete Windows download')):
            self.assertEqual(windows_portable.main_cli(['--check']),1)

    def test_quiet_check_does_not_request_administrator_login(self):
        with patch.object(windows_portable,'validate_portable_directory',return_value=Path(__file__).resolve().parents[1]),patch.object(windows_portable,'initialise_admin') as prompt:
            # Fake out database-writing app module imports to keep tests isolated.
            import types
            root=Path(__file__).resolve().parents[1]
            with patch.dict(sys.modules,{'main':types.SimpleNamespace(ROOT=root),'startup_manager':types.SimpleNamespace()}):
                self.assertEqual(windows_portable.serve(check=True),0)
            prompt.assert_not_called()

if __name__=='__main__':unittest.main()
