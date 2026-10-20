"""Content-based file routing and provisional strength-source pricing controls."""
import base64,io,os,tempfile,unittest
from pathlib import Path
from unittest import mock
from zipfile import ZipFile
import fitz
from fastapi.testclient import TestClient
from document_classifier import classify_document
import main

def sample_pdf(*lines):
    doc=fitz.open();page=doc.new_page()
    for index,line in enumerate(lines):page.insert_text((45,75+index*22),line)
    data=doc.tobytes();doc.close();return data

def sample_workbook(*headings):
    cells=''.join('<c t="inlineStr"><is><t>'+h+'</t></is></c>' for h in headings)
    xml='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row>'+cells+'</row></sheetData></worksheet>'
    memory=io.BytesIO()
    with ZipFile(memory,'w') as z:
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Sheet1" sheetId="1"/></sheets></workbook>')
        z.writestr('xl/worksheets/sheet1.xml',xml)
    return memory.getvalue()

class DocumentClassificationTests(unittest.TestCase):
    def test_pdf_uses_content_not_filename(self):
        invoice=sample_pdf('PULSE FITNESS INVOICE','Document No: 53274','Tax Point: 05/12/2018')
        agreement=sample_pdf('PULSE FITNESS MAINTENANCE AGREEMENT','Agreement number c7335')
        self.assertEqual(classify_document('unknown.pdf',invoice)['kind'],'invoice')
        self.assertEqual(classify_document('unknown.pdf',agreement)['kind'],'agreement')
        self.assertFalse(classify_document('invoice.pdf',sample_pdf('CREDIT NOTE'))['kind'])
        self.assertFalse(classify_document('invoice.pdf',sample_pdf('Generic PDF'))['kind'])
    def test_spreadsheet_uses_headings_not_filename(self):
        self.assertEqual(classify_document('file.xlsx',sample_workbook('Model','Serial Number','Quantity','Site'))['kind'],'assets')
        self.assertEqual(classify_document('file.xlsx',sample_workbook('RRP','Annual Maintenance Cost','Monthly Fee','Discount'))['kind'],'calculations')
        self.assertEqual(classify_document('historical.xls',b'old format')['kind'],'calculations')
    def test_api_detection_does_not_import_or_change_quotes(self):
        with tempfile.TemporaryDirectory() as d,mock.patch.dict(os.environ,{'SMARTQUOTE_AUTH':'off'}),mock.patch.object(main,'DB',Path(d)/'test.db'):
            with TestClient(main.app) as client:
                quote=client.post('/api/quotes').json()['quote']['id']
                raw=sample_pdf('PULSE FITNESS INVOICE','Document No: 53274','Tax Point: 05/12/2018')
                payload={'filename':'mystery.pdf','content_base64':base64.b64encode(raw).decode()}
                resp=client.post('/api/documents/detect',json=payload)
                self.assertEqual(resp.status_code,200,resp.text)
                self.assertEqual(resp.json()['kind'],'invoice')
                self.assertTrue(resp.json()['confidence']=='high')
                self.assertEqual(client.get(f'/api/quotes/{quote}').json()['quote']['assets'],[])
                self.assertEqual(client.get(f'/api/quotes/{quote}').json()['quote']['files'],[])
                self.assertEqual(client.post('/api/documents/detect',json={'filename':'x.pdf','content_base64':'NOT-BASE64'}).status_code,400)
    def test_browser_uses_server_detection_and_only_auto_previews(self):
        script=(Path(__file__).resolve().parents[1]/'static/app.js').read_text('utf-8')
        self.assertIn("api('/api/documents/detect'",script)
        self.assertIn('await Promise.all(added.map(identifyStagedUpload))',script)
        self.assertIn("if(added.every(x=>x.kind==='invoice'))",script)
        self.assertIn("if(added.length===1&&added[0].kind==='assets')",script)
        self.assertIn('Agreements and historic calculations use',script)
        self.assertIn('compactMachineDescription(name)',script)

if __name__=='__main__':unittest.main()
