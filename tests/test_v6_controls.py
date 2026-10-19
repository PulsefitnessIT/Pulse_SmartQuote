"""V6 regression and release-control tests."""
import os,io,csv,secrets,hashlib,unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import engine,catalogue_admin,security
from main import app

class V6ControlsTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)
        self.old=os.environ.get('SMARTQUOTE_AUTH')
        os.environ['SMARTQUOTE_AUTH']='off'
        self.base='/api/quotes/'+self.client.post('/api/quotes').json()['quote']['id']
    def tearDown(self):
        if self.old is None:os.environ.pop('SMARTQUOTE_AUTH',None)
        else:os.environ['SMARTQUOTE_AUTH']=self.old

    def test_manual_base_rate_receives_quotation_discount(self):
        row=self.client.post(self.base+'/manual',json={'name':'Special cycle','sku':'SPECIAL-123','model':'ABC','qty':2}).json()['quote']['assets'][0]
        updated=self.client.put(self.base+'/assets/'+row['id'],json={'manual_annual_unit':100,'manual_price_source':'Written email dated 16 October 2026'})
        self.assertEqual(updated.status_code,200,updated.text)
        summary=self.client.put(self.base,json={'discount':10,'customer':'Test centre','site':'North site'}).json()['summary']
        self.assertEqual(summary['annual'],180)
        self.assertEqual(summary['lines'][0]['price']['unit'],90)
        self.assertTrue(summary['ready'],summary['issues'])

    def test_invalid_imported_quantity_is_visible_and_blocks_issue(self):
        text='Item Code,Description,Quantity\n260G-AAS,Club Line Treadmill,INVALID\n'
        import base64
        data=self.client.post(self.base+'/import',json={'filename':'wrong_qty.csv','content_base64':base64.b64encode(text.encode()).decode()})
        self.assertEqual(data.status_code,200,data.text)
        d=data.json();self.assertEqual(d['quote']['assets'][0]['qty'],1)
        self.assertIn('invalid',d['quote']['assets'][0]['qty_issue'])
        aid=d['quote']['assets'][0]['id']
        d=self.client.put(self.base,json={'customer':'A Leisure','site':'A Site'}).json()
        self.assertFalse(d['summary']['ready']);self.assertTrue(any('quantity' in x.lower() for x in d['summary']['issues']))
        no=self.client.post(self.base+'/issue');self.assertEqual(no.status_code,422)
        fixed=self.client.put(self.base+'/assets/'+aid,json={'qty':2})
        self.assertEqual(fixed.status_code,200,fixed.text)
        self.assertFalse(fixed.json()['quote']['assets'][0]['qty_issue'])
        self.assertTrue(fixed.json()['summary']['ready'])

    def test_master_import_detects_console_only_changes(self):
        original=engine.BY_SKU['260G-AAS']
        text=f'Product Code,Description,Current RRP,Console Type\n260G-AAS,"{original["name"]}",{original["rrp"]},New V6 Console\n'
        changes,_=catalogue_admin.parse_master('new_master.csv',text.encode())
        self.assertEqual(changes[0]['action'],'Changed')
        self.assertEqual(changes[0]['item']['console'],'New V6 Console')

    def test_pdf_versions_are_immutable_even_after_quote_edits(self):
        self.client.post(self.base+'/manual',json={'sku':'260G-AAS','qty':1})
        self.client.put(self.base,json={'customer':'Riverside Leisure','site':'Riverside One'})
        r=self.client.post(self.base+'/issue');self.assertEqual(r.status_code,200,r.text[:100] if r.status_code!=200 else '')
        original=r.content;v=int(r.headers['x-quote-version']);digest=hashlib.sha256(original).hexdigest()
        again=self.client.post(self.base+'/issue')
        self.assertEqual(int(again.headers['x-quote-version']),v)
        self.assertEqual(again.content,original)
        self.assertEqual(digest,r.headers['x-pdf-sha256'])
        self.client.put(self.base,json={'customer':'Riverside Leisure Ltd','site':'New gym'})
        recent=self.client.post(self.base+'/issue');self.assertEqual(recent.status_code,200)
        self.assertEqual(int(recent.headers['x-quote-version']),v+1)
        old=self.client.get(self.base+f'/versions/{v}/pdf')
        self.assertEqual(old.status_code,200)
        self.assertEqual(old.content,original)
        self.assertNotEqual(recent.content,original)
        self.assertIn('Pilot snapshot',str(self.client.get(self.base+'/versions').json()))

    def test_password_accounts_and_roles_protect_master(self):
        tag=secrets.token_hex(4)
        security.add_user('coord_'+tag,'Strong testing password 2026','coordinator')
        security.add_user('manager_'+tag,'Strong testing password 2026','manager')
        with patch.dict(os.environ,{'SMARTQUOTE_AUTH':'on'}):
            no=self.client.get('/api/catalog/admin/info');self.assertEqual(no.status_code,401)
            auth=self.client.post('/api/auth/login',json={'username':'coord_'+tag,'password':'Strong testing password 2026'})
            self.assertEqual(auth.status_code,200)
            headers={'Authorization':'Bearer '+auth.json()['token']}
            self.assertEqual(self.client.get('/api/quotes',headers=headers).status_code,200)
            self.assertEqual(self.client.get('/api/catalog/admin/info',headers=headers).status_code,403)
            manager=self.client.post('/api/auth/login',json={'username':'manager_'+tag,'password':'Strong testing password 2026'})
            mh={'Authorization':'Bearer '+manager.json()['token']}
            self.assertEqual(self.client.get('/api/catalog/admin/info',headers=mh).status_code,200)
            self.assertEqual(self.client.get('/api/auth/me',headers=mh).json()['user']['role'],'manager')
            self.client.post('/api/auth/logout',headers=mh)
            self.assertEqual(self.client.get('/api/catalog/admin/info',headers=mh).status_code,401)

if __name__=='__main__':unittest.main()

class V6ReportingTests(unittest.TestCase):
    def setUp(self):
        os.environ['SMARTQUOTE_AUTH']='off'
        self.c=TestClient(app)
        self.base='/api/quotes/'+self.c.post('/api/quotes').json()['quote']['id']
    def test_report_export_and_customer_lookup(self):
        self.c.put(self.base,json={'customer':'ABC Test Leisure','site':'West Bank Leisure'})
        suggestion=self.c.get('/api/customers/suggest?q=ABC Test').json()['customers']
        self.assertTrue(any(x['customer']=='ABC Test Leisure' for x in suggestion))
        missing=self.c.post(self.base+'/pipeline',json={'pipeline_status':'Accepted','note':''})
        self.assertEqual(missing.status_code,400)
        updated=self.c.post(self.base+'/pipeline',json={'pipeline_status':'Sent externally','note':'Sent by recorded email on 16 October 2026'})
        self.assertEqual(updated.status_code,200)
        summary=self.c.get('/api/reporting/summary')
        self.assertEqual(summary.status_code,200)
        export=self.c.get('/api/reporting/quotes.csv')
        self.assertEqual(export.status_code,200)
        self.assertIn(b'Sent externally',export.content)
