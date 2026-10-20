"""V10 legacy RRP policy register: manager review, never autonomous pricing.

Current-equivalent RRP is the default commercial basis.  Any historical RRP
exception must be traceable to documentary evidence and independently approved.
This module does NOT alter equipment selections, quotes, RRPs or tariffs.
"""
from __future__ import annotations
import datetime as dt
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
import engine as E

DB = Path(__file__).resolve().parent / 'smartquote_local.db'
BASIS = {'current_equivalent', 'legacy_exception'}
POLICY = {
    'default_basis': 'current_equivalent',
    'exception_basis': 'legacy_exception',
    'applies_to': 'Legacy Pulse Fitness equipment only',
    'approved_policy': True,
    'authorisation_scope': 'Pricing basis decision only; no SKU, console, RRP, tariff, or customer quotation has been approved',
    'requires_exact_configuration': True,
    'requires_operator_confirmation': True,
    'automatic_price_application': False,
    'historical_rrp_auto_fallback': False,
}


def code(value):
    token = str(value or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9._/-]{1,47}', token):
        raise ValueError('Enter a specific legacy model/SKU (2–48 characters), not a description or serial number.')
    return token


def _date(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        raise ValueError('Enter a valid ISO date (YYYY-MM-DD).')


def _db():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS legacy_rrp_policy (
        id TEXT PRIMARY KEY, legacy_code TEXT NOT NULL, basis TEXT NOT NULL,
        current_sku TEXT NOT NULL, console TEXT NOT NULL, exception_rrp REAL,
        evidence TEXT NOT NULL, reason TEXT NOT NULL, expires_on TEXT,
        proposed_by TEXT NOT NULL, proposed_at TEXT NOT NULL,
        approved_by TEXT, approved_at TEXT, status TEXT NOT NULL,
        catalogue_revision INTEGER NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS legacy_rrp_policy_audit (
        id TEXT PRIMARY KEY, rule_id TEXT NOT NULL, action TEXT NOT NULL,
        reviewer TEXT NOT NULL, note TEXT NOT NULL, at TEXT NOT NULL)''')
    c.execute('CREATE INDEX IF NOT EXISTS legacy_rrp_policy_lookup ON legacy_rrp_policy(legacy_code,status)')
    c.commit()
    return c


def _sku_check(sku, console):
    sku = code(sku)
    if sku in E.DUPLICATE_CODES or sku not in E.BY_SKU:
        raise ValueError('Current equivalent must be an existing, non-conflicting catalogue SKU.')
    target = E.BY_SKU[sku]
    if not isinstance(target.get('rrp'), (int, float)) or target['rrp'] <= 0:
        raise ValueError('Equivalent SKU has no valid numerical RRP.')
    recorded = str(target.get('console') or '').strip()
    if recorded and recorded.casefold() not in ('no console / n/a', 'none', 'n/a', 'not specified'):
        if not console or console.strip().casefold() != recorded.casefold():
            raise ValueError('Console must match the exact catalogue configuration; do not assume a console.')
    return sku


def _validate(v):
    if not isinstance(v, dict):
        raise ValueError('Submit a review object.')
    legacy = code(v.get('legacy_code'))
    basis = str(v.get('basis') or 'current_equivalent').strip()
    if basis not in BASIS:
        raise ValueError('Choose current_equivalent or legacy_exception.')
    console = str(v.get('console') or '').strip()
    if len(console) > 120:
        raise ValueError('Console information is too long.')
    evidence = str(v.get('evidence') or '').strip()
    reason = str(v.get('reason') or '').strip()
    if not 25 <= len(evidence) <= 1500 or not 20 <= len(reason) <= 800:
        raise ValueError('Supply documented source evidence (25+ characters) and a rationale (20+ characters).')
    expires = _date(v.get('expires_on'))
    if expires and expires < dt.date.today().isoformat():
        raise ValueError('Exception expiry cannot be in the past.')
    if basis == 'current_equivalent':
        sku = _sku_check(v.get('current_sku'), console)
        if legacy == sku:
            raise ValueError('A legacy-equivalence rule must identify a distinct current SKU.')
        if v.get('exception_rrp') not in (None, ''):
            raise ValueError('Do not supply a manual RRP for a current-equivalent rule.')
        rrp = None
    else:
        sku = ''
        if v.get('current_sku'):
            raise ValueError('An exception must not silently reference a current equivalent.')
        if not console:
            raise ValueError('Confirm the physical console, or write "Not fitted" / "Unconfirmed" explicitly.')
        try:
            rrp = round(float(v.get('exception_rrp')), 2)
            if not 0 < rrp <= 1000000:
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise ValueError('A legacy exception requires a positive evidenced GBP RRP, not a guessed rate.')
        if not expires:
            raise ValueError('Legacy exception requires an expiry/review date.')
    return {'legacy_code': legacy, 'basis': basis, 'current_sku': sku,
            'console': console, 'exception_rrp': rrp, 'evidence': evidence,
            'reason': reason, 'expires_on': expires}


def propose(payload, reviewer, revision):
    data = _validate(payload)
    who = str(reviewer or '').strip()
    if len(who) < 2:
        raise ValueError('Sign in with a named reviewer account.')
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    rule_id = uuid.uuid4().hex
    with closing(_db()) as c, c:
        existing = c.execute("SELECT id FROM legacy_rrp_policy WHERE legacy_code=? AND status IN ('pending','approved')",
                             (data['legacy_code'],)).fetchone()
        if existing:
            raise ValueError('This legacy code already has an active or pending decision; revoke it with an audit reason first.')
        c.execute('''INSERT INTO legacy_rrp_policy VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (rule_id, data['legacy_code'], data['basis'], data['current_sku'],
                   data['console'], data['exception_rrp'], data['evidence'], data['reason'],
                   data['expires_on'], who, now, None, None, 'pending', int(revision)))
        c.execute('INSERT INTO legacy_rrp_policy_audit VALUES (?,?,?,?,?,?)',
                  (uuid.uuid4().hex, rule_id, 'PROPOSED', who, data['reason'], now))
    return {'id': rule_id, 'status': 'pending', 'basis': data['basis'],
            'legacy_code': data['legacy_code'], 'commercially_approved': False}


def approve(rule_id, reviewer, revision, note):
    who = str(reviewer or '').strip()
    note = str(note or '').strip()
    if len(note) < 20:
        raise ValueError('Enter at least 20 characters describing your independent verification.')
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    with closing(_db()) as c, c:
        row = c.execute('SELECT * FROM legacy_rrp_policy WHERE id=?', (str(rule_id),)).fetchone()
        if not row or row['status'] != 'pending':
            raise ValueError('No pending rule with this ID.')
        if row['proposed_by'].casefold() == who.casefold():
            raise ValueError('A different authorised manager must independently approve the proposal.')
        if int(row['catalogue_revision']) != int(revision):
            raise ValueError('Catalogue changed since review; revoke and propose a fresh mapping.')
        if row['expires_on'] and row['expires_on'] < dt.date.today().isoformat():
            raise ValueError('This exception has expired and must be reviewed again.')
        if row['basis'] == 'current_equivalent':
            _sku_check(row['current_sku'], row['console'])
        c.execute('UPDATE legacy_rrp_policy SET status=?,approved_by=?,approved_at=? WHERE id=?',
                  ('approved', who, now, rule_id))
        c.execute('INSERT INTO legacy_rrp_policy_audit VALUES (?,?,?,?,?,?)',
                  (uuid.uuid4().hex, rule_id, 'APPROVED', who, note, now))
    return {'id': rule_id, 'status': 'approved', 'identity_mapping_only': True,
            'automatic_price_application': False}


def revoke(rule_id, reviewer, reason):
    reason = str(reason or '').strip()
    if len(reason) < 20:
        raise ValueError('Enter a revocation reason (20+ characters).')
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    with closing(_db()) as c, c:
        row = c.execute('SELECT status FROM legacy_rrp_policy WHERE id=?',(str(rule_id),)).fetchone()
        if not row or row['status'] not in ('pending','approved'):
            raise ValueError('No active or pending rule with this ID.')
        c.execute('UPDATE legacy_rrp_policy SET status=? WHERE id=?',('revoked',rule_id))
        c.execute('INSERT INTO legacy_rrp_policy_audit VALUES (?,?,?,?,?,?)',
                  (uuid.uuid4().hex, rule_id, 'REVOKED', str(reviewer), reason, now))
    return {'id':rule_id,'status':'revoked'}


def rules(limit=200):
    with closing(_db()) as c:
        items = c.execute('SELECT * FROM legacy_rrp_policy ORDER BY proposed_at DESC LIMIT ?',
                          (max(1,min(int(limit),1000)),)).fetchall()
        return [dict(v) for v in items]


def suggest(asset,revision):
    """Return human-review evidence, NEVER mutate an imported asset or price."""
    source = asset.get('source_cells') if isinstance(asset.get('source_cells'), dict) else {}
    original = str(source.get('code') or source.get('model') or asset.get('imported_code')
                   or asset.get('imported_model') or asset.get('code') or asset.get('model') or '').strip().upper()
    if not original:
        return {'basis':'current_equivalent','status':'unmapped',
                'requires_operator_confirmation':True,'automatic_price_application':False}
    with closing(_db()) as c:
        row = c.execute("SELECT * FROM legacy_rrp_policy WHERE legacy_code=? AND status='approved'",
                        (original,)).fetchone()
    if not row:
        return {'basis':'current_equivalent','legacy_code':original,
                'status':'unmapped','requires_operator_confirmation':True,
                'automatic_price_application':False}
    result = {'basis':row['basis'],'legacy_code':original,'status':'reviewed',
              'rule_id':row['id'],'console':row['console'],
              'reference':row['evidence'],'approved_by':row['approved_by'],
              'requires_operator_confirmation':True,'automatic_price_application':False}
    if int(revision)!=row['catalogue_revision']:
        result.update(status='stale',warning='Catalogue changed; mapping must be reapproved.')
    elif row['expires_on'] and row['expires_on']<dt.date.today().isoformat():
        result.update(status='expired',warning='Legacy exception expired; do not apply.')
    elif row['basis']=='current_equivalent':
        if row['current_sku'] not in E.BY_SKU or row['current_sku'] in E.DUPLICATE_CODES:
            result.update(status='stale',warning='Equivalent SKU is missing or conflicting.')
        else:
            target=E.BY_SKU[row['current_sku']]
            result['current_equivalent']={'sku':row['current_sku'],'name':target['name'],
                                          'console':target.get('console'),'rrp':target.get('rrp')}
    else:
        result['exception_rrp_evidence_only']=row['exception_rrp']
        result['warning']='Approved exception record is evidence only; a pricing manager must still approve its application to this quote.'
    return result
