"""Transparent historic-model renewal reference pricing.

No historical machine code is silently rewritten as a different modern SKU.
This module constructs *indicative* service charges from verifiable current
catalogue RRPs, while retaining the original machine name, variant and serials.
The existing published source tariff supplies the rate, not this module.
"""
from __future__ import annotations
import re
from decimal import Decimal

# These are semantic suggestions, not manufacturer-confirmed supersessions.
# Exact old identity remains on the customer line; the source current family
# is recorded alongside the RRP used for the indicative estimate.
HISTORIC_REFERENCE = {
 '751H':('751G','Adjustable incline bench'),
 '875H':('875G','Counterbalanced Smith Machine including bench'),
 '650H':('650G','Adjustable abdominal decline bench'),
 '785H':('785G','Preacher curl bench'),
 '290E5':('290E','Concept2 rower Model E / PM5'),
 'SKIERG5FLOOR':('205C','Concept2 SkiErg PM5 floor mounted'),
 # A WattBike Pro and Air-Pro are NOT validated as equivalent. Keep TBC.
}

def usable_rrp(obj):
    try:
        n=Decimal(str(obj.get('rrp')))
        return n if n.is_finite() and n > 0 else None
    except (ValueError,TypeError,ArithmeticError):
        return None

def family_reference(asset,catalogue,duplicate_codes,rate_group_fn):
    """Build price from a traceable modern RRP family; never identify exact SKU.

    Returns None if no reliable family price exists. Cross-generation choices
    cannot be called a verified equivalent and carry explicit risk annotation.
    """
    if not asset.get('prior_contract_ref'):
        return None
    code=str(asset.get('code') or '').strip().upper()
    description=str(asset.get('name') or '')
    if not code:
        return None
    reference=code
    method='Model family reference'
    risk='Model variant not specified by historic agreement'
    if code in HISTORIC_REFERENCE:
        reference,_source_description=HISTORIC_REFERENCE[code]
        method='Historical-to-current product-family comparison (unverified supersession)'
        risk='Old and current model codes differ; verify physical equipment against the product family'
    elif re.fullmatch(r'([0-9]{3}[A-Z])-6\.0',code):
        reference=code.split('-')[0]
        method='Historic 6.0 console-generation proxy (NOT an exact equivalent)'
        risk='19-inch Fusion 6.0 console has no verified matching current SKU; use provisional current-family RRP only'
    elif not re.fullmatch(r'[0-9]{3}[A-Z]',code):
        return None
    candidates=[p for p in catalogue if (str(p.get('model') or '').upper()==reference or str(p.get('sku') or '').upper().startswith(reference+'-')) and usable_rrp(p)
                and str(p.get('sku') or '').upper() not in duplicate_codes]
    if not candidates:return None
    # An agreement can include different physical products in one model family.
    # Filter only when a clear distinguishing term is in the old description.
    desc=description.lower()
    if code=='875H':
        matching=[p for p in candidates if re.search(r'(inc\.?\s*adjustable incline bench|incl\.?\s*bench|including bench)',p['name'].lower())]
        if matching:candidates=matching
    if code=='SKIERG5FLOOR':
        matching=[p for p in candidates if 'floor mounted' in p['name'].lower()]
        if matching:candidates=matching
    if code=='866H' and 'platform' not in desc:
        matching=[p for p in candidates if 'platform' not in p['name'].lower()]
        if matching:candidates=matching
    if code=='290E5':
        matching=[p for p in candidates if 'model e' in p['name'].lower() and 'pm5' in p['name'].lower()]
        if matching:candidates=matching
    if 'with console' in desc and not code.endswith('-6.0'):
        matching=[p for p in candidates if 'console' in p['name'].lower() or 'touchscreen' in p['name'].lower()]
        if matching:
            candidates=matching
        else:
            risk+='; current family has no independently identified console-compatible variant'
    if not re.search(r'\binclusive\b|\bifi\b',desc):
        standard=[p for p in candidates if not re.search(r'\binclusive\b|\bifi\b',p['name'],re.I)]
        if standard:candidates=standard
    if not candidates:return None
    # Using the highest RRP in the relevant family deliberately avoids treating
    # the cheapest trim as the confirmed historic replacement. It is NOT an
    # independently authorised price and can exceed the eventual correct rate.
    best=max(candidates,key=lambda p:(usable_rrp(p),p['sku']))
    min_rrp=min(usable_rrp(p) for p in candidates)
    max_rrp=usable_rrp(best)
    group,basis,confidence=rate_group_fn(best)
    if group=='Manual Review':return None
    return {
        'sku':'','name':description,'model':code,
        'console':asset.get('console') or 'Not specified in original agreement',
        'console_display':asset.get('console') or 'Not specified in original agreement',
        'console_status':'source' if asset.get('console') else 'unknown',
        'rrp':float(max_rrp),'rrp_low':float(min_rrp),'rrp_high':float(max_rrp),
        'service_key':'','rate_group':group,'eligible':'Estimate - approval required',
        'approved':'Not approved - family reference only',
        'match':'Historic machine code - family only',
        'reason':method,'price_origin':'historic-family-estimate',
        'pricing_rule':f'{method}; {basis}; upper RRP of compatible catalogue variants',
        'estimate_confidence':'Low' if '6.0' in code or reference!=code else 'Medium',
        'reference_model':reference,'reference_sku':best['sku'],
        'reference_variants':len(candidates),
        'reference_range':f'£{min_rrp:,.2f} to £{max_rrp:,.2f}',
        'reference_warning':risk,
        'legacy_comparison_only':True,
    }
