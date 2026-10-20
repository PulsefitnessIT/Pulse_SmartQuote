"""API compatibility and drag/drop import regression, no private customer files."""
import base64
import os
import unittest
from unittest import mock
from fastapi.testclient import TestClient

import main
import startup_manager


class ConnectionAndUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth = mock.patch.dict(os.environ, {'SMARTQUOTE_AUTH':'off'})
        cls.auth.start()
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.auth.stop()

    def test_health_identifies_v10_folder(self):
        response=self.client.get('/api/health')
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['api_contract'],10)
        self.assertEqual(data['instance_id'],startup_manager.instance_id(main.ROOT))
        self.assertIn('V10',data['version'])

    def test_spreadsheet_preview_and_confirm_work_without_browser(self):
        created=self.client.post('/api/quotes')
        self.assertEqual(created.status_code,200)
        quote_id=created.json()['quote']['id']
        content=b'Site,Make,Model,Description,Serial Number,Quantity\nClub, Pulse, 260G-AAS, Treadmill, 1234, 1\n'
        body={'filename':'synthetic_test.csv','content_base64':base64.b64encode(content).decode()}
        preview=self.client.post(f'/api/quotes/{quote_id}/import-preview',json=body)
        self.assertEqual(preview.status_code,200,preview.text[:300])
        self.assertEqual(preview.json()['source_rows'],1)
        body['content_sha256']=preview.json()['content_sha256']
        imported=self.client.post(f'/api/quotes/{quote_id}/import',json=body)
        self.assertEqual(imported.status_code,200,imported.text[:300])
        self.assertEqual(imported.json()['import_report']['added'],1)
        duplicate=self.client.post(f'/api/quotes/{quote_id}/import',json=body)
        self.assertEqual(duplicate.status_code,409)

if __name__=='__main__': unittest.main()
