"""Source-traceable Pulse invoice-to-maintenance-asset candidate preview.

An old *sale invoice* is NOT a current RRP source. Never use its sale prices
for maintenance calculations; never treat sales at £0 as zero-maintenance assets.
Only machine candidates enter quote drafts. Every exclusion remains in preview.
"""
from __future__ import annotations
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import re

AMOUNT = re.compile(r'^-?£[\d,]+\.\d{2}$')
CODE = re.compile(r'^[\w][\w./ -]{1,24}$', re.I)
PLACEHOLDER_SERIALS = {'5206/3', '-', 'N/A', 'NA', '0'}
COMMERCIAL_GROUPS = {'customer care', 'trade in', 'pulse move management system'}
MISC_PRODUCT_CODES = {'ACCESSORIES', 'TRADEIN', 'CUSTOMER', 'SMART'}
SERIAL_TRIGGER = re.compile(r'^Serial Numbers?\s*$', re.I)

def _money(value):
    try:
        return Decimal(value.replace('£', '').replace(',', ''))
    except (ValueError, InvalidOperation):
        return None

def _serials(blocks, start):
    """Read serial blocks attached to *one* invoice stock-code row."""
    pieces = []
    serial_section = False
    for block in blocks[start:start+4]:
        lines = [x.strip() for x in block[4].splitlines() if x.strip()]
        if not lines:
            continue
        if SERIAL_TRIGGER.match(lines[0]):
            serial_section = True
            continue
        if lines[-1].startswith('Product Group:') or ('Product Group:' in lines) or _item(lines) or lines[0].startswith('Our Ref:'):
            break
        if serial_section:
            # Trailing hyphens are part of serials that wrap over a printed line.
            for line in lines:
                if pieces and pieces[-1].endswith('-'):
                    pieces[-1] += line
                else:
                    pieces.append(line)
    combined = ' '.join(pieces)
    serials = [re.sub(r'\s+', '',x) for x in combined.split(',') if x.strip()]
    valid = [x for x in serials if x.upper() not in PLACEHOLDER_SERIALS]
    return valid, bool(serials) and not valid

def _item(lines):
    # The PDF's selection order puts Total first, then product code,
    # description, Unit and Qty. Coordinates/blocks avoid repeated headers.
    if len(lines) != 5 or not AMOUNT.fullmatch(lines[0]) or not AMOUNT.fullmatch(lines[3]):
        return None
    if not CODE.fullmatch(lines[1]) or not re.fullmatch(r'\d{1,5}', lines[4]):
        return None
    return {'code':lines[1], 'name':lines[2], 'unit':_money(lines[3]),
            'total':_money(lines[0]), 'qty':int(lines[4])}

def _text_address(blocks, xlow, xhigh):
    values=[]
    for block in blocks:
        if (125 <= block[1] <= 205 and xlow <= block[0] < xhigh):
            values += [s.strip() for s in block[4].splitlines() if s.strip()]
    return values

# A second Pulse invoice layout (e.g. the 2021 Phoenix/Siemens template) uses
# horizontally positioned stock-code rows and serials which may spill across pages.
MODERN_SALE_RE = re.compile(r'^\d[\d,]*\.\d{2}$')
MISC_NOT_CONTRACT_ASSETS = re.compile(
    r'(?i)(?:\bTRAKK\b|\blicen[cs]e\b|software installation|\bNFC wristbands?\b|'
    r'\bNFC tag reader\b|\b(?:olympic|bumper|competition|training|tri-grip|freeweight)\s+plates?\b|\bbumper plates?\b|'
    r'\b(?:dumbbells?|barbells?|kettlebells?|medicine balls?|slam balls?|swiss balls?|wall balls?)\b|'
    r'\bBOSU\b|\bbasebags?\b|\bbattle ropes?\b|\bpower straps?\b|'
    r'\bfoam plyo boxes?\b|\btraining bands?\b|\b86["\x27] ?bar\b)'
)


