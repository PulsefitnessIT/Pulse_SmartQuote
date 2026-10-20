"""Deterministically combine verified XLSX history with recovered later-year identities.

Identity evidence only: never imports RRPs or invents current-equivalent mappings.
A source workbook row is preferred to a recovered row from the same or earlier
calendar year; genuine later recovered 2025/26 data remains the latest snapshot.
Original row-by-row revision evidence is retained in an optional audit export.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import csv
import json

FORBIDDEN = {"rrp", "price", "price_pence", "annual", "monthly", "approved_rrp"}
INDEX = 'historical_catalogue_index.json'
MANIFEST = 'historical_catalogue_manifest.json'


def load(path):
    with Path(path).open(encoding='utf-8') as handle:
        return json.load(handle)


def _provenance(row):
    """Keep auditable source coordinates, not prices or quoted terms."""
    items = []
    for p in row.get('provenance', []):
        if not isinstance(p, dict):
            continue
        year = p.get('year')
        if not isinstance(year, int) or not 2020 <= year <= 2026:
            continue
        items.append({k: p[k] for k in ('year', 'revision', 'source', 'sheet', 'row') if k in p})
    return items


def _uniq(provenance):
    seen = set()
    result = []
    for p in provenance:
        key = (p.get('year'), p.get('revision'), p.get('source'), p.get('sheet'), p.get('row'))
        if key not in seen:
            seen.add(key)
            result.append(p)
    return sorted(result, key=lambda p: (p.get('year', 0), str(p.get('revision', '')), str(p.get('source', '')), int(p.get('row', 0) or 0)))


def _rev_history(provenance):
    seen = set()
    versions = []
    for p in provenance:
        key = (p['year'], str(p.get('revision') or 'unlettered').lower())
        if key not in seen:
            seen.add(key)
            versions.append(f'{key[0]}:{key[1]}')
    return versions


def reconcile(new_folder, recovered_folder, target, write_audit=True):
    new_folder, recovered_folder, target = map(Path, (new_folder, recovered_folder, target))
    new = load(new_folder / INDEX)
    earlier = load(recovered_folder / INDEX)
    new_manifest = load(new_folder / MANIFEST)
    old_manifest = load(recovered_folder / MANIFEST)
    records, old = new.get('records'), earlier.get('records')
    if not isinstance(records, dict) or not records or not isinstance(old, dict) or not old:
        raise ValueError('Both source indexes must have non-empty identity records.')
    if len(records) != new_manifest.get('unique_skus') or len(old) != old_manifest.get('unique_skus'):
        raise ValueError('At least one source manifest is inconsistent with its index.')
    if any(set(x).intersection(FORBIDDEN) or x.get('evidence_only') is not True
           for x in list(records.values()) + list(old.values())):
        raise ValueError('Historical input is not identity-only.')
    new_rows = load(new_folder / 'historical_equipment_master.json')
    if set(new_rows) != set(records):
        raise ValueError('Full XLSX provenance does not match the canonical identity index.')

    combined = {}
    audit = {}
    newer_recovered = 0
    superseded_recovered = 0
    for sku in sorted(set(records) | set(old)):
        incoming = records.get(sku)
        previous = old.get(sku)
        if incoming and previous:
            # Recovered 2025/26 snapshots take precedence over actual 2020-24.
            # If a later physical master becomes available, it takes precedence.
            use_old = int(previous.get('year', 0) or 0) > int(incoming.get('year', 0) or 0)
            selected = previous if use_old else incoming
            newer_recovered += bool(use_old)
            superseded_recovered += not use_old
        else:
            selected = incoming or previous
        selected = dict(selected)
        if incoming:
            source_rows = _provenance(new_rows[sku])
            # Do not double-count the 2020-24 data recovered from a different
            # (older) export when original physical workbooks are available.
            remaining = [p for p in _provenance(previous or {})
                         if p['year'] > int(incoming.get('year', 0) or 0)]
        else:
            source_rows = []
            remaining = _provenance(previous or {})
        full_history = _uniq(source_rows + remaining)
        if not full_history:
            full_history = [{k: selected[k] for k in ('year','source','rev') if k in selected}]
        first_year = min(p.get('year', selected.get('year', 2020)) for p in full_history)
        selected['first_seen'] = min(first_year, int(selected.get('first_seen', first_year)))
        selected['evidence_only'] = True
        selected['source_revisions'] = _rev_history(full_history)
        selected['source_row'] = (full_history[-1].get('row') if full_history else None)
        # Display only compact evidence in running app; detailed coordinates
        # are kept in separate full audit archive to avoid bloating memory/UI.
        selected.pop('provenance', None)
        selected.pop('pricing_status', None)
        combined[sku] = selected
        audit[sku] = full_history

    aliases = defaultdict(set)
    for source in (new.get('aliases', {}), earlier.get('aliases', {})):
        for alias, targets in source.items():
            if not isinstance(targets, list):
                continue
            for code in targets:
                if code in combined and code != alias:
                    aliases[alias].add(code)
    aliases = {k: sorted(v) for k, v in sorted(aliases.items()) if v}
    restored = sorted(set(old) - set(records))
    freshly_found = sorted(set(records) - set(old))
    # Physical master worksheets are authoritative for 2020-24. Only years
    # not physically supplied remain represented by the recovered snapshots.
    physical_years = {row['year'] for row in new_manifest['worksheets']
                      if row.get('status') == 'read' and row.get('equipment_rows', 0) > 0}
    recovered_sheets = [dict(row, recovered_identity_only=True)
                        for row in old_manifest.get('worksheets', [])
                        if row.get('status') == 'read' and row.get('year') not in physical_years
                        and row.get('equipment_rows', 0) > 0]
    sheets = new_manifest['worksheets'] + recovered_sheets
    total_observations = sum(row.get('equipment_rows', 0) for row in sheets
                             if row.get('status') == 'read')
    source_files = sorted({row['file'] for row in sheets
                           if row.get('status') == 'read' and row.get('equipment_rows', 0) > 0})
    manifest = {
        'archive_scope': 'Physical 2020-2024 revisions combined with 2025-2026 recovered identity snapshots; original 2025-2026 workbooks still require source verification',
        'archive_review_status': 'Not approved',
        'source_files': len(source_files),
        'snapshots': total_observations,
        'unique_skus': len(combined),
        'alias_codes': len(aliases),
        'ambiguous_alias_codes': sum(len(x)>1 for x in aliases.values()),
        'worksheets': sheets,
        'by_year': dict(sorted(Counter({year: sum(r.get('equipment_rows', 0) for r in sheets if r.get('year')==year and r.get('status')=='read') for year in range(2020, 2027)}).items())),
        'reconciliation': {
            'new_source_unique_skus': len(records),
            'recovered_source_unique_skus': len(old),
            'intersection_unique_skus': len(set(records)&set(old)),
            'new_only_unique_skus': len(freshly_found),
            'recovered_only_unique_skus': len(restored),
            'newer_recovered_variants_preserved': newer_recovered,
            'new_source_variants_preferred': superseded_recovered,
            'physical_files_read': new_manifest.get('source_files'),
            'physical_observations_read': new_manifest.get('snapshots'),
            'recovered_2025_2026_observations': sum(r.get('equipment_rows',0) for r in recovered_sheets),
        },
        'pricing_status': 'IDENTITY ONLY - NO APPROVED RRP',
        'note': 'Catalogue identities and source provenance are not permission to use a historical RRP or substitute a newer console. Owner source signoff is pending.',
    }
    target.mkdir(parents=True, exist_ok=True)
    (target/INDEX).write_text(json.dumps({'records':combined,'aliases':aliases}, ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    if write_audit:
        (target/'historical_full_provenance.json').write_text(json.dumps(audit,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        with (target/'historical_reconciliation_review.csv').open('w',newline='',encoding='utf-8-sig') as output:
            writer=csv.writer(output)
            writer.writerow(['Review Type','Code','Candidates/Count','Guidance'])
            for code, candidates in aliases.items():
                if len(candidates)>1:
                    writer.writerow(['Ambiguous historical alias',code,' | '.join(candidates),'Do not automatically choose a replacement or RRP'])
            for sku in restored:
                writer.writerow(['Recovered-only equipment SKU',sku, '1','Verify against physical source archive when available'])
    return manifest


def main():
    parser=argparse.ArgumentParser(description='Reconcile physical historical master imports with later recovered identity index.')
    parser.add_argument('--physical',type=Path,required=True)
    parser.add_argument('--recovered',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=reconcile(args.physical,args.recovered,args.output)
    print(json.dumps({k:report[k] for k in ('source_files','snapshots','unique_skus','alias_codes','ambiguous_alias_codes','reconciliation')},indent=2))


if __name__=='__main__':
    main()
