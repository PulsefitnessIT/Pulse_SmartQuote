"""Staff-oriented import preflight: no side effects and no duplicate equipment."""
import base64
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('SMARTQUOTE_AUTH', 'off')
from fastapi.testclient import TestClient
import main
import matching_memory


class StaffWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path=Path(temp.name)/'app.sqlite'
        a=patch.object(main,'DB',path)
        b=patch.object(matching_memory,'DB',path)
        a.start();b.start()
        self.addCleanup(a.stop);self.addCleanup(b.stop)
        self.client=TestClient(main.app)
        response=self.client.post('/api/quotes')
        self.assertEqual(response.status_code,200,response.text)
        self.quote=response.json()['quote']
        self.root='/api/quotes/'+self.quote['id']

    @staticmethod
    def file(content, name='complex.csv'):
        return {'filename':name, 'content_base64':base64.b64encode(content).decode()}

    def test_preview_does_not_change_quote_and_reuses_real_parser(self):
        content=('Name,Make,Model,Description,Serial Number,Remark\n'
                 'Facility,224B-AAB,Group Cycle,Group Cycle,SER1,Inspect\n'
                 'Facility,224B-AAB,Group Cycle,Group Cycle,SER2,Inspect\n'
                 'Facility,0,260G-0,Low Impact Elevation Treadmill,SER3,Other\n').encode()
        result=self.client.post(self.root+'/import-preview',json=self.file(content))
        self.assertEqual(result.status_code,200,result.text)
        pre=result.json()
        self.assertEqual(pre['source_rows'],3)
        self.assertEqual(pre['physical_units'],3)
        self.assertEqual(pre['equipment_groups'],2)
        self.assertEqual(pre['content_sha256'],hashlib.sha256(content).hexdigest())
        self.assertFalse(pre['already_imported'])
        self.assertEqual(pre['quantity_checks'],0)
        self.assertEqual(pre['existing_quote_rows'],0)
        self.assertEqual(len(self.client.get(self.root).json()['quote']['assets']),0)
        self.assertEqual(self.client.get(self.root).json()['quote']['files'],[])
        self.assertEqual(pre['sample_groups'][0]['source_rows'],2)

    def test_immutable_preview_then_import_then_duplicate_rejected_even_with_new_name(self):
        content=('Equipment,Model,SKU,Serial Number\n'
                 'Pulse treadmill,260G,260G-AAS,A001\n'
                 'Pulse treadmill,260G,260G-AAS,A002\n').encode()
        request=self.file(content)
        preview=self.client.post(self.root+'/import-preview',json=request).json()
        stored={**request,'content_sha256':preview['content_sha256']}
        created=self.client.post(self.root+'/import',json=stored)
        self.assertEqual(created.status_code,200,created.text)
        self.assertEqual(len(created.json()['quote']['assets']),2)
        self.assertEqual(len(created.json()['display_groups']),1)
        self.assertEqual(created.json()['quote']['files'][0]['content_sha256'],preview['content_sha256'])
        repeated=self.client.post(self.root+'/import-preview',json=self.file(content,'same_data_renamed.csv'))
        self.assertTrue(repeated.json()['already_imported'])
        rejected=self.client.post(self.root+'/import',json=self.file(content,'same_data_renamed.csv'))
        self.assertEqual(rejected.status_code,409,rejected.text)
        self.assertEqual(len(self.client.get(self.root).json()['quote']['assets']),2)
        self.assertEqual(len(self.client.get(self.root).json()['quote']['files']),1)
        self.assertEqual(len(self.client.get(self.root+'/asset-register.csv').text.splitlines()),3)

    def test_modified_file_requires_second_preview(self):
        base=b'Equipment,Model,Serial\nTreadmill,260G,A100\n'
        extra=b'Equipment,Model,Serial\nTreadmill,260G,A100\nTreadmill,260G,A101\n'
        old=self.client.post(self.root+'/import-preview',json=self.file(base)).json()['content_sha256']
        mismatch=self.client.post(self.root+'/import',json={**self.file(extra),'content_sha256':old})
        self.assertEqual(mismatch.status_code,409)
        self.assertEqual(len(self.client.get(self.root).json()['quote']['assets']),0)

    def test_invalid_file_does_not_mutate_quote(self):
        invalid=self.client.post(self.root+'/import-preview',json={'filename':'bad.csv','content_base64':'***'})
        self.assertEqual(invalid.status_code,400)
        self.assertEqual(self.client.get(self.root).json()['quote']['files'],[])
        self.assertEqual(self.client.get(self.root).json()['quote']['assets'],[])

    def test_quantity_issue_flagged_before_import(self):
        content=b'Name,Model,Description\nFacility,224B,Group Cycle\n'
        response=self.client.post(self.root+'/import-preview',json=self.file(content))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['quantity_checks'],1)
        self.assertEqual(self.client.get(self.root).json()['quote']['assets'],[])

    def test_register_searches_customer_site_and_contract_reference(self):
        info={'customer':'Hartley Leisure Trust','site':'Swimming Centre North',
              'contract_ref':'HLT-123456'}
        self.assertEqual(self.client.put(self.root,json=info).status_code,200)
        hits=self.client.get('/api/quotes?q=hlt-123456').json()['quotes']
        self.assertTrue(any(x['id']==self.quote['id'] for x in hits))
        by_customer=self.client.get('/api/quotes?q=hartley').json()['quotes']
        self.assertTrue(any(x['id']==self.quote['id'] for x in by_customer))
        by_site=self.client.get('/api/quotes?q=SWIMMING CENTRE').json()['quotes']
        self.assertTrue(any(x['id']==self.quote['id'] for x in by_site))
        no_match=self.client.get('/api/quotes?q=NOMATCHZZ999').json()['quotes']
        self.assertFalse(no_match)
        self.assertEqual(self.client.get('/api/quotes?pipeline_status=Accepted').json()['quotes'],[])

    def test_undo_last_untouched_batch_is_lossless_and_allows_reimport(self):
        content=('Name,Make,Model,Description,Serial Number\n'
                 'Club,224B-AAB,Group Cycle,Group Cycle,SER-01\n'
                 'Club,224B-AAB,Group Cycle,Group Cycle,SER-02\n').encode()
        body=self.file(content)
        uploaded=self.client.post(self.root+'/import',json=body)
        self.assertEqual(uploaded.status_code,200,uploaded.text)
        self.assertEqual(len(uploaded.json()['quote']['assets']),2)
        undo=self.client.post(self.root+'/imports/undo-last')
        self.assertEqual(undo.status_code,200,undo.text)
        self.assertEqual(undo.json()['undone_rows'],2)
        self.assertEqual(undo.json()['quote']['assets'],[])
        self.assertEqual(undo.json()['quote']['files'],[])
        self.assertEqual(len(self.client.get(self.root+'/asset-register.csv').text.splitlines()),1)
        again=self.client.post(self.root+'/import',json=body)
        self.assertEqual(again.status_code,200,again.text)

    def test_undo_rejects_reviewed_or_partially_deleted_batch(self):
        body=self.file(b'Name,Make,Model,Description,Serial Number\nClub,224B-AAB,Group Cycle,Group Cycle,S01\n')
        up=self.client.post(self.root+'/import',json=body).json()
        asset=up['quote']['assets'][0]
        edit=self.client.put(self.root+'/assets/'+asset['id'],json={'display_name':'Staff corrected description'})
        self.assertEqual(edit.status_code,200,edit.text)
        refused=self.client.post(self.root+'/imports/undo-last')
        self.assertEqual(refused.status_code,409,refused.text)
        self.assertEqual(len(self.client.get(self.root).json()['quote']['assets']),1)
        self.assertEqual(self.client.get(self.root).json()['quote']['assets'][0]['display_name'],
                         'Staff corrected description')

    def test_undo_only_removes_most_recent_batch(self):
        first=self.file(b'Name,Make,Model,Description,Serial Number\nClub,224B-AAB,Group Cycle,Group Cycle,S01\n')
        second=self.file(b'Name,Make,Model,Description,Serial Number\nClub,224B-AAB,Group Cycle,Group Cycle,S02\n','second.csv')
        self.assertEqual(self.client.post(self.root+'/import',json=first).status_code,200)
        self.assertEqual(self.client.post(self.root+'/import',json=second).status_code,200)
        undo=self.client.post(self.root+'/imports/undo-last')
        self.assertEqual(undo.status_code,200,undo.text)
        self.assertEqual(len(undo.json()['quote']['assets']),1)
        self.assertEqual(undo.json()['quote']['assets'][0]['serial'],'S01')
        self.assertEqual(len(undo.json()['quote']['files']),1)

    def test_large_anonymised_asset_list_stays_grouped(self):
        header='Name,Make,Model,Description,Serial Number\n'
        data=header+''.join(f'Demo Club,224B-AAB,Group Cycle,Group Cycle,SN{i:03d}\n' for i in range(165))
        r=self.client.post(self.root+'/import-preview',json=self.file(data.encode()))
        self.assertEqual(r.status_code,200,r.text)
        info=r.json()
        self.assertEqual((info['source_rows'],info['physical_units'],info['equipment_groups']),(165,165,1))
        self.assertEqual(info['sample_groups'][0]['source_rows'],165)
        self.assertEqual(len(self.client.get(self.root).json()['quote']['assets']),0)


if __name__=='__main__':unittest.main()
