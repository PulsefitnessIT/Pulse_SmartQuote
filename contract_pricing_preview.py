"""Conservative draft-price previews for unselected equipment.

Only uses the August 2026 master evidence; does not select an actual SKU,
change a quote, or approve a maintenance tariff. An exact configuration must
have sufficiently distinctive attributes and a single source RRP.
"""
from __future__ import annotations
from decimal import Decimal
import re
from staff_price_guides import _model, _index, _clean, guide


def features(text):
    val=_clean(text).lower()
    sizes=tuple(s for s in ('7', '10.1', '18.5', '19') if re.search(r'(?<!\d)'+re.escape(s)+r'\s*(?:[\"”]|-?\s*inch)',val))
    return {
        'size': sizes,
        'premium': bool(re.search(r'\bpremium\b',val)),
        'club': bool(re.search(r'\bclub\s+line\b',val)),
        'classic': bool(re.search(r'\bclassic\b',val)),
        'touchscreen': 'touchscreen' in val or 'touch screen' in val,
        'tactile': 'tactile' in val,
        'wireless': 'wireless charging' in val,
        'watch': 'watch connectivity' in val,
        'mirroring': 'content mirroring' in val,
        'egym': bool(re.search(r'\begym\b',val)),
        'ifi': bool(re.search(r'\bifi\b|\binclusive\b',val)),
        'platform': bool(re.search(r'\bplatform\b',val)),
        'illuminated': bool(re.search(r'\billuminated\b',val)),
        'fixed_stride': 'fixed stride' in val,
        '22.5kph': '22.5kph' in val or '22.5 kph' in val,
    }



def source_sku_reference(asset):
    """A unique RRP for a documented exact 2026 SKU (DRAFT, not approved)."""
    code=_clean(asset.get('code')).upper()
    model=_model(asset)
    if not re.fullmatch(r'[0-9]{3}[A-Z]-[A-Z0-9.-]{2,}',code):return None
    if not model or model not in _index() or code not in _index()[model]:return None
    make=_clean(asset.get('make')).lower()
    if any(x in make for x in ('technogym','life fitness','matrix','concept2','concept 2','wattbike','stairmaster','precor','keiser')):return None
    rows=_index()[model][code]
    prices={x['rrp'] for x in rows}
    if len(prices)!=1:return None
    original=_clean(asset.get('source_description') or asset.get('name'))
    # A bare SKU can be legacy/revised; require corroborating product/console evidence.
    if len(original)<45 or not ('console' in original.casefold() or _clean(asset.get('console'))):
        if not asset.get('invoice_ref'):return None
        # Historic invoices identify many non-console machines by exact SKU.
        # Corroborate product words; a unique current SKU RRP is DRAFT evidence.
        stop={'line','club','premium','classic','with','equipment','sand','black',
              'grey','silver','dark','steel','weight','stack','in','the','and',
              'vertical','horizontal','covered','total','stand'}
        tokens={w for w in re.findall(r'[a-z]{4,}',original.lower()) if w not in stop}
        source=' '.join(row['name'].lower() for row in rows)
        if len(tokens)<1 or len([w for w in tokens if w in source])<min(2,len(tokens)):return None
    recorded=features(original)
    source_features=[features(x['name']) for x in rows]
    for size in recorded['size']:
        if not all(size in f['size'] for f in source_features):return None
    if recorded['touchscreen'] and not all(f['touchscreen'] for f in source_features):return None
    if recorded['tactile'] and not all(f['tactile'] for f in source_features):return None
    if recorded['ifi'] and not all(f['ifi'] for f in source_features):return None
    explicit=features(asset.get('console'))
    for size in explicit['size']:
        if not all(size in f['size'] for f in source_features):return None
    if explicit['touchscreen'] and not all(f['touchscreen'] for f in source_features):return None
    if explicit['tactile'] and not all(f['tactile'] for f in source_features):return None
    chosen=rows[0]
    return {'model':model,'rrp':float(next(iter(prices))),
      'reference_sku':code,'reference_name':chosen['name'],
      'source_variants':len(rows),'console_label':chosen['console_label'],
      'source':'Full Master Price List 24-08-2026.xlsx',
      'basis':'Exact stock code in dated 2026 RRP source; provisional tariff and approval required',
      'confidence':'exact_source_sku','rate_basis':'source_exact_sku'}


