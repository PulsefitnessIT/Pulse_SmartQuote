"""Explainable product candidates for ambiguous customer asset records.

This module is intentionally a *review aid*. A model, serial prefix, historical
alias or description must NEVER silently become a confirmed SKU/RRP. Operator
selection is still made through the existing source-aware /resolve endpoint.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter

MODEL = re.compile(r'^([0-9]{3}[A-Z])(?:[-./ ]([0-9]{1,2}))?$', re.I)
NOISE = {'machine', 'gym', 'fitness', 'pulse', 'equipment', 'original',
         'old', 'club', 'line', 'with', 'and', 'black', 'sand', 'the', 'a',
         'in', 'for', 'of', 'series', 'version', 'model'}
SUBS = {'running':'treadmill', 'run':'treadmill', 'cross':'elliptical',
        'cross-trainer':'elliptical', 'spin':'cycle', 'bike':'cycle',
        'spinning':'cycle', 'rowing':'rower', 'r-cycle':'recumbent',
        'upright':'upright', 'stepper':'stepmill', 'skierg':'ski'}


def family_code(text):
    """Keep an explicitly suffixed legacy variant distinct from a base model."""
    value = str(text or '').strip().upper()
    result = MODEL.fullmatch(value)
    return (result.group(1), result.group(2) is not None) if result else ('', False)


def tokens(value):
    clean = re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).split()
    return {SUBS.get(w, w) for w in clean if w not in NOISE and len(w)>1}


def _score(asset, record):
    source_name = str(asset.get('name') or '')
    item_name = str(record.get('name') or '')
    a = tokens(source_name)
    b = tokens(item_name)
    overlap = len(a & b) / max(len(a), 1) if a else 0
    sequence = difflib.SequenceMatcher(None, ' '.join(sorted(a)), ' '.join(sorted(b))).ratio()
    return round(overlap * 35 + sequence * 10, 2)


def suggest(asset, by_model, all_skus, catalogue, option_func, limit=10):
    """Rank *catalogue candidates*, returning no independently approved prices.

    Exact product SKU candidate(s) always outrank model-family suggestions.
    Model-variant suffixes are explicitly flagged and never auto-confirmed.
    """
    model = str(asset.get('model') or '').strip().upper()
    code = str(asset.get('code') or '').strip().upper()
    base, variant = family_code(model)
    if not base and code:
        base, variant = family_code(code)
    evidence = []
    if variant:
        evidence.append(f'Source model {model or code} includes a variant suffix; it may not be equivalent to {base}.')
    if not base and model:
        # Only an actual model field can be interpreted as a product family;
        # never guess a SKU from a serial number alone.
        match = re.search(r'\b([0-9]{3}[A-Z])\b', model)
        if match:
            base = match.group(1)
    direct = all_skus.get(code, []) if code else []
    candidates = []
    for raw in direct:
        candidates.append((160, raw, 'Exact catalogue item code'))
    if base:
        for raw in catalogue:
            if str(raw.get('model') or '').upper() != base:
                continue
            if code and code == str(raw.get('sku') or '').upper():
                continue
            candidates.append((75 + _score(asset, raw), raw,
                               'Same model family, exact configuration not established'))
    else:
        # No known model: description search is strictly advisory and must
        # beat a meaningful token-overlap threshold to avoid random products.
        for raw in catalogue:
            score = _score(asset, raw)
            if score < 24:
                continue
            candidates.append((score, raw, 'Description similarity only'))
    chosen = []
    seen = set()
    candidates.sort(key=lambda item: (-item[0], item[1].get('sku',''), item[1].get('name','')))
    for score, raw, why in candidates:
        sku = str(raw.get('sku') or '').upper()
        if sku in seen:
            continue
        seen.add(sku)
        current = option_func(raw)
        console = str(asset.get('console') or '').strip().casefold()
        actual_console = str(current.get('console') or '').strip().casefold()
        text_console = str(current.get('console_display') or '').strip().casefold()
        contradictions = []
        if console and console != actual_console and console != text_console:
            contradictions.append('Console needs independent confirmation')
        if sku in all_skus and len(all_skus[sku]) > 1:
            contradictions.append('Duplicate SKU: data-owner correction required')
        if variant:
            contradictions.append('Legacy model suffix: verify physical variant')
        if current.get('eligible') != 'Yes' or current.get('approved') not in ('Approved','Authorised'):
            contradictions.append('RRP, maintenance category or cover approval remains provisional')
        if not isinstance(current.get('rrp'), (int,float)) or current.get('rrp') <= 0:
            contradictions.append('Current reference RRP unavailable')
        chosen.append({
            'sku': sku, 'name': current.get('name',''),
            'model': current.get('model',''),
            'console': current.get('console',''),
            'console_display': current.get('console_display',''),
            'rrp': current.get('rrp'),
            'price_origin': current.get('price_origin',''),
            'service_key': current.get('service_key',''),
            'eligible': current.get('eligible',''),
            'duplicate_sku': bool(current.get('duplicate_sku')),
            'reason': why, 'review_flags': contradictions,
            'rank_score': score, 'operator_confirmation_required': True,
        })
        if len(chosen) >= limit:break
    return {
        'model_family': base, 'source_variant': model if variant else '',
        'historical_evidence_only': True, 'operator_confirmation_required': True,
        'candidates': chosen, 'warnings': evidence,
        'candidate_count_shown': len(chosen),
        'explanation': 'These are possibilities from the source catalogue, not approved substitutions. Confirm the machine SKU, console and RRP before choosing.',
    }
