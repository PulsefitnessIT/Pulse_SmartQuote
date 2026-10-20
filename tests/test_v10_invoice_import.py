"""Invoice importer regression: only synthetic documents, never private customer PDFs."""
import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import fitz
from fastapi.testclient import TestClient
from invoice_import import read_invoice_pdf
import main


def synthetic_invoice():
    doc=fitz.open()
    p=doc.new_page(width=595,height=842)
    for x,y,text in [
        (440,80,'INVOICE'),
        (20,120,'PULSE FITNESS LIMITED'),
        (60,180,'Test Leisure Ltd\nStreet Road\nCity\nAA1 1AA'),
        (310,180,'Demo Fitness Centre\nMain Street\nCity\nAA1 1BB'),
        (220,245,'Order No: 12808   Document No: 53274'),
        (220,265,'Account No: W123  Tax Point: 05/12/2018'),
        (23,340,'H - Resistance Equipment\nProduct Group: '),
        (21,390,'£0.00\n560HDS\nH Range Leg Extension Dark Silver\n£0.00\n2'),
        (32,470,'Serial Numbers'),
        (45,493,'560H100001, 560H100002'),
        (21,550,'-£100.00\nTRADEIN\nTrade In\n-£100.00\n1')]:
        p.insert_text((x,y),text,fontsize=9)
    data=doc.tobytes()
    doc.close()
    return data


class InvoiceExtractTests(unittest.TestCase):
    def test_zero_sale_strength_equipment_is_retained_and_tradein_excluded(self):
        result=read_invoice_pdf(synthetic_invoice(),'synthetic.pdf')
        self.assertEqual(result['invoice']['customer'],'Test Leisure Ltd')
        self.assertEqual(result['invoice']['site'],'Demo Fitness Centre')
        self.assertEqual(result['invoice']['invoice_no'],'53274')
        self.assertEqual(result['report']['equipment_lines'],1)
        self.assertEqual(result['report']['equipment_units'],2)
        self.assertEqual(result['report']['serial_count'],2)
        self.assertEqual(result['report']['zero_sale_equipment_lines'],1)
        self.assertFalse(result['report']['invoice_sales_prices_used_as_rrp'])
        self.assertEqual(result['assets'][0]['code'],'560HDS')
        self.assertEqual(result['assets'][0]['serials'],['560H100001','560H100002'])
        self.assertEqual(result['excluded'][0]['code'],'TRADEIN')
        self.assertNotIn('rrp',result['assets'][0])

    def test_noninvoice_rejected(self):
        d=fitz.open();d.new_page();raw=d.tobytes();d.close()
        with self.assertRaisesRegex(ValueError,'supports selectable-text'):
            read_invoice_pdf(raw)

    def test_invoice_preview_is_read_only_import_requires_matching_sha(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'}), mock.patch.object(main,'DB',Path(d)/'test_only.db'):
            with TestClient(main.app) as client:
                q=client.post('/api/quotes').json()['quote']['id']
                payload={'filename':'synthetic.pdf','content_base64':base64.b64encode(synthetic_invoice()).decode()}
                p=client.post(f'/api/quotes/{q}/invoice-preview',json=payload)
                self.assertEqual(p.status_code,200,p.text[:400])
                self.assertEqual(p.json()['report']['equipment_units'],2)
                self.assertEqual(client.get(f'/api/quotes/{q}').json()['quote']['assets'],[])
                self.assertEqual(client.post(f'/api/quotes/{q}/invoice-import',json=payload).status_code,409)
                payload['content_sha256']=p.json()['content_sha256']
                got=client.post(f'/api/quotes/{q}/invoice-import',json=payload)
                self.assertEqual(got.status_code,200,got.text[:400])
                quote=got.json()['quote'];self.assertEqual(len(quote['assets']),1)
                self.assertEqual(quote['assets'][0]['qty'],2)
                self.assertEqual(quote['customer'],'Test Leisure Ltd')
                self.assertEqual(quote['site'],'Demo Fitness Centre')
                self.assertFalse(quote['pricing_approved'])
                self.assertFalse(quote['line_reviews_approved'])
                self.assertEqual(client.post(f'/api/quotes/{q}/invoice-import',json=payload).status_code,409)
                p2=client.post(f'/api/quotes/{q}/invoice-preview',json=payload)
                self.assertTrue(p2.json()['already_imported'])

if __name__=='__main__':unittest.main()
