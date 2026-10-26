"""Schema correction and reversible grouping for messy maintenance asset exports.

Never infer an exact SKU/RRP from a serial number or model family. All original
source values survive in source_cells and per-unit asset registers.
"""
from __future__ import annotations
import re
from collections import OrderedDict

BAD={'', '0','0.0','NONE','N/A','NA','NULL','-','UNKNOWN'}
SKU_RE=re.compile(r'^(?:[A-Z0-9]{2,12})-(?:[A-Z]{2,6}|[A-Z]{2,5}[0-9]{0,3}|[0-9A-Z]{3,8})$',re.I)
MODEL_RE=re.compile(r'\b([0-9]{3}[A-Z](?:-[0-9])?)\b',re.I)
PF_RE=re.compile(r'^\s*(PF\s*0*\d{3,7})\s*[-–:]\s*',re.I)
CONSOLE_RE=re.compile(r'(\b(?:cirrus\s*v\s*\d|console\s*[3-9](?:\.\d)?|pm\s*[345])\b)',re.I)

def value(text):
    s=re.sub(r'\s+',' ',str(text or '')).strip()
    return '' if s.upper() in BAD else s

def clean_description(raw):
    text=value(raw)
    m=PF_RE.match(text)
    return (m.group(1).replace(' ','').upper() if m else '',text[m.end():].strip() if m else text)

def model_from(text):
    m=MODEL_RE.search(value(text).upper())
    return m.group(1) if m else ''

def normalize_asset(asset):
    """Repair misplaced SKU/empty model while preserving the source columns."""
    out=dict(asset)
    raw={k:out.get(k,'') for k in ('name','make','model','code','serial','console','site','source_row','source_sheet','original_qty','install_date','correct_serial')}
    out.setdefault('source_cells',raw)
    tag,name=clean_description(out.get('name',''))
    out['asset_tag']=out.get('asset_tag') or tag
    out['source_description']=out.get('source_description') or value(out.get('name',''))
    out['name']=name
    code=value(out.get('code','')).upper()
    make=value(out.get('make',''))
    model=value(out.get('model',''))
    original_serial=value(out.get('serial',''))
    corrected_serial=value(out.get('correct_serial',''))
    serial=corrected_serial or original_serial
    if corrected_serial and corrected_serial!=original_serial:
        out['original_serial']=original_serial
    if not code and SKU_RE.fullmatch(make):
        code=make.upper()
        make='Pulse Fitness (SKU in original Make column)'
        out['identification_evidence']='Exact stock code recovered from Make column'
    # Some exports put the SKU in the Model column, not the SKU column.
    if not code and SKU_RE.fullmatch(model):
        code=model.upper()
        out['identification_evidence']='Exact stock code recovered from Model column'
    model_hint=model_from(model) or model_from(code)
    if not model_hint:
        model_hint=model_from(name)
    if not model_hint and not code:
        model_hint=model_from(serial)  # Family only; a serial is never a priced SKU.
        if model_hint:out['identification_evidence']='Model family derived from serial prefix — console/SKU unverified'
    # Preserve descriptive model text in source_cells while using a useful family model.
    out['code']=code
    out['model']=model_hint or (model if re.fullmatch(r'[A-Z0-9-]{2,22}',model,re.I) else '')
    out['make']=make
    out['serial']=serial
    out['console']=value(out.get('console',''))
    if not out['console']:
        hint=CONSOLE_RE.search(name)
        if hint:
            out['console']=hint.group(1)
            out['console_evidence']='Description mentions a console; configuration requires verification'
    return out

def group_key(asset,price=None):
    """Never merge different site, model, SKU, console, selection or price basis."""
    def key(x):return re.sub(r'\s+',' ',str(x or '').strip()).casefold()
    sel=asset.get('selected') or {}
    description=clean_description(asset.get('name'))[1]
    # Separate explicit model variants and priced/unpriced selections.
    return (key(asset.get('site')),key(asset.get('code')),key(asset.get('model')),
            key(asset.get('console')),key(description),key(asset.get('make')),
            key(sel.get('sku')),key(sel.get('service_key')),
            key(sel.get('console')),key(asset.get('manual_annual_unit')),
            key(asset.get('excluded')),key(asset.get('exclusion_reason')),key(asset.get('contract_note')),
            key((price or {}).get('unit')),key((price or {}).get('basis')),
            key(asset.get('qty_issue')),key(asset.get('cover_start')))

def grouped_assets(assets,price_by_id=None):
    """Make display groups only; original list/individual IDs remain intact."""
    price_by_id=price_by_id or {}
    groups=OrderedDict()
    for asset in assets:
        price=price_by_id.get(asset.get('id'))
        key=group_key(asset,price)
        if key not in groups:
            groups[key]={'id':asset.get('id'),'representative':asset,'ids':[],
                         'qty':0,'source_rows':[],'serials':[],'assets':[],
                         'price':price,'source_sheets':set()}
        group=groups[key]
        group['ids'].append(asset.get('id'))
        group['qty']+=max(1,int(asset.get('qty') or 1))
        group['source_rows'].append(asset.get('source_row'))
        if asset.get('source_sheet'):group['source_sheets'].add(asset['source_sheet'])
        if asset.get('serial'):group['serials'].append(str(asset['serial']))
        group['assets'].append({'id':asset.get('id'),'source_row':asset.get('source_row'),
                    'source_sheet':asset.get('source_sheet'),'serial':asset.get('serial',''),
                    'asset_tag':asset.get('asset_tag',''), 'original_qty':asset.get('original_qty',''),
                    'qty':asset.get('qty',1), 'source_cells':asset.get('source_cells',{}),
                    'source_description':asset.get('source_description',asset.get('name','')),
                    'install_date':asset.get('install_date',''),
                    'original_serial':asset.get('original_serial',''),
                    'source_raw_columns':asset.get('source_raw_columns',[])})
    result=[]
    for g in groups.values():
        g['source_sheets']=sorted(g['source_sheets'])
        # No price synthesis. Source quantity determines only the group line sum.
        if g['price']:
            g['price']={**g['price'],'qty':g['qty'],
                        'annual':round(float(g['price']['unit'])*g['qty'],2)}
        result.append(g)
    return result
