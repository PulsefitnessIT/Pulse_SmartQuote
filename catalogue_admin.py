"""Single-computer catalogue management. Staged imports and audit trail.
Source JSON is immutable; SQLite overlays are explicitly local pilot data.
"""
from __future__ import annotations
import csv, io, json, re, sqlite3, datetime, uuid
from pathlib import Path
import engine as E

ROOT=Path(__file__).parent
DB=ROOT/'smartquote_local.db'
COLUMNS=['sku','name','rrp','model','group','category','console','rate_group_override','coverage_override','console_multiplier_override','edit_reason']
def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS catalogue_edits (sku TEXT PRIMARY KEY, payload TEXT NOT NULL, modified TEXT NOT NULL, operator TEXT NOT NULL, reason TEXT NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS catalogue_audit (id TEXT PRIMARY KEY, sku TEXT, modified TEXT, operator TEXT, reason TEXT, previous TEXT, updated TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS catalogue_imports (id TEXT PRIMARY KEY, filename TEXT NOT NULL, created TEXT, payload TEXT NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS catalogue_metadata (key TEXT PRIMARY KEY, value TEXT)')
 c.execute("INSERT OR IGNORE INTO catalogue_metadata VALUES ('revision','0')")
 c.commit();return c

def revision():
 c=db();r=c.execute("SELECT value FROM catalogue_metadata WHERE key='revision'").fetchone();c.close();return int(r['value'])

def bump(c):c.execute("UPDATE catalogue_metadata SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")

def apply_stored():
 c=db();rows=c.execute('SELECT payload FROM catalogue_edits ORDER BY sku').fetchall();c.close()
 for row in rows:E.update_catalogue(json.loads(row['payload']))
 return len(rows)

def validate(s, original=None):
 data={**(original or {}), **s}
 sku=E.upper(data.get('sku',''))
 if not re.fullmatch(r'[A-Z0-9][A-Z0-9._/+-]{1,59}',sku):raise ValueError('An item code of 2-60 letters, digits or normal SKU symbols is required.')
 name=E.neat(data.get('name',''))
 if len(name)<4 or len(name)>300:raise ValueError('Provide an equipment description (4-300 characters).')
 try:rrp=float(str(data.get('rrp','')).replace('£','').replace(',','').strip())
 except:raise ValueError('Enter a numeric current RRP.')
 if not 0<rrp<=10000000:raise ValueError('RRP must be greater than £0 and below £10m.')
 rate=data.get('rate_group_override') or ''
 if rate and rate not in E.RATES or rate=='Manual Review':raise ValueError('Choose a recognised equipment rate group.')
 cov=data.get('coverage_override') or ''
 if cov not in ('','Estimate - approval required','Approved for maintenance','Not eligible'):
  raise ValueError('Invalid maintenance eligibility.')
 try:factor=float(data.get('console_multiplier_override') or 1)
 except:raise ValueError('Invalid console multiplier.')
 if not .7<=factor<=2.0:raise ValueError('Console multiplier outside controlled range (0.7-2.0).')
 data.update({'sku':sku,'name':name,'rrp':E.money(rrp),'model':E.upper(data.get('model',''))[:55],
  'group':E.neat(data.get('group',''))[:85], 'category':E.neat(data.get('category',''))[:85],
  'console':E.neat(data.get('console',''))[:130] or 'No Console / N/A',
  'rate_group_override':rate,'coverage_override':cov,'console_multiplier_override':factor})
 if not data.get('service_key'):
  data['service_key']=data['model']+' | '+data['console']
 if not data.get('match'):data['match']='Price list only - review'
 if cov=='Approved for maintenance' and not rate:raise ValueError('A confirmed rate group is needed before approving maintenance eligibility.')
 return data

def save_item(payload, operator, reason, external_connection=None):
 operator=E.neat(operator);reason=E.neat(reason)
 if len(operator)<3 or len(reason)<12:raise ValueError('Operator and a meaningful reason (12+ characters) are required.')
 code=E.upper(payload.get('sku'))
 old=E.BY_SKU.get(code)
 updated=validate(payload,old)
 c=external_connection or db()
 now=datetime.datetime.now().isoformat(timespec='seconds')
 c.execute('INSERT OR REPLACE INTO catalogue_edits VALUES (?,?,?,?,?)',(code,json.dumps(updated,ensure_ascii=False),now,operator,reason))
 c.execute('INSERT INTO catalogue_audit VALUES (?,?,?,?,?,?,?)',(uuid.uuid4().hex,code,now,operator,reason,json.dumps(old,ensure_ascii=False),json.dumps(updated,ensure_ascii=False)))
 bump(c)
 if not external_connection:c.commit();c.close()
 E.update_catalogue(updated)
 return updated

ALIASES={
 'sku':{'product code','item code','sku','stock code','code','product id','productcode','part number'},
 'name':{'description','product description','item description','name','equipment description','product name'},
 'rrp':{'current rrp','rrp','selling price','list price','retail price','rrp gbp'},
 'model':{'model','model number','model code'},
 'group':{'product group','group'},'category':{'product category','category'},
 'console':{'contract console type','console type','console','display'},
}
def canon(v):return E.descslug(v)
def parse_master(filename,raw):
 if not filename.lower().endswith(('.xlsx','.csv','.tsv')):raise ValueError('Upload a CSV or XLSX catalogue or price-list export.')
 if len(raw)>60*1024*1024:raise ValueError('Upload must be under 60 MB. For larger files export the SKU catalogue tab.')
 sheets=E.parse_xlsx(raw) if filename.lower().endswith('.xlsx') else E.parse_csv(raw)
 candidates=[];inspected=[]
 for title,rows in sheets:
  candidate=None
  for i,row in enumerate(rows[:35]):
   cols={k:next((idx for idx,v in row.items() if isinstance(idx,int) and canon(v) in variants),None) for k,variants in ALIASES.items()}
   if all(cols.get(k) is not None for k in ('sku','name','rrp')):
    candidate=(i,cols);break
  if candidate is None:
   inspected.append(title+' (no SKU/Description/RRP header found)');continue
  first,cols=candidate
  for r in rows[first+1:]:
   get=lambda key:E.neat(r.get(cols[key])) if cols.get(key) is not None else ''
   if not get('sku') or not get('name'):continue
   value={k:get(k) for k in ('sku','name','rrp','model','group','category','console') if cols.get(k) is not None}
   value.update({'source_sheet':title,'source_row':r.get('_rownum')})
   try:
    orig=E.BY_SKU.get(E.upper(value['sku']))
    clean=validate(value,orig)
    for k in ('source_sheet','source_row'):clean.pop(k,None)
    watch=('rrp','name','model','group','category','console','rate_group_override','coverage_override','console_multiplier_override')
    action='New' if orig is None else ('Changed' if any(E.neat(orig.get(k))!=E.neat(clean.get(k)) for k in watch) else 'Unchanged')
    candidates.append({'action':action,'item':clean,'source_sheet':title,'source_row':r.get('_rownum')})
   except Exception as e:candidates.append({'action':'Invalid','item':value,'error':str(e),'source_sheet':title,'source_row':r.get('_rownum')})
  inspected.append(title)
 if not candidates:raise ValueError('No recognised SKU / Description / RRP rows. Supply a clean three-column price list or the SmartQuote SKU Catalogue sheet. No changes made. Sheets checked: '+', '.join(inspected[:8]))
 if len(candidates)>12000:raise ValueError('Split imported price lists larger than 12,000 lines.')
 seen={}
 for r in candidates:
  code=E.upper(r['item']['sku'])
  if code in seen:
   orig=seen[code]
   if any(r['item'].get(k)!=orig['item'].get(k) for k in ('rrp','name','model','group','category','console')):
    r['action']='Conflict';orig['action']='Conflict'
   else:r['action']='Duplicate identical'
  else:seen[code]=r
 return candidates,inspected

def stage(filename,raw):
 rows,sheets=parse_master(filename,raw)
 token=uuid.uuid4().hex;now=datetime.datetime.now().isoformat(timespec='seconds')
 c=db();c.execute('INSERT INTO catalogue_imports VALUES (?,?,?,?)',(token,filename,now,json.dumps({'rows':rows,'revision':revision()},ensure_ascii=False)));c.commit();c.close()
 from collections import Counter
 counts=dict(__import__('collections').Counter(r['action'] for r in rows))
 return {'stage_id':token,'filename':filename,'source_sheets':sheets,'counts':counts,'total':len(rows),'preview':[{k:v for k,v in r.items() if k!='item'}|{'sku':r['item'].get('sku'),'name':r['item'].get('name'),'rrp':r['item'].get('rrp')} for r in rows[:30]],'message':'Preview only: no live catalogue rows have changed.'}

def apply_stage(token,operator,reason):
 operator=E.neat(operator);reason=E.neat(reason)
 if len(operator)<3 or len(reason)<12:raise ValueError('Enter an editor name and a meaningful source/reference (12+ characters).')
 c=db();r=c.execute('SELECT payload FROM catalogue_imports WHERE id=?',(token,)).fetchone()
 if not r:c.close();raise ValueError('Import preview is missing or was already applied.')
 staged=json.loads(r['payload'])
 if isinstance(staged,dict):
  if staged.get('revision')!=revision():c.close();raise ValueError('The catalogue changed after your preview. Please upload and preview again.')
  rows=staged['rows']
 else:rows=staged
 changes=[x for x in rows if x['action'] in ('New','Changed')]
 updated=[]
 try:
  now=datetime.datetime.now().isoformat(timespec='seconds')
  for row in changes:
   code=E.upper(row['item']['sku']);old=E.BY_SKU.get(code)
   item=validate(row['item'],old)
   c.execute('INSERT OR REPLACE INTO catalogue_edits VALUES (?,?,?,?,?)',(code,json.dumps(item,ensure_ascii=False),now,operator,reason))
   c.execute('INSERT INTO catalogue_audit VALUES (?,?,?,?,?,?,?)',(uuid.uuid4().hex,code,now,operator,reason,json.dumps(old,ensure_ascii=False),json.dumps(item,ensure_ascii=False)))
   updated.append(item)
  if changes:bump(c)
  c.execute('DELETE FROM catalogue_imports WHERE id=?',(token,));c.commit()
 except Exception:c.rollback();raise
 finally:c.close()
 # Update the in-process indexes once for the entire batch, not thousands of times.
 if updated:
  codes={p['sku'].upper() for p in updated}
  E.CAT[:]=[p for p in E.CAT if p['sku'].upper() not in codes]+updated
  E.refresh_source_indexes()
 return {'updated':len(changes),'skipped':len(rows)-len(changes),'conflicts':sum(r['action']=='Conflict' for r in rows),'revision':revision()}

def as_csv():
 buff=io.StringIO();w=csv.writer(buff);w.writerow(COLUMNS+['price_origin','tariff_group','monthly_silver','monthly_gold','monthly_platinum','data_warnings'])
 for p in sorted(E.CAT,key=lambda x:(x['sku'],x['name'])):
  o=E.live_catalogue_option(p)
  costs=[None if p['sku'].upper() in E.DUPLICATE_CODES else E.price_line({'selected':o,'qty':1},'Standard',tier,0) for tier in ('Silver','Gold','Platinum')]
  vals=[p.get(f,'') for f in COLUMNS]+[o.get('price_origin'),o.get('rate_group')]+[E.money(z['unit']/12) if z else '' for z in costs]+['Conflicting SKU' if p['sku'].upper() in E.DUPLICATE_CODES else ('RRP-derived estimate needs approval' if o['price_origin']=='calculated-estimate' else '')]
  w.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in vals])
 return buff.getvalue()
