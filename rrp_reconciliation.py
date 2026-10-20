"""Read-only 24-Aug-2026 source RRP reconciliation against current V10 catalogue.

No source record in this module authorises a commercial RRP, maintenance tariff,
console replacement, customer quotation or catalogue write.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import gzip
import io
import json
from functools import lru_cache
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'data' / 'rrp_2026_source.json.gz'
CURRENT_STATUS = 'SOURCE_PENDING_COMMERCIAL_APPROVAL'
_STATUS_ORDER = ('source_price_conflict', 'source_variant_conflict', 'source_rrp_missing',
                 'live_sku_conflict', 'not_in_live_catalogue', 'live_rrp_missing',
                 'rrp_difference', 'aligned')


def _money(value):
    try:
        d = Decimal(str(value or 0)).quantize(Decimal('0.01'))
        return d if d.is_finite() and d >= 0 else Decimal('0.00')
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _pounds(value):
    return float(_money(value))


def _signed_difference(left, right):
    return float((left - right).quantize(Decimal('0.01')))


def _model(code):
    return str(code or '').split('-', 1)[0].upper()


@lru_cache(maxsize=1)
def source():
    if not SOURCE.is_file():
        return {'rows': [], 'source_file': '', 'source_sha256': '', 'source_date': '', 'source_status': 'MISSING'}
    try:
        with gzip.open(SOURCE, 'rt', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError, UnicodeError):
        return {'rows': [], 'source_file': '', 'source_sha256': '', 'source_date': '', 'source_status': 'INVALID'}
    if not isinstance(data, dict) or not isinstance(data.get('rows'), list):
        return {'rows': [], 'source_file': '', 'source_sha256': '', 'source_date': '', 'source_status': 'INVALID'}
    return data


def reconcile(live_catalogue, live_duplicates=()):
    """SKU-level review, not an approval or an automated replacement mapping."""
    raw = source()
    groups = {}
    for row in raw['rows']:
        code = str(row.get('sku', '')).strip().upper()
        if not code or len(code) > 100:
            continue
        groups.setdefault(code, []).append(row)
    live = {}
    for record in live_catalogue:
        if isinstance(record, dict) and record.get('sku'):
            live[str(record['sku']).upper()] = record
    conflicted = {str(c).upper() for c in live_duplicates}
    result = []
    for code, src_rows in groups.items():
        prices = sorted({_money(row.get('rrp')) for row in src_rows if _money(row.get('rrp')) > 0})
        consoles = sorted({str(row.get('console', '')).strip() for row in src_rows})
        descriptions = {str(row.get('name', '')).strip() for row in src_rows}
        record = live.get(code)
        live_rrp = _money(record.get('rrp')) if record else Decimal('0')
        exact_variant_conflict = len(src_rows) > 1 and (len(consoles) > 1 or len(descriptions) > 1)
        if len(prices) > 1:
            status = 'source_price_conflict'
        elif exact_variant_conflict:
            status = 'source_variant_conflict'
        elif not prices:
            status = 'source_rrp_missing'
        elif code in conflicted:
            status = 'live_sku_conflict'
        elif record is None:
            status = 'not_in_live_catalogue'
        elif live_rrp == 0:
            status = 'live_rrp_missing'
        elif live_rrp != prices[0]:
            status = 'rrp_difference'
        else:
            status = 'aligned'
        result.append({
            'sku': code, 'model': _model(code), 'name': src_rows[0].get('name', ''),
            'console': consoles[0] if len(consoles) == 1 else 'CONFIGURATION CONFLICT',
            'source_rrp': _pounds(prices[0]) if len(prices) == 1 else None,
            'source_prices': [_pounds(price) for price in prices],
            'live_rrp': _pounds(live_rrp) if record else None,
            'difference_gbp': _signed_difference(prices[0], live_rrp) if len(prices) == 1 and live_rrp > 0 and record else None,
            'status': status, 'sources': [{
                'sheet': row.get('sheet', ''), 'row': row.get('row', ''),
                'column': row.get('rrp_column', ''), 'rrp': _pounds(row.get('rrp')),
                'name': row.get('name', ''), 'console': row.get('console', ''),
            } for row in src_rows],
            'current_catalogue_present': bool(record), 'needs_review': status != 'aligned',
            'commercial_approved': False,
        })
    return result


def summary(rows):
    d = source()
    counts = {key: sum(row['status'] == key for row in rows) for key in _STATUS_ORDER}
    return {'source_file': d.get('source_file'), 'source_date': d.get('source_date'),
            'source_sha256': d.get('source_sha256'), 'source_rows': len(d['rows']),
            'distinct_source_skus': len(rows), 'status_counts': counts,
            'needs_review': sum(x['needs_review'] for x in rows),
            'conflicting_source_skus': counts['source_price_conflict'] + counts['source_variant_conflict'],
            'commercial_approved': False, 'write_enabled': False,
            'notice': 'Internal source-RRP evidence only. Never auto-copy these RRPs into approved catalogue or quote pricing.'}


def search(rows, query='', status='', offset=0, limit=40):
    query = str(query or '').strip().casefold()[:120]
    status = str(status or '').strip()
    if status and status not in _STATUS_ORDER and status != 'needs_review':
        raise ValueError('Unknown review filter')
    filtered = [x for x in rows if (not status or (x['needs_review'] if status == 'needs_review' else x['status'] == status))
                and (not query or query in (x['sku'] + ' ' + x['model'] + ' ' + x['name'] + ' ' + x['console']).casefold())]
    filtered.sort(key=lambda x: (_STATUS_ORDER.index(x['status']), x['sku']))
    offset = min(max(0, int(offset)), 100000)
    limit = min(max(1, int(limit)), 100)
    return {'total': len(filtered), 'offset': offset, 'items': filtered[offset:offset + limit],
            'source_approved': False, 'automatic_price_updates': False}


def family(rows, model, limit=70):
    model = str(model or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{2,16}', model):
        raise ValueError('Enter a valid equipment model family.')
    all_variants = [x for x in rows if x['model'] == model]
    safe = [x['source_rrp'] for x in all_variants if x['source_rrp'] is not None and x['status'] not in ('source_price_conflict','source_variant_conflict')]
    return {'model': model, 'total': len(all_variants), 'items': all_variants[:max(1,min(100,int(limit)))],
            'min_unapproved_rrp': min(safe) if safe else None,
            'max_unapproved_rrp': max(safe) if safe else None,
            'consoles': sorted({x['console'] for x in all_variants}),
            'must_confirm_exact_variant': len(all_variants) > 1,
            'pricing_basis': 'Current equivalent normally; reviewed exceptions for legacy equipment',
            'notice': 'Confirm the exact installed console and SKU. Source list RRPs are unapproved and shown for comparison only; no console inferred for an unspecified installation.'}


def export_csv(rows):
    buffer = io.StringIO(newline='')
    out = csv.writer(buffer)
    out.writerow(['SKU','Model family','Source description','Source console','Source 2026 RRP GBP',
                  'Current SmartQuote RRP GBP','Difference GBP (source - catalogue)',
                  'Review status','Source sheet / rows','Source has commercial approval'])
    def safe(value):
        s = str(value if value is not None else '')
        return "'" + s if s.lstrip().startswith(('=', '+', '-', '@', '\t')) else s
    for item in sorted(rows, key=lambda x: (_STATUS_ORDER.index(x['status']), x['sku'])):
        out.writerow([safe(item['sku']), safe(item['model']), safe(item['name']), safe(item['console']),
                      item['source_rrp'] if item['source_rrp'] is not None else '',
                      item['live_rrp'] if item['live_rrp'] is not None else '',
                      item['difference_gbp'] if item['difference_gbp'] is not None else '',
                      item['status'], safe('; '.join(str(s['sheet'])+' row '+str(s['row']) for s in item['sources'])),
                      'NO'])
    return '\ufeff' + buffer.getvalue()
