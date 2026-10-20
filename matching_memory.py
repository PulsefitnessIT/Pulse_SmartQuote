"""Human-confirmed legacy equipment crosswalk. Never automatically prices or selects items.

Rules describe exact imported equipment identity, NOT a product substitution policy.
This local register is held in smartquote_local.db and is excluded from pilot ZIPs.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path
from contextlib import closing
from asset_intelligence import normalize_asset, value
import engine as E

DB = Path(__file__).resolve().parent / 'smartquote_local.db'


def clean(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip().upper()


def identity(asset):
    """Prefer the immutable imported columns, not subsequently chosen SKU/model."""
    original = asset.get('source_cells')
    if isinstance(original, dict) and any(original.get(k) for k in ('name','code','model','make')):
        source = normalize_asset({key: original.get(key,'') for key in
                        ('name','code','model','make','console','serial','site')})
    else:
        source = {key: asset.get('imported_'+key, asset.get(key,''))
                  for key in ('name','code','model','make','console')}
    return {key:clean(value(source.get(key,''))) for key in
            ('code','model','console','make','name')}


def fingerprint(asset):
    source=identity(asset)
    if not source['code'] and not source['model']:
        raise ValueError('Matching memory needs an identifiable original product code or model; description alone is unsafe.')
    serial=json.dumps(source,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(serial.encode('utf-8')).hexdigest(),source


def db():
    c=sqlite3.connect(DB,timeout=12)
    c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS equipment_crosswalk (id TEXT PRIMARY KEY, signature TEXT NOT NULL UNIQUE, source_json TEXT NOT NULL, sku TEXT NOT NULL, revision INTEGER NOT NULL, evidence TEXT NOT NULL, reviewer TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL, status TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS equipment_crosswalk_audit (id TEXT PRIMARY KEY, rule_id TEXT NOT NULL, action TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL, at TEXT NOT NULL)')
    c.execute('CREATE INDEX IF NOT EXISTS equipment_crosswalk_status ON equipment_crosswalk(status)')
    c.commit()
    return c


def remember(asset,sku,reviewer,evidence,revision):
    sku=clean(sku);reviewer=str(reviewer or '').strip();evidence=str(evidence or '').strip()
    if sku not in E.BY_SKU or sku in E.DUPLICATE_CODES:
        raise ValueError('Only a non-conflicting SKU in the current catalogue can be retained as an identity suggestion.')
    if len(evidence)<12 or len(evidence)>800:
        raise ValueError('Enter at least 12 characters of physical identification evidence or reference (max 800).')
    if len(reviewer)<2:raise ValueError('Reviewer name required.')
    signature,source=fingerprint(asset)
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    with closing(db()) as c, c:
        existing=c.execute('SELECT * FROM equipment_crosswalk WHERE signature=?',(signature,)).fetchone()
        if existing and existing['status']=='active' and existing['sku']!=sku:
            raise ValueError('This exact imported identity already has a DIFFERENT reviewed SKU. Revoke the old rule with a reason before approving a replacement.')
        if existing and existing['status']=='active':
            return {'rule_id':existing['id'],'created':False,'sku':sku}
        # Historical, revoked records are reactivated only following fresh explicit review.
        rule_id=existing['id'] if existing else uuid.uuid4().hex
        c.execute('INSERT OR REPLACE INTO equipment_crosswalk VALUES (?,?,?,?,?,?,?,?,?,?)',
                  (rule_id,signature,json.dumps(source,sort_keys=True),sku,int(revision),evidence,reviewer,now,now,'active'))
        c.execute('INSERT INTO equipment_crosswalk_audit VALUES (?,?,?,?,?,?)',
                  (uuid.uuid4().hex,rule_id,'RECONFIRMED' if existing else 'CONFIRMED',reviewer,evidence,now))
    return {'rule_id':rule_id,'created':True,'sku':sku}


def recall(asset,revision):
    try: signature,source=fingerprint(asset)
    except ValueError:return None
    c=db()
    try: row=c.execute('SELECT * FROM equipment_crosswalk WHERE signature=? AND status=?',(signature,'active')).fetchone()
    finally:c.close()
    if not row:return None
    sku=row['sku']
    if sku not in E.BY_SKU or sku in E.DUPLICATE_CODES:
        return {'sku':sku,'available':False,'stale':True,'reason':'Reviewed SKU missing or conflicting in current catalogue; data-owner action required','identity_only':True}
    option=E.live_catalogue_option(E.BY_SKU[sku],'Previously reviewed equipment identity — RECONFIRM')
    stale=revision!=row['revision']
    return {'sku':sku,'available':True,'stale':stale,'source':source,
            'evidence':row['evidence'],'reviewed_by':row['reviewer'],
            'reviewed_at':row['updated'],'catalogue_revision':row['revision'],
            'reason':('Catalogue changed since identity review; reconfirm SKU, console and current RRP' if stale else 'Previously verified import signature; physical unit must be reconfirmed'),
            'identity_only':True,'operator_confirmation_required':True,
            'catalogue_option':option}


def all_rules(limit=250):
    c=db()
    try: records=c.execute('SELECT * FROM equipment_crosswalk ORDER BY updated DESC LIMIT ?',
                          (max(1,min(int(limit),1000)),)).fetchall()
    finally:c.close()
    return [{'id':r['id'],'source':json.loads(r['source_json']),'sku':r['sku'],
             'status':r['status'],'evidence':r['evidence'],'reviewer':r['reviewer'],
             'revision':r['revision'],'created':r['created'],'updated':r['updated'],
             'catalogue_sku_available':r['sku'] in E.BY_SKU and r['sku'] not in E.DUPLICATE_CODES}
            for r in records]


def revoke(rule_id, reviewer, reason):
    reason=str(reason or '').strip()
    if len(reason)<12:raise ValueError('Enter a meaningful revocation reason (12+ characters).')
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    with closing(db()) as c, c:
        row=c.execute('SELECT status FROM equipment_crosswalk WHERE id=?',(rule_id,)).fetchone()
        if not row:raise ValueError('Matching rule not found.')
        if row['status']!='active':raise ValueError('This rule is already revoked.')
        c.execute('UPDATE equipment_crosswalk SET status=?,updated=? WHERE id=?',('revoked',now,rule_id))
        c.execute('INSERT INTO equipment_crosswalk_audit VALUES (?,?,?,?,?,?)',
                  (uuid.uuid4().hex,rule_id,'REVOKED',reviewer,reason,now))
    return {'revoked':True,'id':rule_id}
