"""Dated Sage Sales Price fallback. Never rewrites the master RRP, tariffs or PDF history.
Equipment prices are sourced only from a manager-imported Sage export, never a customer invoice.
"""
from __future__ import annotations
import csv,datetime as dt,gzip,hashlib,io,json,os,re,sqlite3,threading,zipfile
from contextlib import contextmanager
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parent
N='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
ALLOWED_GROUPS=frozenset(('Strength Equipment','Cardiovascular Equipment','Functional Equipment','Free Weight Benches & Racks','Studio/Circuit Equipment','Non Pulse Equipment','Equipment with Serial Numbers','Equipment without serial numbers'))
_LOCK=threading.RLock()

def database():
 return Path(os.environ.get('SMARTQUOTE_SAGE_DB') or ROOT/'smartquote_local.db')

def due(date):
 d=dt.date.fromisoformat(date)
 try:return d.replace(year=d.year+1).isoformat()
 except ValueError:return d.replace(year=d.year+1,day=28).isoformat()

@contextmanager
def _db():
 c=sqlite3.connect(database(),timeout=10);c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS sage_price_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, imported_at TEXT NOT NULL, imported_by TEXT NOT NULL, filename TEXT NOT NULL, file_sha256 TEXT NOT NULL, source_date TEXT NOT NULL, review_due TEXT NOT NULL, total_rows INTEGER NOT NULL, usable_rows INTEGER NOT NULL, excluded_rows INTEGER NOT NULL, active INTEGER NOT NULL, payload BLOB NOT NULL)')
 c.execute('CREATE INDEX IF NOT EXISTS idx_sage_active ON sage_price_snapshots(active)')
 c.commit()
 try:
  yield c;c.commit()
 except Exception:
  c.rollback();raise
 finally:c.close()

def _parse_sheet(raw):
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  shared=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   shared=[''.join(t.text or '' for t in el.iter(N+'t')) for el in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(N+'si')]
  names=[n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n)]
  if not names:raise ValueError('No Excel worksheet found.')
  with z.open(sorted(names)[0]) as f:
   for _,el in ET.iterparse(f,events=('end',)):
    if el.tag!=N+'row':continue
    row={}
    for c in el.findall(N+'c'):
     col=re.match(r'[A-Z]+',c.attrib.get('r',''))
     if not col:continue
     v=c.find(N+'v');typ=c.attrib.get('t','');value=v.text if v is not None else ''
     if typ=='s' and value:value=shared[int(value)]
     if typ=='inlineStr':value=''.join(t.text or '' for t in c.iter(N+'t'))
     row[col.group(0)]=str(value or '').strip()
    num=int(el.attrib.get('r','0'));el.clear()
    if row:yield num,row

def _parse_csv(raw):
 text=raw.decode('utf-8-sig')
 try:dialect=csv.Sniffer().sniff(text[:2048],delimiters=',;\t')
 except csv.Error:dialect=csv.excel
 for i,values in enumerate(csv.reader(io.StringIO(text),dialect),1):
  if any(v.strip() for v in values):yield i,{chr(65+j):v.strip() for j,v in enumerate(values[:4])}