def strength_spec_reference(asset):
    """A numerical but unapproved guide when a rich legacy specification matches one price."""
    model=_model(asset)
    if not model or model not in _index():return None
    code=_clean(asset.get('code')).upper()
    if not re.fullmatch(r'[0-9]{3}H(?:-[A-Z0-9.-]+)?',code or model):return None
    make=_clean(asset.get('make')).lower()
    if any(x in make for x in ('technogym','life fitness','matrix','concept2','stairmaster','precor','keiser')):return None
    desc=_clean(asset.get('source_description') or asset.get('name')).lower()
    feat=features(desc)
    if not(feat['premium'] and feat['size']==('10.1',) and feat['touchscreen']):return None
    # The premium upholstery and machine configuration are material to RRP.
    required=('carbon fibre','red stitching','sand black','weight stack')
    if not all(term in desc for term in required):return None
    candidates=[]
    for sku,rows in _index()[model].items():
        rrps={r['rrp'] for r in rows}
        if len(rrps)!=1:continue
        for row in rows:
            name=row['name'].lower();f=features(name)
            if f['premium'] and f['size']==('10.1',) and f['touchscreen'] and all(term in name for term in required):
                candidates.append(row)
    rrps={r['rrp'] for r in candidates}
    if len(rrps)!=1:return None
    chosen=sorted(candidates,key=lambda x:x['sku'])[0]
    return {'model':model,'rrp':float(next(iter(rrps))),
      'reference_sku':chosen['sku'],'source_variants':len({r['sku'] for r in candidates}),
      'reference_name':chosen['name'],'console_label':chosen['console_label'],
      'source':'Full Master Price List 24-08-2026.xlsx',
      'basis':'Matching premium 10.1-inch strength console specification, one source RRP; installed legacy SKU and connectivity not confirmed',
      'confidence':'unique_strength_spec_price','rate_basis':'source_spec_equivalent'}

def exact_config_from_description(asset):
    """Unique-price *draft* RRP if an imported spec identifies one config.

    Reject bare family names, external manufacturers, contradictory feature
    sets, duplicate-source conflicts and descriptions with multiple RRPs.
    Colour and upholstery can vary only when a source configuration price is
    identical. Source SKU remains a reference, never the installed identity.
    """
    text=_clean(asset.get('source_description') or asset.get('name'))
    model=_model(asset)
    if len(text)<37 or not model or model not in _index():return None
    make=_clean(asset.get('make')).lower()
    if any(v in make for v in ('stairmaster','technogym','life fitness','matrix','concept2','concept 2','wattbike','precor','keiser')):return None
    feat=features(text)
    distinctive=sum(bool(feat[k]) for k in ('premium','club','classic','wireless','watch','mirroring','egym','ifi','illuminated','fixed_stride','tactile','touchscreen','platform'))
    if distinctive<2 or not (feat['size'] or feat['ifi'] or feat['platform'] or feat['fixed_stride']):return None
    candidates=[]
    for sku,rows in _index()[model].items():
        unique_rrps={row['rrp'] for row in rows}
        if len(unique_rrps)!=1:continue
        row=rows[0]
        if features(row.get('name'))==feat:
            candidates.append(row)
    rrps={c['rrp'] for c in candidates}
    if len(rrps)!=1:return None
    rrp=float(next(iter(rrps)))
    chosen=sorted(candidates,key=lambda r:r['sku'])[0]
    return {'model':model,'rrp':rrp,'reference_sku':chosen['sku'],
            'source_variants':len(candidates),'reference_name':chosen['name'],
            'console_label':chosen['console_label'],'source':'Full Master Price List 24-08-2026.xlsx',
            'basis':'Full configuration features, one source RRP — tariff provisional'}


def draft_reference(asset):
    match=source_sku_reference(asset)
    if match:return match
    match=exact_config_from_description(asset)
    if match:return {**match,'confidence':'exact_source_configuration','rate_basis':'source_config'}
    match=strength_spec_reference(asset)
    if match:return match
    # The model-AAA reference for simple strength machines was explicitly
    # requested as a draft baseline; it is never an assertion of true SKU.
    g=guide(asset)
    std=g.get('standard_reference') if g else None
    if not std:return None
    return {'model':g['model'],'rrp':std['rrp'],'reference_sku':std['example_sku'],
            'source_variants':1,'reference_name':str(asset.get('name') or ''),
            'console_label':'Unconfirmed','source':g['source'],
            'confidence':'standard_model_assumption','rate_basis':'provisional_standard'}
