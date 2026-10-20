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
