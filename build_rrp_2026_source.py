"""Sanitise an operator-supplied staged RRP CSV into a source-only evidence index.

Usage: python build_rrp_2026_source.py <staging.csv> <original_master.xlsx>
Never import supplier cost, sell price or customer information into the index.
"""
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

DEST = Path(__file__).resolve().parent / 'data' / 'rrp_2026_source.json.gz'
SOURCE_NAME = 'Full Master Price List 24-08-2026.xlsx'


def build(csv_path, master_path, destination=DEST):
    csv_path, master_path, destination = map(Path, (csv_path, master_path, destination))
    if master_path.name != SOURCE_NAME:
        raise ValueError('Supply the named 24 August 2026 full master price list')
    verified_hash = hashlib.sha256(master_path.read_bytes()).hexdigest()
    if verified_hash != 'fbc544db9365f6b47cd37fb3e085e5c75acc03042eff5d6f820ffa55f80b3433':
        raise ValueError('Original master SHA-256 mismatch; do not stage uncertain prices')
    rows = []
    with csv_path.open(encoding='utf-8-sig', newline='') as f:
        for x in csv.DictReader(f):
            code = str(x['product_code']).strip().upper()
            if not code or not x.get('source_row'): continue
            rows.append({'sku':code,'name':x['description'],'console':x['console'],
                         'rrp':x['list_price_gbp'],'sheet':x['sheet'],
                         'row':int(x['source_row']),'rrp_column':x['rrp_column']})
    if len(rows) != 4640 or len({x['sku'] for x in rows}) != 4632:
        raise ValueError('Staged source row/SKU count changed; review raw import again')
    data = {'source_file':SOURCE_NAME, 'source_date':'2026-08-24',
            'source_sha256':verified_hash, 'source_status':'PENDING_COMMERCIAL_APPROVAL',
            'source_rows':len(rows),'rows':rows,
            'note':'Source list RRPs only. Excludes selling prices and supplier costs. No live catalogue approval.'}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(destination,'wt',encoding='utf-8',compresslevel=9) as h:
        json.dump(data,h,ensure_ascii=False,separators=(',',':'))
    return data

if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit('Provide staged CSV and matching original master price list')
    result = build(sys.argv[1],sys.argv[2]); print('Staged source SKUs',len({x['sku'] for x in result['rows']}))
