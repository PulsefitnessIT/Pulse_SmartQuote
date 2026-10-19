"""Import historic Pulse maintenance agreements as source-evidenced renewal drafts.

Extract machine, quantity and serials from the Schedule 3 form fields/table.
Never carry forward old prices as current, or assume unclear equipment identities.
"""
from __future__ import annotations
import io,re
from pathlib import Path


def _field(page):
    return {w.field_name:(w.field_value or '').strip() for w in (page.widgets() or []) if w.field_name}


def _items(v):
    return [re.sub(r'\s+',' ',s).strip() for s in re.split(r'[\r\n]+',v or '') if s.strip()]


def read_agreement_pdf(data:bytes,filename='Previous agreement.pdf'):
    try:import fitz
    except ImportError:raise ValueError('PDF support is not installed. Install requirements.txt and restart SmartQuote.')
    if len(data)>35*1024*1024:raise ValueError('Agreement PDF must be under 35 MB.')
    try:doc=fitz.open(stream=data,filetype='pdf')
    except Exception:raise ValueError('This does not appear to be a readable PDF agreement.')
    if doc.needs_pass:raise ValueError('Password-protected agreement: unlock a copy before importing.')
    if len(doc)>100:raise ValueError('Agreement is too long; use a document under 100 pages.')
    first=_field(doc[0]) if len(doc) else {}
    cover=doc[0].get_text() if len(doc) else ''
    agreement_ref=first.get('Agreement number','') or (re.search(r'Agreement number\s*:?\s*([A-Z0-9/-]+)',cover,re.I).group(1) if re.search(r'Agreement number\s*:?\s*([A-Z0-9/-]+)',cover,re.I) else '')
    customer=first.get('The customer','')
    site=first.get('In respect of','')
    address='\n'.join(first[k] for k in ('undefined','undefined_2','undefined_3','undefined_4') if first.get(k))
    contract={}
    for p in doc[:min(3,len(doc))]:
        f=_field(p)
        if 'Dropdown1' in f:
            contract={'tier':f.get('Dropdown1',''), 'start_date':f.get('Start Date',''),
                      'end_date':f.get('End date',''), 'agreement_length':f.get('Dropdown2',''),
                      'visits_text':f.get('Dropdown3',''), 'previous_total':f.get('totalling','') or f.get('Or Lump sum payment of',''),
                      'coverage_text':f.get('Whats covered',''), 'exclusions':f.get('Exclusions','')}
            break
    assets=[];warnings=[];sheets=[]
    for i,page in enumerate(doc):
        f=_field(page)
        code_val=f.get('Machine1', f.get('Machine',''))
        descr_val=f.get('Description1', f.get('Description',''))
        qty_val=f.get('Qty1', f.get('Qty',''))
        if not(code_val and descr_val and qty_val):continue
        codes=_items(code_val)
        descriptions=_items(descr_val)
        quantities=_items(qty_val)
        if not codes or not quantities:continue
        if len(codes)!=len(quantities) or len(descriptions)<len(codes):
            warnings.append(f'Page {i+1}: equipment columns do not align cleanly. Review the imported lines carefully.')
        # Coordinates locate serials in the same row; preserve 0-prefixed serials.
        words=page.get_text('words')
        starts=[]
        for code in codes:
            pos=next((w[1] for w in words if w[0]<85 and w[4].strip().upper()==code.upper() and (not starts or w[1]>starts[-1]+1)),None)
            starts.append(pos)
        if any(x is None for x in starts):
            warnings.append(f'Page {i+1}: some serial-to-row positions could not be verified; compare with the original agreement.')
        page_added=0
        for j,code in enumerate(codes[:min(len(descriptions),len(quantities))]):
            try:
                qty=int(quantities[j]);assert 1<=qty<=10000
            except (ValueError,AssertionError):
                warnings.append(f'Page {i+1}, machine {code}: invalid contract quantity; not imported.');continue
            y=starts[j]
            nexty=next((v for v in starts[j+1:] if v is not None),1e10)
            serial=[]
            if y is not None:
                serial=[(w[0],w[1],w[4].strip()) for w in words if w[0]>655 and y-4<=w[1]<min(nexty-1,480) and w[4].strip()]
            serial.sort(key=lambda x:(round(x[1]/7),x[0]))
            serials=[v[2] for v in serial]
            if serials and len(serials)!=qty:warnings.append(f'Page {i+1}: {code} has {qty} units but {len(serials)} serials extracted; check agreement.')
            desc=descriptions[j].replace('**','').strip()
            console=''
            m=re.search(r'\bwith\s+(\d+(?:\.\d+)?["″]\s*(?:monitor|screen|console))',desc,re.I)
            if m:console=m.group(1)
            elif re.search(r'\bwith console\b',desc,re.I):console='Console - model not specified'
            assets.append({'source_sheet':f'Agreement page {i+1}', 'source_row':j+1,'code':code,
                           'name':desc,'model':code,'console':console,'make':'','qty':qty,
                           'original_qty':str(qty),'serial':', '.join(serials),'site':site,
                           'source_document':filename,'prior_contract_ref':agreement_ref})
            page_added+=1
        sheets.append({'sheet':f'Schedule 3 / page {i+1}','rows':len(codes),'added':page_added,'detected':True,'columns':['machine','description','qty','serial']})
    doc.close()
    if not assets:raise ValueError('No readable Schedule 3 equipment rows found. This importer supports selectable-text Pulse maintenance agreement PDFs; scanned documents need a manual review or conversion.')
    total=sum(a['qty'] for a in assets)
    return {'assets':assets,'warnings':warnings,'sheets':sheets,
            'contract':{'customer':customer,'site':site,'delivery_address':address,'billing_address':'',
                        'contract_ref':agreement_ref,**contract},
            'report':{'lines':len(assets),'units':total,'previous_total':contract.get('previous_total',''), 'agreement_ref':agreement_ref}}