def parse(filename,raw):
 if not isinstance(raw,bytes) or not raw or len(raw)>25*1024*1024:raise ValueError('Sage export must be a non-empty file under 25 MB.')
 ext=Path(filename).suffix.lower()
 if ext not in ('.csv','.xlsx'):raise ValueError('Upload a Sage Sales Price export as CSV or XLSX.')
 rows=_parse_sheet(raw) if ext=='.xlsx' else _parse_csv(raw)
 found={};conflict=set();total=0;invalid=0;equipment=0
 for line,cells in rows:
  if line==1:
   expected=('code','name','product group description','sales price')
   actual=tuple(cells.get(chr(65+i),'').strip().lower() for i in range(4))
   if actual!=expected:raise ValueError('Sage export must contain Code, Name, Product Group Description, Sales Price in columns A-D.')
   continue
  total+=1
  if total>60000:raise ValueError('Sage export exceeds 60,000 rows.')
  sku=cells.get('A','').strip().upper();name=cells.get('B','').strip();group=cells.get('C','').strip()
  if group not in ALLOWED_GROUPS:continue
  equipment+=1
  if not sku or len(sku)>100 or not re.fullmatch(r'[A-Z0-9][A-Z0-9._/-]*',sku):invalid+=1;continue
  try:
   number=Decimal(cells.get('D','') or '0')
   if not number.is_finite() or number<=0 or number>1000000:raise ValueError('Invalid sales price')
   value=float(number.quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
  except (InvalidOperation,ValueError):invalid+=1;continue
  record={'sku':sku,'name':name,'group':group,'sales_price':value,'row':line}
  if sku in found and (found[sku]['sales_price']!=value or found[sku]['name']!=name):conflict.add(sku)
  else:found.setdefault(sku,record)
 for code in conflict:found.pop(code,None)
 if total<5 or not found:raise ValueError('No valid Sage equipment price lines. Nothing changed.')
 return {'prices':found,'total_rows':total,'usable_rows':len(found),'equipment_rows':equipment,'excluded_rows':total-len(found),'invalid_equipment':invalid,'conflicting_codes':len(conflict)}

@lru_cache(maxsize=1)
def active():
 with _LOCK:
  with _db() as c:
   row=c.execute('SELECT id,filename,source_date,review_due,total_rows,usable_rows,excluded_rows,imported_at,imported_by,file_sha256,payload FROM sage_price_snapshots WHERE active=1 ORDER BY id DESC LIMIT 1').fetchone()
   if not row:return {'prices':{},'status':None}
   result=dict(row)
   result['prices']=json.loads(gzip.decompress(result.pop('payload')).decode('utf-8'))
   result['status']='due' if result['review_due']<=dt.date.today().isoformat() else 'current'
   return result

def status():
 snapshot=active().copy();snapshot.pop('prices',None)
 if not snapshot.get('id'):return {'loaded':False,'status':'not_loaded','message':'No Sage fallback snapshot installed. A pricing manager can import the dated Sage Sales Price export.'}
 snapshot['loaded']=True
 snapshot['days_until_review']=(dt.date.fromisoformat(snapshot['review_due'])-dt.date.today()).days
 return snapshot

def lookup(sku):
 if not isinstance(sku,str):return None
 snapshot=active();record=snapshot['prices'].get(sku.strip().upper())
 if not record:return None
 return {**record,'source':'Sage Sales Price export — static reference only','source_date':snapshot['source_date'],'review_due':snapshot['review_due'],'snapshot_id':snapshot['id'],'stale':snapshot['status']=='due','file_sha256':snapshot['file_sha256']}

def install(filename,raw,source_date,operator='Pricing manager'):
 dt.date.fromisoformat(source_date)
 if dt.date.fromisoformat(source_date)>dt.date.today():raise ValueError('Sage price-list date cannot be in the future.')
 result=parse(filename,raw);digest=hashlib.sha256(raw).hexdigest()
 payload=gzip.compress(json.dumps(result['prices'],separators=(',',':'),ensure_ascii=False).encode('utf-8'))
 with _LOCK:
  with _db() as c:
   prev=c.execute('SELECT id,file_sha256 FROM sage_price_snapshots WHERE active=1 ORDER BY id DESC LIMIT 1').fetchone()
   if prev and prev['file_sha256']==digest:return {**status(),'unchanged':True}
   c.execute('UPDATE sage_price_snapshots SET active=0 WHERE active=1')
   c.execute('INSERT INTO sage_price_snapshots(imported_at,imported_by,filename,file_sha256,source_date,review_due,total_rows,usable_rows,excluded_rows,active,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(dt.datetime.now(dt.timezone.utc).isoformat(),str(operator)[:120],Path(filename).name,digest,source_date,due(source_date),result['total_rows'],result['usable_rows'],result['excluded_rows'],1,payload))
   c.commit()
  active.cache_clear()
 return {**status(),'unchanged':False,'invalid_equipment':result['invalid_equipment'],'conflicting_codes':result['conflicting_codes'],'equipment_rows':result['equipment_rows']}

def seed_from_local():
 """Optional first-launch Windows seed. Never changes an existing Sage snapshot."""
 if active()['status'] is not None:return False
 seed=ROOT/'data'/'sage_price_seed_2026-10-23.xlsx'
 if not seed.is_file():return False
 install(seed.name,seed.read_bytes(),'2026-10-23','Pulse Fitness Sage snapshot seed')
 return True
