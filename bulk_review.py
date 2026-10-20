"""Auditable, two-stage multi-group catalogue resolution for busy coordinators.

The first step is read-only. An explicit second action applies only operator
confirmed catalogue SKUs, never guessed model families, RRPs or prices.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

import engine as eng
from asset_intelligence import grouped_assets

MAX_ACTIONS = 20
MAX_GROUP_ROWS = 1200


class ReviewError(ValueError):
    """A staff-actionable validation failure; caller returns HTTP 4xx."""


def fingerprint(quote, catalogue_revision):
    """Optimistic lock: all source, review and commercial quote inputs are included."""
    value = {'assets': quote.get('assets', []), 'tier': quote.get('tier'),
             'discount': quote.get('discount'), 'level': quote.get('level'),
             'catalogue_revision': catalogue_revision}
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str,
                         separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _groups(quote):
    prices = {x['id']: x.get('price') for x in eng.calc_quote(quote)['lines']}
    return grouped_assets(quote.get('assets', []), prices)


def _bulk_eligibility(asset, candidate):
    """Only same-family, console-consistent priced suggestions can use batch mode."""
    source = str(asset.get('model') or '').upper()
    if not source:
        source = str(asset.get('code') or '').upper()
    original_family = re.match(r'^(\d{3}[A-Z])(?:$|[- ])', source)
    if not original_family:
        return False, 'No reliable original model family: inspect the machine individually'
    suggested_model = str(candidate.get('model') or '').upper()
    if original_family and suggested_model != original_family.group(1):
        return False, 'Different machine family: resolve this replacement individually'
    console = str(asset.get('console') or '').strip().casefold()
    offered = {str(candidate.get(k) or '').strip().casefold()
               for k in ('console', 'console_display')}
    if console and console not in offered:
        return False, 'Imported console differs: check physical configuration individually'
    if not isinstance(candidate.get('rrp'), (float, int)) or candidate['rrp'] <= 0:
        return False, 'Current RRP unavailable: pricing manager must reconcile it'
    return True, ''


def _actionable(g):
    return all(not a.get('excluded') and not a.get('selected')
               and a.get('manual_annual_unit') in (None, '')
               and not a.get('qty_issue') and not a.get('import_reviewed')
               for a in (g['representative'],)) and not g.get('price')


def queue(quote, revision, offset=0, limit=30):
    offset = max(0, min(int(offset), 100000))
    limit = max(1, min(int(limit), 40))
    groups = sorted((g for g in _groups(quote) if _actionable(g)),
                    key=lambda g: (-g['qty'], str(g['representative'].get('model') or ''),
                                   str(g['representative'].get('name') or '')))
    rows = []
    for g in groups[offset:offset + limit]:
        asset = g['representative']
        reviewed = eng.review_candidates(asset, limit=10)
        # Catalogues can contain duplicate item codes or legacy-only records;
        # they must never be offered as one-click bulk assignments.
        proposals = []
        for c in reviewed.get('candidates', []):
            sku = str(c.get('sku') or '').upper().strip()
            if not sku or sku in eng.DUPLICATE_CODES or sku not in eng.BY_SKU:
                continue
            if sku in [p['sku'] for p in proposals]:
                continue
            allow, why_not = _bulk_eligibility(asset, c)
            proposals.append({**{k: c.get(k) for k in
                  ('sku', 'name', 'model', 'console', 'console_display', 'rrp',
                   'reason', 'review_flags', 'price_origin', 'eligible')},
                    'batch_selectable': allow, 'block_reason': why_not})
            if len(proposals) == 6:
                break
        rows.append({'asset_id': asset['id'], 'description': asset.get('source_description')
                     or asset.get('name') or 'Unlabelled equipment',
                     'source_code': asset.get('code') or asset.get('model') or '',
                     'source_console': asset.get('console') or '',
                     'site': asset.get('site') or '',
                     'rows': len(g['ids']), 'units': g['qty'],
                     'source_rows': g['source_rows'], 'serials': g['serials'],
                     'variant_notice': reviewed.get('source_variant') or '',
                     'candidates': proposals, 'can_bulk_review': any(c['batch_selectable'] for c in proposals)})
    return {'token': fingerprint(quote, revision), 'total_groups': len(groups),
            'offset': offset, 'shown': len(rows), 'remaining':
            max(0, len(groups) - offset - len(rows)), 'groups': rows,
            'message': 'Suggestions require physical SKU and console verification. '
                       'A saved identity does not approve the catalogue RRP or commercial tariff.'}


def prepare(quote, revision, actions, expected_token):
    """Validate an entire batch before any mutation; return new quote and summary."""
    if not isinstance(expected_token, str) or expected_token != fingerprint(quote, revision):
        raise ReviewError('The quotation or catalogue changed. Refresh the workbench and preview again.')
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
        raise ReviewError(f'Select 1 to {MAX_ACTIONS} equipment groups to review at once.')
    initial = {g['id']: g for g in _groups(quote) if _actionable(g)}
    staged = copy.deepcopy(quote)
    by_id = {a.get('id'): a for a in staged['assets']}
    seen = set()
    affected = set()
    details = []
    for action in actions:
        if not isinstance(action, dict):
            raise ReviewError('Each review must specify an equipment group and catalogue SKU.')
        aid = action.get('asset_id')
        sku = str(action.get('sku') or '').upper().strip()
        evidence = str(action.get('evidence') or '').strip()
        if not isinstance(aid, str) or aid not in initial or aid in seen:
            raise ReviewError('This equipment group is no longer available or was included twice. Refresh the workbench.')
        if action.get('verified') is not True or len(evidence) < 12 or len(evidence) > 400:
            raise ReviewError('Verify each exact SKU and console, and record at least 12 characters of source evidence.')
        if sku in eng.DUPLICATE_CODES or sku not in eng.BY_SKU:
            raise ReviewError('The chosen SKU is unavailable or ambiguous in the current catalogue.')
        group = initial[aid]
        if len(group['ids']) > MAX_GROUP_ROWS or len(affected) + len(group['ids']) > MAX_GROUP_ROWS:
            raise ReviewError('The requested batch is too large to verify safely in one action.')
        possible = eng.review_candidates(group['representative'], limit=20)
        allowed = {str(c.get('sku') or '').upper() for c in possible.get('candidates', [])
                   if c.get('sku') and not c.get('duplicate_sku')}
        if sku not in allowed:
            raise ReviewError('The selected SKU is not in this group’s reviewed candidate set. Use the individual equipment editor for an unusual match.')
        reviewed_candidate = next(c for c in possible['candidates']
                                   if str(c.get('sku') or '').upper() == sku)
        eligible, blocked = _bulk_eligibility(group['representative'], reviewed_candidate)
        if not eligible:
            raise ReviewError(blocked + '. Use the individual equipment editor.')
        chosen = eng.live_catalogue_option(eng.BY_SKU[sku], 'Explicit bulk staff review')
        if chosen.get('duplicate_sku'):
            raise ReviewError('Conflicting SKU requires data-owner correction.')
        new_prices = 0
        for id_ in group['ids']:
            a = by_id[id_]
            if a.get('selected') or a.get('excluded') or a.get('qty_issue'):
                raise ReviewError('An equipment row was modified during the review. Refresh and retry.')
            a['imported_code'] = a.get('imported_code') or a.get('code', '')
            a['imported_name'] = a.get('imported_name') or a.get('name', '')
            a['selected'] = dict(chosen)
            a['candidates'] = []
            a['issues'] = eng.selection_issues(chosen)
            a['match_type'] = 'Staff-confirmed in bulk workbench'
            a['match_confidence'] = 95
            a['review_evidence'] = evidence
            if a.get('import_batch_id'):
                a['import_reviewed'] = True
            if chosen.get('sku'):
                a['code'] = chosen['sku']
            if chosen.get('model'):
                a['model'] = chosen['model']
            if chosen.get('console_status') == 'source' and chosen.get('console'):
                a['console'] = chosen['console']
            if eng.price_line(a, 'Standard', staged.get('tier', 'Gold'),
                              staged.get('discount', 0)):
                new_prices += 1
            affected.add(id_)
        seen.add(aid)
        flags = next((c.get('review_flags', []) for c in possible['candidates']
                      if str(c.get('sku') or '').upper() == sku), [])
        details.append({'asset_id': aid, 'sku': sku, 'description':
                        group['representative'].get('name', ''), 'site':
                        group['representative'].get('site', ''), 'units': group['qty'],
                        'source_rows': len(group['ids']), 'draft_priced_assets': new_prices,
                        'warnings': flags, 'evidence': evidence})
    staged['pricing_approved'] = False
    staged['line_reviews_approved'] = False
    staged['approver'] = ''
    staged['approval_note'] = 'Equipment identities changed; all commercial pricing requires revalidation.'
    return staged, {'groups': len(details), 'source_rows': len(affected),
                    'units': sum(d['units'] for d in details),
                    'draft_priced_assets': sum(d['draft_priced_assets'] for d in details),
                    'changes': details,
                    'commercially_approved': False,
                    'message': 'Group selections are operator-confirmed identities, not approval of current RRP, tariff or customer issue.'}
