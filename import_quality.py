"""Read-only import preflight for staff. Never creates catalogue prices or edits a quote.

The preview and commit use the same import parser. Imported source rows, original
columns, serials and source sheet metadata are retained by the normal importer.
"""
from __future__ import annotations
from collections import Counter
from asset_intelligence import grouped_assets
from engine import match_asset, price_line


def preview(parsed, quote):
    proposed = []
    prices = {}
    findings = Counter()
    for index, original in enumerate(parsed['assets'], 1):
        asset = match_asset({**original, 'id': f'preview_{index}'})
        proposed.append(asset)
        if asset.get('qty_issue'):
            findings['quantity_checks'] += 1
        if not asset.get('code') and not asset.get('model'):
            findings['identity_checks'] += 1
        if asset.get('selected'):
            findings['identified'] += 1
        quoted = price_line(asset, 'Standard', quote.get('tier', 'Gold'), quote.get('discount', 0))
        if quoted:
            prices[asset['id']] = quoted
            findings['draft_priced'] += 1
    groups = grouped_assets(proposed, prices)
    existing = quote.get('assets', [])
    sheet_list = [
        {'sheet': s.get('sheet', ''), 'rows_found': s.get('rows', 0),
         'assets_found': s.get('added', 0), 'headings_recognised': bool(s.get('detected'))}
        for s in parsed['sheets']
    ]
    return {
        'filename': parsed.get('file', ''),
        'source_rows': len(proposed),
        'physical_units': sum(a.get('qty', 1) for a in proposed),
        'equipment_groups': len(groups),
        'identified_rows': findings['identified'],
        'draft_priced_rows': findings['draft_priced'],
        'quantity_checks': findings['quantity_checks'],
        'identity_checks': findings['identity_checks'],
        'existing_quote_rows': len(existing),
        'sheets': sheet_list,
        'warnings': list(parsed['warnings'][:30]),
        'more_warnings': max(0, len(parsed['warnings']) - 30),
        'sample_groups': [
            {'description': (g['representative'].get('source_description')
                             or g['representative'].get('name') or 'Unlabelled equipment'),
             'code': (g['representative'].get('code')
                      or g['representative'].get('model') or ''),
             'units': g['qty'], 'source_rows': len(g['ids']),
             'draft_priced': bool(g.get('price'))}
            for g in groups[:8]
        ],
        'notice': ('Import preview only. Identification and draft-priced counts are not '
                   'authorised prices or proof of catalogue completeness. Review the '
                   'quotation after import; no customer records have been modified.')
    }
