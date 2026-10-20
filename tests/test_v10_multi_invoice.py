"""Synthetic invoices only: no customer billing/serial data committed to GitHub."""
import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import fitz
from fastapi.testclient import TestClient
import main
from invoice_import import read_invoice_pdf


def phoenix_like_pdf(invoice_no='0000001001', model='224B-AAB', serials=None,
                     site='Demo Leisure Centre', qty=None, late_serials=False):
    serials=list(serials if serials is not None else ['DEMO001','DEMO002','DEMO003'])
    qty=len(serials) if qty is None else qty
    doc=fitz.open()
    p=doc.new_page(width=595,height=842)
    p.insert_text((46,158),f'Sample Leasing Ltd\n{site}\nDemo Road\nZZ1 2AA',fontsize=7)
    p.insert_text((46,267),f'Invoice\n{invoice_no}\nCustomer Ref: DEMO123\nAccount Ref\nDEMO123',fontsize=7)
    p.insert_text((46,286),'Invoice Date\n25/08/2021\nSales Order Ref\n0000001234',fontsize=7)
    p.insert_text((46,311),'Line Item Code',fontsize=7)
    p.insert_text((43,330),'1',fontsize=7)
    p.insert_text((65,330),model,fontsize=7)
    p.insert_text((168,330),'Group Cycle with console',fontsize=7)
    p.insert_text((343,330),str(qty),fontsize=7)
    p.insert_text((392,330),'950.00',fontsize=7)
    p.insert_text((485,330),str(950*qty)+'.00',fontsize=7)
    for i,s in enumerate([] if late_serials else serials[:2]):
        p.insert_text((43,347+i*13),'Batch/Serial Number :',fontsize=7)
        p.insert_text((168,347+i*13),s,fontsize=7)
    p=doc.new_page(width=595,height=842)
    p.insert_text((46,311),'Line Item Code',fontsize=7)
    for i,s in enumerate(serials if late_serials else serials[2:]):
        p.insert_text((43,330+i*13),'Batch/Serial Number :',fontsize=7)
        p.insert_text((168,330+i*13),s,fontsize=7)
    raw=doc.tobytes();doc.close()
    return raw


def payload(raw,name='Invoice.pdf'):
    return {'filename':name,'content_base64':base64.b64encode(raw).decode()}


