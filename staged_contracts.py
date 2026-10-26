"""Staged contract quote arithmetic. Prices remain sourced from the ordinary tariff engine.

Annualised catalogue prices are unchanged. A planned schedule is a dated,
quoted contract value, not an invoice, activation, or amendment to Sicon.
"""
from __future__ import annotations
import calendar
import datetime as dt
import re
from decimal import Decimal, ROUND_HALF_UP

ISO = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def parse_date(value):
    if not isinstance(value, str) or not ISO.fullmatch(value):
        raise ValueError('Enter a valid date in YYYY-MM-DD format.')
    return dt.date.fromisoformat(value)


def valid_contract(start, end):
    begin, finish = parse_date(start), parse_date(end)
    if finish <= begin:
        raise ValueError('Contract end must be later than its start date.')
    if finish.year - begin.year > 5 or (finish - begin).days > 366 * 5:
        raise ValueError('Staged contracts can cover up to five years.')
    return begin, finish


def money_decimal(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def pro_rata(annual, begin, finish):
    """Inclusive dates, ACT/ACT by calendar year; round once per equipment line."""
    if finish < begin:
        return 0.0
    annual = Decimal(str(annual))
    amount = Decimal('0')
    for year in range(begin.year, finish.year + 1):
        first = max(begin, dt.date(year, 1, 1))
        last = min(finish, dt.date(year, 12, 31))
        covered_days = (last - first).days + 1
        if covered_days > 0:
            amount += annual * Decimal(covered_days) / Decimal(366 if calendar.isleap(year) else 365)
    return money_decimal(amount)


def stage_summary(quote, prices):
    """Return a dated, line-by-line plan, or disabled when no contract dates entered."""
    start, end = quote.get('contract_start') or '', quote.get('contract_end') or ''
    if not start and not end:
        return {'enabled': False, 'issues': [], 'lines': [], 'stages': [], 'total': None}
    if not start or not end:
        return {'enabled': True, 'issues': ['Enter both the contract start and end dates.'], 'lines': [], 'stages': [], 'total': None}
    try:
        begin, finish = valid_contract(start, end)
    except ValueError as exc:
        return {'enabled': True, 'issues': [str(exc)], 'lines': [], 'stages': [], 'total': None}
    issues, lines = [], []
    buckets = {}
    for asset in quote.get('assets', []):
        if asset.get('excluded'):
            continue
        label = asset.get('code') or asset.get('model') or asset.get('name') or 'Equipment'
        raw = asset.get('cover_start') or start
        try:
            coverage = parse_date(raw)
            if not begin <= coverage <= finish:
                raise ValueError('The equipment start date must fall within the contract period.')
        except ValueError as exc:
            issues.append(f'{label}: {exc}')
            continue
        price = prices.get(asset.get('id'))
        if not price:
            continue  # Existing engine separately blocks unpriced equipment.
        period = pro_rata(price['annual'], coverage, finish)
        row = {'id': asset.get('id'), 'sku': asset.get('code') or asset.get('model') or '',
               'cover_start': coverage.isoformat(), 'cover_end': end,
               'annual': price['annual'], 'period_charge': period,
               'days': (finish - coverage).days + 1}
        lines.append(row)
        bucket = buckets.setdefault(row['cover_start'], {'start': row['cover_start'], 'count': 0, 'amount': Decimal('0')})
        bucket['count'] += int(asset.get('qty', 1))
        bucket['amount'] += Decimal(str(period))
    stages = [{**value, 'amount': money_decimal(value['amount'])} for _, value in sorted(buckets.items())]
    return {'enabled': True, 'start': start, 'end': end, 'issues': issues,
            'lines': lines, 'stages': stages,
            'total': money_decimal(sum((Decimal(str(row['period_charge'])) for row in lines), Decimal('0')))}


def machine_sort_key(asset):
    """Natural ascending numeric/alphanumeric SKU ordering, unknown codes last."""
    source = asset.get('representative', asset)
    code = str(source.get('code') or source.get('model') or (source.get('selected') or {}).get('sku') or '').strip().upper()
    fragments = re.split(r'(\d+)', code)
    chunks = tuple((0, int(x)) if x.isdigit() else (1, x) for x in fragments if x)
    return (not bool(code), chunks, code, str(source.get('name') or '').casefold(), str(source.get('id') or ''))
