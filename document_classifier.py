"""Read-only content recognition for the unified SmartQuote file uploader.

Never changes a quote. Unrecognised/scanned documents require staff review.
"""
from __future__ import annotations
import io,re,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ALLOWED={'.pdf','.xlsx','.xls','.csv','.tsv','.txt'}

def _result(kind='',reason='',confidence='review'):
    return {'kind':kind,'reason':reason,'confidence':confidence,'requires_type_selection':not bool(kind)}

def classify_document(filename,raw):
    ext=Path(str(filename)).suffix.lower()
    if ext not in ALLOWED or not raw:return _result(reason='Empty or unsupported file')
    if ext=='.pdf':
        try:
            import fitz
            doc=fitz.open(stream=raw,filetype='pdf')
            if doc.needs_pass:return _result(reason='Password protected PDF: unlock before importing')
            words=[];fields=[]
            for page in list(doc)[:min(2,len(doc))]:
                words.append(page.get_text('text')[:18000])
                fields.extend(str(w.field_name or '') for w in (page.widgets() or []))
            doc.close()
            text=' '.join(words).casefold()
            field_text=' '.join(fields).casefold()
            if not text.strip() and not field_text:
                return _result(reason='Scan/image-only PDF: review manually')
            if re.search(r'\bcredit\s+(?:note|memo)\b',text):
                return _result(reason='Credit notes must be reviewed separately, not imported as sales')
            invoice=(('line item code' in text and ('invoice' in text or 'customer ref' in text))
                     or ('document no:' in text and 'tax point:' in text and 'invoice' in text))
            agreement=('agreement number' in text or 'maintenance agreement' in text
                       or ('schedule 3' in text and 'maintenance' in text)
                       or ('machine1' in field_text and 'qty1' in field_text)
                       or ('the customer' in field_text and 'in respect of' in field_text))
            if invoice and not agreement:return _result('invoice','Recognised Pulse sales-invoice content','high')
            if agreement and not invoice:return _result('agreement','Recognised maintenance-agreement content','high')
            return _result(reason='PDF type unclear: choose the appropriate document type')
        except Exception:
            return _result(reason='Unreadable PDF: check the original document')
    if ext in ('.csv','.tsv','.txt'):return _result('assets','Recognised equipment data list','high')
    if ext=='.xls':return _result('calculations','Legacy Excel workbook (old calculations importer)','high')
    # Standard-library-only inspection: works in the portable Windows EXE.
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            strings=[]
            for name in archive.namelist():
                if name in ('xl/workbook.xml','xl/sharedStrings.xml') or re.fullmatch(r'xl/worksheets/sheet\d+\.xml',name):
                    if archive.getinfo(name).file_size>8_000_000:continue
                    root=ET.fromstring(archive.read(name))
                    strings.extend(str(n.text or '') for n in root.iter() if n.tag.rsplit('}',1)[-1] in ('t','v','name'))
            text=' '.join(strings).casefold()[:100000]
    except (OSError,ValueError,zipfile.BadZipFile,ET.ParseError,RuntimeError):
        return _result(reason='Workbook could not be inspected')
    if not text.strip():return _result(reason='Workbook headings not readable')
    commercial=sum(bool(re.search(p,text)) for p in
      (r'\brrp\b',r'\bannual\b|\byearly\b',r'\bmonthly\b|\bper month\b',
       r'contract pric|maintenance pric|maintenance rate|service rate|cost calculation',
       r'\bdiscount\b|\bmargin\b',r'\bcalc(?:ulation)?s?\b'))
    assets=sum(bool(re.search(p,text)) for p in
      (r'serial\s*(?:number|no\b|num\b)',r'\bmodel\b|\bsku\b|product code',
       r'\bquantity\b|\bqty\b',r'\bsite\b|\blocation\b|\bcustomer\b'))
    if commercial>=2 and (commercial>=assets or ('rrp' in text and commercial>=3)):
        return _result('calculations','Recognised maintenance pricing/calculation columns','high')
    if assets>=2 and commercial<3:
        return _result('assets','Recognised model/serial/quantity columns','high')
    return _result(reason='Spreadsheet purpose unclear: choose asset list or old calculations')
