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
    match=exact_config_from_description(asset)
    if match:return {**match,'confidence':'exact_source_configuration','rate_basis':'source_config'}
    # The model-AAA reference for simple strength machines was explicitly
    # requested as a draft baseline; it is never an assertion of true SKU.
    g=guide(asset)
    std=g.get('standard_reference') if g else None
    if not std:return None
    return {'model':g['model'],'rrp':std['rrp'],'reference_sku':std['example_sku'],
            'source_variants':1,'reference_name':str(asset.get('name') or ''),
            'console_label':'Unconfirmed','source':g['source'],
            'confidence':'standard_model_assumption','rate_basis':'provisional_standard'}
