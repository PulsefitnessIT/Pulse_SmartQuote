"""The quote builder must expose one mixed-document upload panel."""
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'static/index.html').read_text(encoding='utf-8')
JS=(ROOT/'static/app.js').read_text(encoding='utf-8')

class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=[]
        self.inputs=[]
    def handle_starttag(self,tag,attrs):
        attributes=dict(attrs)
        if 'id' in attributes:self.ids.append(attributes['id'])
        if tag=='input':self.inputs.append(attributes)

class UnifiedUploadTests(unittest.TestCase):
    def test_one_picker_in_builder_accepts_all_document_types(self):
        builder=HTML.split('id="builderView"',1)[1].split('id="quoteDetails"',1)[0]
        parser=Elements();parser.feed(builder)
        inputs=[x for x in parser.inputs if x.get('type')=='file']
        self.assertEqual(len(inputs),1,inputs)
        picker=inputs[0]
        self.assertEqual(picker['id'],'filePicker')
        self.assertIn('multiple',picker)
        for ext in ('.pdf','.xlsx','.xls','.csv','.tsv','.txt'):
            self.assertIn(ext,picker['accept'])
        for control in ('dropzone','uploadQueue','uploadQueueItems','reviewInvoiceBatch','invoicePreview'):
            self.assertEqual(parser.ids.count(control),1,control)

    def test_separate_cards_and_handlers_removed(self):
        for old in ('browseInvoice','invoicePicker','browseAgreement','agreementPicker',
                    'browseOldCalcs','oldCalcsPicker'):
            self.assertNotIn('id="'+old+'"',HTML)
            self.assertNotIn("$('"+old+"')",JS)
        self.assertIn('stageUploadFiles(e.dataTransfer.files)',JS)
        self.assertIn('stageUploadFiles(e.target.files)',JS)

    def test_all_preview_and_import_paths_retained(self):
        for route in ('/import-preview','/invoice-batch-preview','/invoice-batch-import',
                      '/agreement-import','/old-calcs-import'):
            self.assertIn(route,JS)
        for method in ('importFile','previewInvoices','importAgreement','importOldCalcs'):
            self.assertIn('function '+method+'(',JS)
        self.assertIn("if(entryId!==null)removeStagedUpload(entryId)",JS)
        self.assertIn('queueEntryIds',JS)

    def test_file_type_detection_and_ambiguous_pdf_handling(self):
        functions=JS.split('function uploadTypesFor(file){',1)[1].split('function removeStagedUpload(id){',1)[0]
        js='function uploadTypesFor(file){'+functions+"""
        const assert=require('node:assert/strict');
        const file=name=>({name});
        assert.equal(suggestedUploadType(file('Invoice - 53274 Evesham.pdf')),'invoice');
        assert.equal(suggestedUploadType(file('Maintenance Agreement 2026.pdf')),'agreement');
        assert.equal(suggestedUploadType(file('document.pdf')),'');
        assert.equal(suggestedUploadType(file('M Club Newcastle.xlsx')),'assets');
        assert.equal(suggestedUploadType(file('Historic Quotation Calculations.xlsx')),'calculations');
        assert.equal(suggestedUploadType(file('historic.xls')),'calculations');
        assert.equal(suggestedUploadType(file('assets.csv')),'assets');
        assert.deepEqual(uploadTypesFor(file('unknown.exe')),[]);
        """
        result=subprocess.run(['node','-e',js],capture_output=True,text=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