def _modern_words_by_line(page):
    """Group text by printed baseline, not PDF stream order."""
    words = sorted((w for w in page.get_text('words') if 318 <= w[1] < 735),
                   key=lambda w: (w[1], w[0]))
    lines = []
    for w in words:
        if lines and abs(w[1] - lines[-1][0]) < 2.4:
            lines[-1][1].append(w)
        else:
            lines.append((w[1], [w]))
    for _, row in lines:
        yield sorted(row, key=lambda w: w[0])


def _modern_invoice(doc, raw, filename):
    """Read numbered Pulse 2021-format invoice rows, including cross-page serials."""
    head = doc[0].get_text('text')
    meta = re.search(r'\bInvoice\s+(\d{6,12})\s+Customer Ref:\s*(\S+)\s+Account Ref\s+(\S+)', head)
    date = re.search(r'\b\d{2}/\d{2}/\d{4}\b', head)
    order = re.search(r'\bSales Order Ref\s+(\d+)', head)
    if not meta or not date:
        raise ValueError('Could not read the invoice reference/date. No equipment has been added.')
    first_blocks = doc[0].get_text('blocks')
    address_lines = next((b[4].splitlines() for b in first_blocks
        if 140 < b[1] < 210 and 'Invoice Address' not in b[4]
        and len([x for x in b[4].splitlines() if x.strip()]) >= 2
        and ('Financial Services' in b[4] or 'Leasing Ltd' in b[4])), [])
    # Fallback: at the printed header, the second address column is the site.
    site = next((x.strip() for x in address_lines[1:2]), '')
    billed = address_lines[0].strip() if address_lines else ''
    if not site:
        # Use coordinates rather than silently assuming the bill-to party owns the assets.
        head_lines = doc[0].get_text('text').splitlines()
        ix = next((i for i,s in enumerate(head_lines) if s.strip()=='Delivery Address'), -1)
        site = head_lines[ix+2].strip() if ix>=0 and len(head_lines)>ix+2 else ''
    if not site:
        raise ValueError('Invoice delivery site was not identified. Confirm location before importing.')
    rows=[];current=None
    for page_no,page in enumerate(doc,1):
        for words in _modern_words_by_line(page):
            first = [w for w in words if 40 <= w[0] < 58]
            is_item = bool(first and first[0][4].isdigit()
                           and 1 <= int(first[0][4]) <= 999)
            desc_part = ' '.join(w[4] for w in words if 165 <= w[0] < 335)
            if is_item:
                sequence = int(first[0][4])
                code_tokens = [w[4] for w in words if 60 <= w[0] < 165]
                code = (code_tokens[0] if code_tokens and re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{2,}',code_tokens[0]) else '')
                qtys = [w[4] for w in words if 335 <= w[0] < 373 and w[4].isdigit()]
                unit = [w[4] for w in words if 375 <= w[0] < 460 and MODERN_SALE_RE.fullmatch(w[4])]
                total = [w[4] for w in words if 465 <= w[0] < 551 and MODERN_SALE_RE.fullmatch(w[4])]
                if rows and sequence != rows[-1]['sequence']+1:
                    raise ValueError('Non-consecutive invoice lines; the PDF may be incomplete.')
                current = {'sequence':sequence,'code':code,'name':desc_part,
                           'qty':int(qtys[0]) if qtys else None,
                           'unit':_money(unit[0]) if unit else None,
                           'total':_money(total[0]) if total else None,
                           'serials':[], 'page':page_no}
                rows.append(current)
                continue
            if current is None:
                continue
            if first and first[0][4].startswith('Batch/Serial'):
                serial_tokens = [w[4] for w in words if 150 <= w[0] < 335 and w[4] != ':']
                if serial_tokens:
                    serial = ''.join(serial_tokens).strip()
                    if serial and serial.upper() not in PLACEHOLDER_SERIALS:
                        current['serials'].append(serial)
            elif not any(w[0] < 150 for w in words):
                # Multiline equipment descriptions; no page header/footer content.
                if desc_part and not desc_part.startswith(('N.B.', 'Products marked')):
                    current['name'] += ' ' + desc_part
    if not rows or len(rows) < 1:
        raise ValueError('No numbered invoice stock-code rows were found.')
    invoice={'invoice_no':meta.group(1),'date':date.group(0),
             'customer':site, 'site':site, 'billed_to':billed,
             'customer_needs_confirmation':bool(billed and billed.casefold()!=site.casefold()),
             'account_ref':meta.group(3),'customer_ref':meta.group(2),
             'sales_order_ref':order.group(1) if order else '',
             'billing_address':billed,'delivery_address':site, 'pages':len(doc)}
    assets=[];excluded=[];warnings=[]
    for row in rows:
        code=row['code'];name=row['name'].strip()
        qty=row['qty']
        doc_row={'code':code,'name':name,'qty':qty,'serials':row['serials'],
                 'page':row['page'],'source_sheet':f'Invoice page {row["page"]}',
                 'source_row':row['sequence'],'source_document':filename,
                 'invoice_ref':invoice['invoice_no'],'source_invoice_date':date.group(0),
                 'invoice_unit_sale_price':str(row['unit']) if row['unit'] is not None else None,
                 'invoice_line_sale_total':str(row['total']) if row['total'] is not None else None,
                 'invoice_sale_values_are_not_rrp':True,
                 'invoice_purchase_sku_identified':bool(code)}
        reason=''
        if not code:
            reason='Warranty, sales note or non-stock item; not a machine'
        elif code.upper().startswith(('TRK-','26-164')):
            reason='Software, licence, installation or TRAKK accessory; not a machine'
        elif (code.upper().startswith('38-') and code.upper()!='38-610-AAA') or (MISC_NOT_CONTRACT_ASSETS.search(name) and not re.search(r'\b(?:weight stack|tire flip machine)\b',name,re.I)):
            reason='Loose weights, accessories or consumables; review separately if contracted'
        if reason:
            excluded.append({**doc_row,'reason':reason})
            continue
        if not isinstance(qty,int) or qty<1 or qty>1000:
            excluded.append({**doc_row,'reason':'Missing or suspicious quantity; requires manual review'})
            continue
        if len(row['serials'])!=qty:
            warnings.append(f'Page {row["page"]}: {code} has {qty} invoiced units but {len(row["serials"])} serial numbers; confirm missing serials.')
        if code=='224B-AAB' and qty==21 and len(row['serials'])!=21:
            warnings.append('Group Cycle serial numbers span multiple invoice pages. Verify all 21 were captured.')
        assets.append({**doc_row, 'model':code.split('-')[0], 'make':'Pulse Fitness',
                       'serial':', '.join(row['serials']),'original_qty':str(qty),
                       'site':site, 'console':_console_from_description(name),
                       'identification_evidence':'Exact invoice product SKU; console read from the original sale description'})
    if not assets:
        raise ValueError('This invoice has no contract-relevant equipment rows.')
    if invoice['customer_needs_confirmation']:
        warnings.append(f'Invoice billed to {billed}, but assets delivered to {site}. Confirm the maintenance contract customer; do not default to the finance provider.')
    warnings.append('Invoice may describe a five-year warranty/service package: verify dates and coverage before quoting a new contract.') if any('Warranty - 5 years' in r['name'] for r in rows) else None
    return {'invoice':invoice,'assets':assets,'excluded':excluded,'unstructured_review':[],
            'warnings':warnings,
            'report':{'source_rows':len(rows),'equipment_lines':len(assets),
                      'equipment_units':sum(x['qty'] for x in assets),
                      'non_equipment_rows':len(excluded), 'unstructured_review_rows':0,
                      'zero_sale_equipment_lines':sum(x['invoice_unit_sale_price']=='0.00' for x in assets),
                      'serial_count':sum(len(x['serials']) for x in assets),
                      'invoice_sales_prices_used_as_rrp':False},
            'content_sha256':hashlib.sha256(raw).hexdigest()}


def _console_from_description(name):
    n=name.lower()
    if '18.5' in n and ('touch' in n or 'console' in n):
        return '18.5-inch touchscreen'
    if '10.1' in n and ('touch' in n or 'console' in n):
        return '10.1-inch touchscreen'
    if 'st22.2' in n:
        return 'ST22.2 Console'
    if 'pm5' in n:
        return 'PM5 Console'
    return ''


def read_invoice_pdf(data:bytes, filename='Historic sales invoice.pdf'):
    """Return source-led candidates and non-equipment lines; make no database changes."""
    if not isinstance(data, bytes) or len(data)>35*1024*1024:
        raise ValueError('Invoice PDF must be under 35 MB.')
    try:
        import fitz
        doc=fitz.open(stream=data, filetype='pdf')
    except Exception as e:
        raise ValueError('This invoice is not a readable PDF.') from e
    try:
        if doc.needs_pass:
            raise ValueError('This invoice is password-protected. Unlock a copy first.')
        if len(doc)>100:
            raise ValueError('Invoice exceeds 100 pages.')
        if doc and 'Line Item Code' in doc[0].get_text('text') and 'Batch/Serial Number' in doc[0].get_text('text'):
            return _modern_invoice(doc,data,filename)
        first=doc[0].get_text(sort=True) if len(doc) else ''
        if 'INVOICE' not in first.upper() or 'PULSE FITNESS' not in first.upper():
            raise ValueError('This importer currently supports selectable-text Pulse Fitness sales invoices only.')
        first_blocks=doc[0].get_text('blocks')
        billed=_text_address(first_blocks,40,300)
        delivered=_text_address(first_blocks,300,470)
        customer=billed[0] if billed else ''
        site=delivered[0] if delivered else ''
        m=re.search(r'Document No:\s*(\d+)',first)
        invoice_no=m.group(1) if m else ''
        date_match=re.search(r'Tax Point:\s*(\d{2}/\d{2}/\d{4})',first)
        date=date_match.group(1) if date_match else ''
        account_match=re.search(r'Account No:\s*([A-Z0-9-]+)',first)
        account=account_match.group(1) if account_match else ''
        order_match=re.search(r'Order No:\s*([A-Z0-9-]+)',first)
        order=order_match.group(1) if order_match else ''
        assets=[];excluded=[];warnings=[];all_rows=[];unstructured=[];active_group=''
        for page_no,page in enumerate(doc, start=1):
            blocks=sorted(page.get_text('blocks'),key=lambda b:(round(b[1],2),round(b[0],2)))
            for i, block in enumerate(blocks):
                lines=[v.strip() for v in block[4].splitlines() if v.strip()]
                if not lines:
                    continue
                if 'Product Group:' in lines and len(lines)>=2:
                    active_group=next((v for v in lines if v != 'Product Group:' and not v.startswith('Product Group:')),active_group)
                    if lines[0].startswith('Product Group:'):
                        active_group=lines[0].split('Product Group:',1)[-1].strip() or active_group
                    continue
                row=_item(lines)
                if not row:
                    # Sales configurations continue for several pages as loose
                    # descriptions, often without an explicit quantity or SKU.
                    # Never manufacture an asset count from this narrative.
                    if page_no>=9 and 315<=block[1]<=770 and block[0]<250:
                        non_amount=[v for v in lines if not AMOUNT.fullmatch(v)]
                        label=' '.join(non_amount).strip()
                        if (label and
                            re.search(r'(?:sled|rack|xcube|flooring|plyoblock|bosu|barbell|bumper|basebag|kettlebell|dumbbell|tr[a-z]* handle|curl bar|crossfit bar|olympic bar|quick lock|\b751H\b)',label,re.I) and
                            not label.startswith('Product Group:')):
                            unstructured.append({'page':page_no,'description':label,
                               'source_sale_total':str(_money(lines[0])) if AMOUNT.fullmatch(lines[0]) else None,
                               'reason':'Loose invoice description has no verified machine/quantity row; check whether it duplicates a listed asset or should be separately included'})
                    continue
                c=row['code'].upper()
                serials,placeholder=([],False) if c in {'TRADEIN', 'ACCESSORIES', 'CUSTOMER CARE', 'SMART CENTRE'} else _serials(blocks,i+1)
                group=active_group.casefold()
                excluded_type=(c in MISC_PRODUCT_CODES or group in COMMERCIAL_GROUPS
                  or row['total'] is not None and row['total']<0
                  or 'accessor' in row['name'].casefold() and c=='ACCESSORIES')
                reason=('non-equipment commercial or accessory line' if excluded_type else '')
                if not excluded_type and (row['qty']>1000 or row['qty']<1):
                    excluded_type=True;reason='unusual invoice quantity; requires manual review'
                common={'code':row['code'],'name':row['name'],'qty':row['qty'],
                        'serials':serials,'product_group':active_group,'page':page_no,
                        'invoice_unit_sale_price':str(row['unit']) if row['unit'] is not None else None,
                        'invoice_line_sale_total':str(row['total']) if row['total'] is not None else None,
                        'invoice_sale_values_are_not_rrp':True,'source_document':filename,
                        'source_row':len(all_rows)+1}
                all_rows.append(common)
                if excluded_type:
                    excluded.append({**common,'reason':reason})
                    continue
                if len(serials)!=row['qty']:
                    warnings.append(f'Page {page_no}: {c} has quantity {row["qty"]} but {len(serials)} verified serial numbers. Check against the original PDF.')
                if placeholder:
                    warnings.append(f'Page {page_no}: {c} uses a generic sales/reference serial; do not treat it as an actual equipment serial.')
                if row['unit']==0:
                    warnings.append(f'Page {page_no}: {c} was invoiced at £0.00 but may still require maintenance cover; do not use £0 as RRP.')
                # Qty and serials remain grouped in one source row, just like Schedule 3.
                assets.append({**common,'source_sheet':f'Invoice page {page_no}',
                               'model':row['code'].split('-')[0],'make':'',
                               'serial':', '.join(serials),'site':site,
                               'original_qty':str(row['qty']),
                               'invoice_ref':invoice_no,
                               'source_invoice_date':date,
                               'console':'',
                               'identification_evidence':'Invoice purchase SKU and description; verify maintenance configuration'})
        if any(a['product_group'].casefold() in ('pulse accessories','origin freeweight equipment') for a in assets):
            warnings.append('Some imported free weights, sets, and accessories may not require maintenance cover. Confirm which items should be included before quotation approval.')
        if not assets:
            raise ValueError('No priced or zero-value equipment stock-code rows found. This may be a scan or an unsupported invoice format; manual review is needed.')
        # Repeated catalogue/sales add-ons are preserved in the original PDF.
        # Never interpret invoice annotations as additional maintenance machines.
        return {
            'invoice':{'invoice_no':invoice_no,'date':date,'customer':customer,
                       'site':site,'billing_address':'\n'.join(billed),
                       'delivery_address':'\n'.join(delivered),'account_ref':account,
                       'customer_ref':order,'pages':len(doc)},
            'assets':assets,'excluded':excluded,'unstructured_review':unstructured,'warnings':warnings,
            'report':{'source_rows':len(all_rows),'equipment_lines':len(assets),
                      'equipment_units':sum(x['qty'] for x in assets),
                      'non_equipment_rows':len(excluded), 'unstructured_review_rows':len(unstructured),
                      'zero_sale_equipment_lines':sum(1 for x in assets if x['invoice_unit_sale_price']=='0.00'),
                      'serial_count':sum(len(x['serials']) for x in assets),
                      'invoice_sales_prices_used_as_rrp':False},
            'content_sha256':hashlib.sha256(data).hexdigest(),
        }
    finally:
        doc.close()