class MultiInvoiceTests(unittest.TestCase):
    def test_modern_layout_keeps_exact_sku_cross_page_serials(self):
        r=read_invoice_pdf(phoenix_like_pdf(), 'synthetic.pdf')
        self.assertEqual(r['invoice']['site'],'Demo Leisure Centre')
        self.assertEqual(r['invoice']['billed_to'],'Sample Leasing Ltd')
        self.assertTrue(r['invoice']['customer_needs_confirmation'])
        self.assertEqual(r['report']['equipment_lines'],1)
        self.assertEqual(r['report']['equipment_units'],3)
        self.assertEqual(r['report']['serial_count'],3)
        self.assertEqual(r['assets'][0]['serials'],['DEMO001','DEMO002','DEMO003'])
        self.assertEqual(r['assets'][0]['code'],'224B-AAB')
        self.assertNotIn('rrp',r['assets'][0])

    def test_multi_invoice_import_one_transaction_and_no_duplicate_serials(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'}),mock.patch.object(main,'DB',Path(d)/'local.db'):
            with TestClient(main.app) as client:
                q=client.post('/api/quotes').json()['quote']['id']
                one=payload(phoenix_like_pdf('0000001001',serials=['DEMO001','DEMO002','DEMO003']),'First.pdf')
                two=payload(phoenix_like_pdf('0000001002',serials=['DEMO003','DEMO004']),'Second.pdf')
                files=[one,two]
                pr=client.post(f'/api/quotes/{q}/invoice-batch-preview',json={'files':files})
                self.assertEqual(pr.status_code,200,pr.text[:200])
                self.assertEqual(pr.json()['total_added_lines'],2)
                self.assertEqual(pr.json()['total_added_units'],4)
                self.assertEqual(pr.json()['duplicate_serials_skipped'],1)
                self.assertEqual(client.get(f'/api/quotes/{q}').json()['quote']['assets'],[])
                blocked=client.post(f'/api/quotes/{q}/invoice-batch-import',json={'files':files,'content_sha256':'wrong'})
                self.assertEqual(blocked.status_code,409)
                got=client.post(f'/api/quotes/{q}/invoice-batch-import',json={'files':files,'content_sha256':pr.json()['content_sha256']})
                self.assertEqual(got.status_code,200,got.text[:200])
                quote=got.json()['quote']
                self.assertEqual(len(quote['files']),2)
                self.assertEqual(sum(a['qty'] for a in quote['assets']),4)
                self.assertEqual(len(quote['assets']),2)
                self.assertEqual(quote['assets'][1]['serials'],['DEMO004'])
                self.assertEqual(quote['assets'][1]['original_invoice_qty'],2)
                self.assertFalse(quote['pricing_approved'])
                again=client.post(f'/api/quotes/{q}/invoice-batch-preview',json={'files':files})
                self.assertTrue(all(x['already_imported'] for x in again.json()['invoices']))
                self.assertFalse(again.json()['ready_to_import'])

    def test_different_sites_and_serial_model_conflicts_fail_closed(self):
        with tempfile.TemporaryDirectory() as d,mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'}),mock.patch.object(main,'DB',Path(d)/'local.db'):
            with TestClient(main.app) as client:
                q=client.post('/api/quotes').json()['quote']['id']
                original=payload(phoenix_like_pdf('0000001001',serials=['DEMO001']),'First.pdf')
                other=payload(phoenix_like_pdf('0000001002',site='Other Town Gym',serials=['DEMO002']),'Second.pdf')
                res=client.post(f'/api/quotes/{q}/invoice-batch-preview',json={'files':[original,other]})
                self.assertEqual(res.status_code,409)
                self.assertEqual(client.get(f'/api/quotes/{q}').json()['quote']['assets'],[])
                conflict=payload(phoenix_like_pdf('0000001003',model='240G-AAN',serials=['DEMO001']),'Third.pdf')
                res=client.post(f'/api/quotes/{q}/invoice-batch-preview',json={'files':[original,conflict]})
                self.assertEqual(res.status_code,409)
                self.assertEqual(client.get(f'/api/quotes/{q}').json()['quote']['assets'],[])

    def test_modern_serials_may_start_on_page_two(self):
        r=read_invoice_pdf(phoenix_like_pdf(late_serials=True),'synthetic.pdf')
        self.assertEqual(r['report']['equipment_units'],3)
        self.assertEqual(r['assets'][0]['serials'],['DEMO001','DEMO002','DEMO003'])

    def test_credit_note_rejected(self):
        d=fitz.open(stream=phoenix_like_pdf(),filetype='pdf')
        d[0].insert_text((45,105),'CREDIT NOTE',fontsize=11)
        raw=d.tobytes();d.close()
        with self.assertRaisesRegex(ValueError,'Credit notes'):
            read_invoice_pdf(raw)

    def test_negative_return_line_excluded(self):
        d=fitz.open(stream=phoenix_like_pdf(),filetype='pdf')
        p=d[0]
        for x,value in [(43,'2'),(65,'260G-ABB'),(168,'Returned treadmill'),(343,'1'),
                        (392,'-950.00'),(485,'-950.00')]:
            p.insert_text((x,430),value,fontsize=7)
        raw=d.tobytes();d.close()
        r=read_invoice_pdf(raw)
        self.assertEqual(r['report']['equipment_lines'],1)
        self.assertEqual(r['report']['non_equipment_rows'],1)
        self.assertEqual(r['excluded'][0]['code'],'260G-ABB')
        self.assertFalse(r['report']['invoice_sales_prices_used_as_rrp'])

    def test_corrected_invoice_number_blocks_atomic_batch(self):
        with tempfile.TemporaryDirectory() as d,mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'}),mock.patch.object(main,'DB',Path(d)/'local.db'):
            with TestClient(main.app) as client:
                q=client.post('/api/quotes').json()['quote']['id']
                files=[payload(phoenix_like_pdf('0000005566',serials=['AAA001']),'Original.pdf'),
                       payload(phoenix_like_pdf('0000005566',serials=['BBB002']),'Changed.pdf')]
                r=client.post(f'/api/quotes/{q}/invoice-batch-preview',json={'files':files})
                self.assertEqual(r.status_code,409,r.text[:200])
                self.assertEqual(client.get(f'/api/quotes/{q}').json()['quote']['assets'],[])

    def test_single_invoice_api_rejects_repeat_serial(self):
        with tempfile.TemporaryDirectory() as d,mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'}),mock.patch.object(main,'DB',Path(d)/'local.db'):
            with TestClient(main.app) as client:
                q=client.post('/api/quotes').json()['quote']['id']
                one=payload(phoenix_like_pdf('0000005567',serials=['AAA111']),'First.pdf')
                p=client.post(f'/api/quotes/{q}/invoice-preview',json=one)
                self.assertEqual(p.status_code,200,p.text[:200])
                done=client.post(f'/api/quotes/{q}/invoice-import',json={**one,'content_sha256':p.json()['content_sha256']})
                self.assertEqual(done.status_code,200,done.text[:200])
                two=payload(phoenix_like_pdf('0000005568',serials=['AAA111']),'Second.pdf')
                denied=client.post(f'/api/quotes/{q}/invoice-preview',json=two)
                self.assertEqual(denied.status_code,409,denied.text[:200])
                self.assertEqual(sum(a['qty'] for a in client.get(f'/api/quotes/{q}').json()['quote']['assets']),1)

    def test_invalid_pdf_json_rejected_as_bad_request(self):
        with tempfile.TemporaryDirectory() as d,mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'}),mock.patch.object(main,'DB',Path(d)/'local.db'):
            with TestClient(main.app) as client:
                q=client.post('/api/quotes').json()['quote']['id']
                r=client.post(f'/api/quotes/{q}/invoice-batch-preview',json={'files':[{'filename':'X.pdf','content_base64':5}]})
                self.assertEqual(r.status_code,400,r.text[:200])


if __name__=='__main__':unittest.main()
