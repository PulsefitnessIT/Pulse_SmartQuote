"""Pulse SmartQuote local pilot. NOT hardened for the public internet.
Run: python -m uvicorn main:app --host 127.0.0.1 --port 8765
"""
import base64,json,os,sqlite3,threading,uuid,datetime,re,hashlib,csv,io
from io import BytesIO
import engine as eng
import catalogue_admin as admin
import matching_memory as memory
import hybrid_rrp as hybrid
import rrp_reconciliation as rrp2026
from catalogue_gaps import analyse as analyse_gaps
from import_quality import preview as import_preflight
import bulk_review
import staff_price_guides as quick_guide
import security
from catalogue_readiness import evaluate as evaluate_readiness
from asset_intelligence import grouped_assets
from startup_manager import instance_id as installation_instance_id
from pathlib import Path
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse,FileResponse,Response,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from engine import ROOT,PRICING,PACKAGES,ingest,match_asset,calc_quote,selection_issues,BY_SKU,BY_KEY,DUPLICATE_CODES,CAT,CONFIG,sku_option,config_option,search_products,price_line,decorate_option,suggest_unknown,live_catalogue_option
from quote_pdf import create_quote_pdf
from agreement_import import read_agreement_pdf
from invoice_import import read_invoice_pdf, PLACEHOLDER_SERIALS

app=FastAPI(title='Pulse Fitness SmartQuote',version='0.10.0',docs_url=None,redoc_url=None)

@app.middleware('http')
async def local_security(request:Request,call_next):
    path=request.url.path
    if not security.enabled() or not path.startswith('/api') or path in ('/api/health','/api/auth/login'):
        return await call_next(request)
    token=request.headers.get('Authorization','').removeprefix('Bearer ').strip()
    user=security.identify(token)
    if not user:return JSONResponse({'detail':'Sign in required. Run manage_users.py bootstrap if this is your first launch.'},status_code=401)
    request.state.user=user
    if path.startswith('/api/users') and user['role'] != 'admin':
        return JSONResponse({'detail':'Only administrators can manage users.'},status_code=403)
    if path.startswith('/api/catalog/admin') and user['role'] not in ('manager','admin'):
        return JSONResponse({'detail':'Only pricing managers can edit or access master catalogue administration.'},status_code=403)
    if path.startswith('/api/quotes/') and path.endswith('/approve') and user['role'] not in ('manager','admin'):
        return JSONResponse({'detail':'Manager permission required.'},status_code=403)
    return await call_next(request)

def actor(request:Request):return getattr(getattr(request,'state',None),'user',{'username':'automated test','role':'admin'})

@app.post('/api/auth/login')
async def signin(request:Request):
    payload=await request.json()
    result=security.login(str(payload.get('username','')),str(payload.get('password','')))
    if not result:raise HTTPException(401,'Incorrect username or password.')
    return result

@app.get('/api/auth/me')
def me(request:Request):return {'user':actor(request),'auth_enabled':security.enabled(),'pilot_only':os.getenv('SMARTQUOTE_LIVE_APPROVED')!='1'}

@app.post('/api/auth/logout')
def signout(request:Request):
    security.logout(request.headers.get('Authorization','').removeprefix('Bearer ').strip())
    return {'ok':True}

admin.apply_stored()
app.mount('/static',StaticFiles(directory=str(ROOT/'static')),name='static')
DB=ROOT/'smartquote_local.db'
_lock=threading.RLock()

def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS quotes (id TEXT PRIMARY KEY, quote_no TEXT UNIQUE, created TEXT, updated TEXT, status TEXT, payload TEXT NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS quote_versions (quote_id TEXT NOT NULL, version INTEGER NOT NULL, created TEXT NOT NULL, actor TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, pdf BLOB NOT NULL, pdf_sha256 TEXT NOT NULL, PRIMARY KEY(quote_id,version))')
 c.execute('CREATE TABLE IF NOT EXISTS quote_events (event_id TEXT PRIMARY KEY, quote_id TEXT NOT NULL, timestamp TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, note TEXT)')
 c.commit();return c

def defaults():
 return {'id':uuid.uuid4().hex,'quote_no':'','created':datetime.date.today().isoformat(),'updated':datetime.datetime.now().isoformat(timespec='seconds'),'customer':'','site':'','contact':'','contact_email':'','prepared_by':'Pulse Fitness Aftersales','billing_address':'','delivery_address':'','customer_ref':'','account_ref':'','contract_ref':'','valid_days':30,'tier':'Gold','level':'Standard','term':1,'visits':1,'discount':0,'approver':'','approval_note':'','pricing_approved':False,'line_reviews_approved':False,'assets':[],'warnings':[],'files':[],'status':'Draft','pipeline_status':'Draft','renewal':None,'renewal_option_checked':False}

def persist(q):
 q['catalogue_revision']=admin.revision()
 q['engine_version']=9
 q['updated']=datetime.datetime.now().isoformat(timespec='seconds')
 q['level']='Standard' # single underlying tariff; client chooses Silver/Gold/Platinum and discount
 q['status']='Ready to generate' if calc_quote(q)['ready'] else 'Needs details'
 with _lock:
  c=conn()
  if not q['quote_no']:
   rows=c.execute("SELECT quote_no FROM quotes WHERE quote_no LIKE ?",(f'SQ-{datetime.date.today().year}-%',)).fetchall()
   seq=max([int(r[0].split('-')[-1]) for r in rows if str(r[0].split('-')[-1]).isdigit()] or [0])+1
   q['quote_no']=f'SQ-{datetime.date.today().year}-{seq:04d}'
  c.execute('INSERT OR REPLACE INTO quotes (id,quote_no,created,updated,status,payload) VALUES (?,?,?,?,?,?)',(q['id'],q['quote_no'],q['created'],q['updated'],q['status'],json.dumps(q,ensure_ascii=False)))
  c.commit();c.close()
 return q

def getq(id):
 with _lock:
  c=conn();r=c.execute('SELECT payload FROM quotes WHERE id=?',(id,)).fetchone();c.close()
 if not r:raise HTTPException(404,'Quote not found')
 q=json.loads(r['payload'])
 if q.get('catalogue_revision',0)!=admin.revision() or q.get('engine_version')!=9:
  for a in q.get('assets',[]):
   selected=a.get('selected')
   if selected and selected.get('sku'):
    sku=selected['sku'].upper()
    if sku in DUPLICATE_CODES:
     a['selected']=None;a['issues']=['Catalogue SKU became conflicting after price-list update. Please reselect.']
    elif sku in BY_SKU:
     updated=live_catalogue_option(BY_SKU[sku],'Rechecked after catalogue update')
     a['selected']=updated;a['issues']=selection_issues(updated)
  q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
  q['approval_note']='Catalogue data changed; all item prices require fresh approval.'
  persist(q)
 # If a V2 database is carried forward, switching from a hidden discounted
 # price band to the standard base requires fresh, explicit authorisation.
 if q.get('level','Standard')!='Standard':
  q['level']='Standard'
  q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
  q['approval_note']='Reapproval required after V3 tariff simplification.'
  persist(q)
 return q

def public(q):
 # Upgrade unresolved historic agreements from V7 without requiring users to
 # delete and reimport their 31 existing machine/serial records. Never replace
 # a selected SKU, a manual price, an exclusion, or a user-confirmed choice.
 upgraded=False
 for old_asset in q.get('assets',[]):
  if old_asset.get('prior_contract_ref') and not old_asset.get('selected') and not old_asset.get('excluded') and old_asset.get('manual_annual_unit') in (None,''):
   refreshed=match_asset(old_asset)
   if refreshed.get('selected') and refreshed['selected'].get('price_origin')=='historic-family-estimate':
    for field in ('selected','candidates','issues','match_type','match_confidence'):
     old_asset[field]=refreshed[field]
    upgraded=True
 if upgraded:
  persist(q)
 # Existing V2 saved quotes contain raw console placeholders. Enrich their
 # display metadata without rewriting an approved identity or source tariff.
 for asset in q.get('assets',[]):
  if isinstance(asset.get('selected'),dict):decorate_option(asset['selected'])
  for candidate in asset.get('candidates',[]):
   if isinstance(candidate,dict):decorate_option(candidate)
  if not asset.get('selected') and not asset.get('candidates') and asset.get('name'):
   asset['candidates']=suggest_unknown(asset)
 summary=calc_quote(q)
 grouped=grouped_assets(q.get('assets',[]),{line['id']:line.get('price') for line in summary['lines']})
 return {'quote':q,'summary':summary,'display_groups':grouped}

@app.get('/')
def home():return FileResponse(ROOT/'static/index.html',headers={'Cache-Control':'no-store, must-revalidate'})
@app.get('/api/health')
def health():return {'ok':True,'name':'Pulse Fitness SmartQuote','mode':'local controlled pilot','version':'V10 internal pilot','api_contract':10,'instance_id':installation_instance_id(ROOT),'auth_setup_required':security.enabled() and security.count()==0}
@app.get('/api/bootstrap')
def bootstrap():
 return {'source':PRICING['source'],'counts':PRICING['source_counts'],'tiers':PRICING['tiers'],'packages':PACKAGES,'rates':PRICING['rates'],'mode':'Local pilot with user sign-in; not a production identity provider'}
@app.get('/api/quotes')
def list_quotes(q:str='',pipeline_status:str='',limit:int=80):
 # Search stored quotes server-side: staff should still find older quotes when
 # the register contains more than the default first-page limit.
 needle=q.strip().casefold()[:150]
 status=pipeline_status.strip().casefold()[:60]
 cap=min(250,max(1,limit))
 with _lock:
  c=conn()
  rows=c.execute('SELECT id,quote_no,created,updated,status,payload FROM quotes ORDER BY updated DESC LIMIT 10000').fetchall()
  c.close()
 out=[]
 for x in rows:
  quote=json.loads(x['payload'])
  if status and quote.get('pipeline_status','Draft').casefold()!=status:continue
  if needle and needle not in ' '.join(str(quote.get(key) or '') for key in
        ('quote_no','customer','site','contact','contact_email','account_ref','contract_ref')).casefold():
   continue
  s=calc_quote(quote)
  out.append({'id':quote['id'],'quote_no':quote['quote_no'],
              'customer':quote['customer'],'site':quote['site'],'tier':quote['tier'],
              'status':quote['status'],'pipeline_status':quote.get('pipeline_status','Draft'),
              'annual':s['annual'],'lines':s['rows'],'updated':quote['updated']})
  if len(out)>=cap:break
 return {'quotes':out,'displayed':len(out),'limit':cap,'searched':bool(needle or status)}
@app.post('/api/quotes')
def create():return public(persist(defaults()))
@app.get('/api/quotes/{id}')
def load(id:str):return public(getq(id))
def _parsed_asset_upload(payload):
 filename=str(payload.get('filename',''))[:260]
 encoded=payload.get('content_base64','')
 if not isinstance(encoded,str) or len(encoded)>35*1024*1024:
  raise HTTPException(413,'File is too large (25 MB maximum).')
 try:
  data=base64.b64decode(encoded,validate=True)
  parsed=ingest(filename,data)
 except Exception as e:raise HTTPException(400,str(e))
 return parsed,hashlib.sha256(data).hexdigest()

@app.post('/api/quotes/{id}/import-preview')
async def upload_preview(id:str,request:Request):
 """No quote writes; staff explicitly confirm a readable asset list before append."""
 q=getq(id)
 parsed,digest=_parsed_asset_upload(await request.json())
 if len(q['assets'])+len(parsed['assets'])>2000:
  raise HTTPException(400,'This import would exceed 2,000 asset rows. Split the register.')
 result=import_preflight(parsed,q)
 result['content_sha256']=digest
 result['already_imported']=any(item.get('content_sha256')==digest for item in q['files'])
 return result

@app.post('/api/quotes/{id}/import')
async def upload(id:str,request:Request):
 q=getq(id)
 payload=await request.json();filename=str(payload.get('filename',''))[:260]
 parsed,digest=_parsed_asset_upload(payload)
 if any(item.get('content_sha256')==digest for item in q['files']):
  raise HTTPException(409,'This exact asset file has already been imported into this quote. No duplicate machines were added.')
 expected=payload.get('content_sha256')
 if expected and expected!=digest:
  raise HTTPException(409,'The selected file changed since preview. Preview the file again before importing.')
 if len(q['assets'])+len(parsed['assets'])>2000:raise HTTPException(400,'Maximum 2,000 asset rows per quotation.')
 existing={a['id'] for a in q['assets']};index=len(existing)
 batch_id=uuid.uuid4().hex
 warnings_start=len(q['warnings'])
 for a in parsed['assets']:
  index+=1;a['id']=f'asset_{index}_{uuid.uuid4().hex[:6]}'
  a['import_batch_id']=batch_id
  q['assets'].append(match_asset(a))
 q['warnings']+=parsed['warnings']
 q['files'].append({'filename':filename,'content_sha256':digest,'sheets':parsed['sheets'],'imported':len(parsed['assets']),'batch_id':batch_id,
                    'warnings_start':warnings_start,
                    'at':datetime.datetime.now().isoformat(timespec='seconds')})
 q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
 persist(q);record_event(id,actor(request)['username'],'ASSET_IMPORT',f"File {filename}, {len(parsed['assets'])} machine rows");return {**public(q),'import_report':{'files':parsed['sheets'],'warnings':parsed['warnings'],'added':len(parsed['assets']),'grouped_lines':len(grouped_assets(q['assets']))}}
@app.post('/api/quotes/{id}/imports/undo-last')
def undo_last_asset_import(id:str,request:Request):
 """Undo only an untouched, most-recent spreadsheet batch; audit all removals."""
 q=getq(id)
 if not q.get('files') or not q['files'][-1].get('batch_id'):
  raise HTTPException(409,'No reversible spreadsheet import is available. Older imports cannot be undone as a batch.')
 latest=q['files'][-1]
 batch=latest['batch_id']
 chosen=[a for a in q['assets'] if a.get('import_batch_id')==batch]
 if len(chosen)!=latest['imported'] or any(a.get('import_reviewed') for a in chosen):
  raise HTTPException(409,'This import has been edited or partially removed. Undo is blocked to protect staff corrections.')
 with _lock:
  c=conn()
  issued=c.execute('SELECT 1 FROM quote_versions WHERE quote_id=? LIMIT 1',(id,)).fetchone()
  c.close()
 if issued:
  raise HTTPException(409,'An issued/PDF quotation version exists. Undo is disabled; create a new revision and review its equipment.')
 q['assets']=[a for a in q['assets'] if a.get('import_batch_id')!=batch]
 q['files'].pop()
 before=int(latest.get('warnings_start',len(q['warnings'])))
 q['warnings']=q['warnings'][:before]
 q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
 result=public(persist(q))
 record_event(id,actor(request)['username'],'ASSET_IMPORT_UNDONE',
              f"Removed {len(chosen)} rows from last import {latest['filename']} ({batch[:8]})")
 return {**result,'undone_rows':len(chosen),'filename':latest['filename']}

def _invoice_payload(payload):
    if not isinstance(payload,dict):
        raise HTTPException(400,'Each invoice must include a PDF filename and content.')
    filename=str(payload.get('filename','')).strip()[:260]
    if not filename.lower().endswith('.pdf'):
        raise HTTPException(400,'Choose a Pulse Fitness invoice PDF.')
    encoded=payload.get('content_base64','')
    if not isinstance(encoded,str) or len(encoded)>48*1024*1024:
        raise HTTPException(413,'Invoice too large. The PDF must be smaller than 35 MB.')
    try:
        raw=base64.b64decode(encoded,validate=True)
        parsed=read_invoice_pdf(raw,filename)
    except Exception as exc:
        raise HTTPException(400,str(exc))
    return parsed


def _invoice_site_key(value):
    # Allow ordinary label variation without silently joining different sites.
    text=str(value or '').casefold().replace('&',' and ')
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',text)).strip()


def _invoice_same_quote(q,parsed):
    existing=str(q.get('customer','')).strip().casefold()
    incoming=str(parsed['invoice'].get('customer','')).strip().casefold()
    # Lease-financed invoices name the finance provider as bill-to; the equipment
    # delivery site, not finance company, is the grouping key.
    if q.get('assets') and existing and incoming and existing != incoming and not parsed['invoice'].get('customer_needs_confirmation'):
        raise HTTPException(409,'Customer names differ between invoices. Confirm the contracting customer before combining.')
    current_site=_invoice_site_key(q.get('site',''))
    new_site=_invoice_site_key(parsed['invoice'].get('site',''))
    if q.get('assets') and current_site and new_site and current_site!=new_site:
        raise HTTPException(409,'This invoice is for a different site. Start a new quotation to keep asset locations separate.')


def _invoice_single_conflicts(q, parsed):
    """Do not let the old single-invoice API bypass batch safeguards."""
    number=str(parsed['invoice'].get('invoice_no','')).lstrip('0') or '0'
    fingerprint=parsed['content_sha256']
    for f in q.get('files',[]):
        if f.get('type')=='historical-sales-invoice':
            previous=str(f.get('invoice_no','')).lstrip('0') or '0'
            if previous==number and f.get('content_sha256')!=fingerprint:
                raise HTTPException(409,'Another PDF has this invoice number but different contents. Review the corrected invoice.')
    existing={_serial_key(s) for asset in q.get('assets',[]) for s in _asset_serial_list(asset)
              if _serial_key(s) not in PLACEHOLDER_SERIALS}
    incoming=set()
    for asset in parsed['assets']:
        for serial in _asset_serial_list(asset):
            key=_serial_key(serial)
            if not key or key in PLACEHOLDER_SERIALS:continue
            if key in existing:
                raise HTTPException(409,f'Serial {serial} is already on the quotation. Use Add invoices (PDF) for duplicate-safe importing.')
            if key in incoming:
                raise HTTPException(409,f'Serial {serial} appears more than once in the invoice. Check the original PDF.')
            incoming.add(key)

@app.post('/api/quotes/{id}/invoice-preview')
async def invoice_preview(id:str,request:Request):
    """Extract only, never modify a quote. Sale prices are evidence, not RRPs."""
    q=getq(id)
    parsed=_invoice_payload(await request.json())
    _invoice_same_quote(q,parsed)
    already=any(f.get('content_sha256')==parsed['content_sha256'] for f in q['files'])
    if not already:
        _invoice_single_conflicts(q,parsed)
    r=parsed['report']
    return {'invoice':parsed['invoice'],'report':r,
        'candidates':[{'code':a['code'],'name':a['name'],'qty':a['qty'],
                       'serial_count':len(a['serials']),'page':a['page'],
                       'product_group':a.get('product_group','')} for a in parsed['assets']],
        'excluded':[{'code':a['code'],'name':a['name'],'reason':a['reason'],
                     'page':a['page']} for a in parsed['excluded']],
        'unstructured_review':parsed['unstructured_review'],
        'warnings':parsed['warnings'],
        'content_sha256':parsed['content_sha256'],
        'already_imported':already,
        'capacity_ok':len(q['assets'])+len(parsed['assets'])<=2000,
        'internal_only':True,'prices_are_historical_sale_values_not_rrp':True}


@app.post('/api/quotes/{id}/invoice-import')
async def invoice_import(id:str,request:Request):
    """Staff confirmed import; append source-traceable equipment only."""
    q=getq(id)
    payload=await request.json()
    parsed=_invoice_payload(payload)
    _invoice_same_quote(q,parsed)
    if payload.get('content_sha256')!=parsed['content_sha256']:
        raise HTTPException(409,'Invoice changed since preview. Preview it again; nothing was imported.')
    if any(f.get('content_sha256')==parsed['content_sha256'] for f in q['files']):
        raise HTTPException(409,'This exact invoice was already imported into this quotation. No duplicates added.')
    _invoice_single_conflicts(q,parsed)
    if len(q['assets'])+len(parsed['assets'])>2000:
        raise HTTPException(400,'Invoice would exceed 2,000 source rows; use another quotation.')
    with _lock:
        c=conn()
        try:
            issued=c.execute('SELECT 1 FROM quote_versions WHERE quote_id=? LIMIT 1',(id,)).fetchone()
        finally:
            c.close()
    if issued:
        raise HTTPException(409,'This quotation already has saved PDF versions. Create a new revision before importing equipment.')
    invoice=parsed['invoice']
    batch_id=uuid.uuid4().hex
    warning_start=len(q['warnings'])
    for source in parsed['assets']:
        asset=match_asset({**source,'id':'invoice_'+uuid.uuid4().hex[:14],
                           'import_batch_id':batch_id})
        if source.get('invoice_purchase_sku_identified') and not asset.get('selected'):
            asset['match_type']='Invoice SKU identified — current maintenance price pending'
            asset['issues']=['The purchase invoice identifies this exact SKU. No alternative machine selection is required; pricing management must confirm the current maintenance RRP basis.']
            asset['invoice_identity_confirmed']=True
        q['assets'].append(asset)
    for k in ('customer','site','billing_address','delivery_address','account_ref','customer_ref'):
        if not str(q.get(k,'')).strip() and str(invoice.get(k,'')).strip():
            q[k]=invoice[k]
    q['warnings']+=parsed['warnings']
    if parsed['unstructured_review']:
        q['warnings'].append(f'Invoice {invoice["invoice_no"]}: {len(parsed["unstructured_review"])} unstructured descriptions could represent additional equipment or catalogue notes. Inspect the original invoice pages.')
    q['files'].append({'filename':str(payload['filename'])[:260],
       'type':'historical-sales-invoice','content_sha256':parsed['content_sha256'],
       'invoice_no':invoice['invoice_no'],'invoice_date':invoice['date'],
       'imported':len(parsed['assets']),'batch_id':batch_id,
       'held_for_scope_review':parsed['excluded'],
       'invoice_customer_review':parsed['invoice'].get('customer_needs_confirmation',False),
       'invoice_billed_to':parsed['invoice'].get('billed_to',''),
       'invoice_delivery_site':parsed['invoice'].get('site',''),
       'warnings_start':warning_start,
       'sheets':[{'sheet':f'Invoice {invoice["invoice_no"]}',
                  'rows':parsed['report']['source_rows'],'added':len(parsed['assets'])}],
       'at':datetime.datetime.now().isoformat(timespec='seconds')})
    q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
    persist(q)
    record_event(id,actor(request)['username'],'SALES_INVOICE_IMPORT',
        f'Invoice {invoice["invoice_no"]}: {len(parsed["assets"])} lines, {parsed["report"]["equipment_units"]} units; historical sale values excluded from pricing')
    return {**public(q),
            'import_report':{**parsed['report'], 'invoice_no':invoice['invoice_no'],
                             'warnings':parsed['warnings'],
                             'excluded':len(parsed['excluded']),
                             'unstructured_review':len(parsed['unstructured_review']),
                             'added':len(parsed['assets'])}}



def _serial_key(value):
    """Serials are site-unique; preserve displayed punctuation in source rows."""
    return re.sub(r'\s+', '',str(value or '')).upper()


def _asset_serial_list(asset):
    value=asset.get('serials')
    if isinstance(value,list):
        return [str(x).strip() for x in value if str(x).strip()]
    serial=asset.get('serial','')
    return [v.strip() for v in re.split(r'[,;\n]+',str(serial)) if v.strip()]


def _invoice_import_plan(q, files):
    """Parse and validate an entire invoice batch BEFORE changing the quotation.

    No invoice sale amounts become RRPs, and serial collisions never silently
    create duplicate equipment. A repeated invoice number is not a new invoice.
    """
    if not isinstance(files,list) or not 1 <= len(files) <= 10:
        raise HTTPException(400,'Select between 1 and 10 PDF invoices for the same site.')
    if any(not isinstance(x,dict) or not isinstance(x.get('content_base64'),str) for x in files):
        raise HTTPException(400,'Each invoice must include valid PDF content.')
    total=sum(len(x['content_base64']) for x in files)
    if total>95*1024*1024:
        raise HTTPException(413,'Invoice batch exceeds 70 MB of PDFs; import smaller groups.')
    reference_site=_invoice_site_key(q.get('site',''))
    seen_hash={str(x.get('content_sha256','')) for x in q.get('files',[]) if x.get('content_sha256')}
    seen_numbers={str(x.get('invoice_no','')).lstrip('0') or '0':str(x.get('content_sha256',''))
                  for x in q.get('files',[]) if x.get('type')=='historical-sales-invoice' and x.get('invoice_no')}
    existing={}
    for a in q['assets']:
        if a.get('excluded'):continue
        code=str(a.get('code','')).strip().upper()
        for serial in _asset_serial_list(a):
            key=_serial_key(serial)
            if key and key not in PLACEHOLDER_SERIALS:
                existing.setdefault(key,code)
    plans=[];report=[];combined_warnings=[];total_added=0;total_units=0;duplicate_units=0
    for payload in files:
        if not isinstance(payload,dict):
            raise HTTPException(400,'Each invoice must contain a filename and PDF.')
        parsed=_invoice_payload(payload)
        _invoice_same_quote(q,parsed)
        inv=parsed['invoice'];site=_invoice_site_key(inv.get('site',''))
        if site and reference_site and site!=reference_site:
            raise HTTPException(409,'Invoices are for different delivery sites. Use one site per quotation, or review multi-site cover separately.')
        if site and not reference_site:reference_site=site
        num=str(inv.get('invoice_no','')).lstrip('0') or '0'
        if not inv.get('invoice_no'):
            raise HTTPException(400,'Invoice number was not identified; nothing imported.')
        known=seen_numbers.get(num)
        if known is not None and known!=parsed['content_sha256']:
            raise HTTPException(409,f'Invoice {inv["invoice_no"]} has two different PDF versions. Review the correction before importing.')
        same=parsed['content_sha256'] in seen_hash or known is not None
        if same:
            report.append({'invoice_no':inv.get('invoice_no'),'filename':payload['filename'],
                           'site':inv.get('site',''),'billed_to':inv.get('billed_to',''),
                           'already_imported':True,'added_lines':0,'added_units':0,
                           'skipped_duplicate_units':0,'excluded_lines':parsed['report']['non_equipment_rows'],
                           'serial_count':parsed['report']['serial_count'],
                           'warnings':['Already imported: this invoice number or PDF is in the quotation.']})
            continue
        seen_hash.add(parsed['content_sha256']);seen_numbers[num]=parsed['content_sha256']
        planned_assets=[];skipped=0;warnings=list(parsed['warnings'])
        for asset in parsed['assets']:
            a=dict(asset)
            serials=_asset_serial_list(a)
            overlaps=[v for v in serials if _serial_key(v) in existing]
            code=str(a.get('code','')).strip().upper()
            if overlaps:
                # Different SKUs with the same serial require human investigation.
                inconsistent=[v for v in overlaps if existing[_serial_key(v)]!=code]
                if inconsistent:
                    raise HTTPException(409, f'Invoice {inv["invoice_no"]}: serial {inconsistent[0]} is already linked to a different machine. No invoices imported; inspect the invoices before combining.')
                if len(serials)!=int(a['qty']):
                    raise HTTPException(409,f'Invoice {inv["invoice_no"]}: {code} has duplicate serials but quantity cannot be reconciled automatically. No invoices imported.')
                fresh=[v for v in serials if _serial_key(v) not in existing]
                skipped+=len(serials)-len(fresh)
                if not fresh:continue
                a['qty']=len(fresh)
                a['serials']=fresh
                a['serial']=', '.join(fresh)
                a['original_invoice_qty']=asset['qty']
                warnings.append(f'Invoice {inv["invoice_no"]}, {code}: {len(serials)-len(fresh)} previously recorded serial(s) excluded to avoid double counting.')
            for serial in _asset_serial_list(a):
                key=_serial_key(serial)
                if key in existing:
                    raise HTTPException(409,f'Repeated serial {serial} within this batch. No invoices imported.')
                if key and key not in PLACEHOLDER_SERIALS:existing[key]=code
            planned_assets.append(a)
        plans.append({'parsed':parsed,'assets':planned_assets,'payload':payload,'warnings':warnings})
        qty=sum(int(a['qty']) for a in planned_assets)
        total_added+=len(planned_assets);total_units+=qty;duplicate_units+=skipped
        report.append({'invoice_no':inv.get('invoice_no'),'filename':payload['filename'],
                       'site':inv.get('site',''),'billed_to':inv.get('billed_to',''),
                       'already_imported':False,'added_lines':len(planned_assets),
                       'added_units':qty,'skipped_duplicate_units':skipped,
                       'excluded_lines':parsed['report']['non_equipment_rows'],
                       'serial_count':parsed['report']['serial_count'],
                       'warnings':warnings,
                       'examples':[{'code':a['code'],'name':a['name'],'qty':a['qty']} for a in planned_assets[:6]]})
        combined_warnings.extend(warnings)
    if len(q['assets'])+total_added>2000:
        raise HTTPException(400,'Too many equipment rows for one draft. Import fewer invoices.')
    return {'plans':plans,'invoices':report,'total_added_lines':total_added,
            'total_added_units':total_units,'duplicate_serials_skipped':duplicate_units,
            'warnings':combined_warnings,
            'content_sha256':hashlib.sha256('|'.join(x.get('content_sha256','') for x in (p['parsed'] for p in plans)).encode()).hexdigest()}


@app.post('/api/quotes/{id}/invoice-batch-preview')
async def invoice_batch_preview(id:str,request:Request):
    q=getq(id)
    data=await request.json()
    plan=_invoice_import_plan(q,data.get('files'))
    return {'invoices':plan['invoices'], 'total_added_lines':plan['total_added_lines'],
            'total_added_units':plan['total_added_units'],
            'duplicate_serials_skipped':plan['duplicate_serials_skipped'],
            'warnings':plan['warnings'],'content_sha256':plan['content_sha256'],
            'ready_to_import':bool(plan['plans']),
            'historical_invoice_sale_values_are_not_maintenance_rrp':True}


@app.post('/api/quotes/{id}/invoice-batch-import')
async def invoice_batch_import(id:str,request:Request):
    q=getq(id)
    data=await request.json()
    plan=_invoice_import_plan(q,data.get('files'))
    if data.get('content_sha256')!=plan['content_sha256']:
        raise HTTPException(409,'One or more invoices changed after preview. Preview the batch again; no equipment was added.')
    if not plan['plans']:
        raise HTTPException(409,'All these invoices are already on the quotation; no equipment added.')
    with _lock:
        c=conn()
        try: issued=c.execute('SELECT 1 FROM quote_versions WHERE quote_id=? LIMIT 1',(id,)).fetchone()
        finally:c.close()
    if issued:raise HTTPException(409,'This quotation has saved PDF versions. Create a new revision before importing more equipment.')
    # All parsing, location, duplicate and capacity checks have passed, so
    # append as one transaction. If any invoice is invalid, none are saved.
    first_invoice=plan['plans'][0]['parsed']['invoice']
    for item in plan['plans']:
        parsed=item['parsed'];inv=parsed['invoice'];batch=uuid.uuid4().hex
        for source in item['assets']:
            asset=match_asset({**source,'id':'invoice_'+uuid.uuid4().hex[:14],
                                            'import_batch_id':batch})
            if source.get('invoice_purchase_sku_identified') and not asset.get('selected'):
                asset['match_type']='Invoice SKU identified — current maintenance price pending'
                asset['issues']=['The invoice identifies this exact purchased SKU; do not choose an alternative merely to fill the price. Resolve the current RRP basis separately.']
                asset['invoice_identity_confirmed']=True
            q['assets'].append(asset)
        warning_start=len(q['warnings']);q['warnings']+=item['warnings']
        q['files'].append({'filename':str(item['payload']['filename'])[:260],
            'type':'historical-sales-invoice','content_sha256':parsed['content_sha256'],
            'invoice_no':inv['invoice_no'],'invoice_date':inv['date'],
            'imported':len(item['assets']),'batch_id':batch,
            'held_for_scope_review':parsed['excluded'],
            'invoice_customer_review':inv.get('customer_needs_confirmation',False),
            'invoice_billed_to':inv.get('billed_to',''),
            'invoice_delivery_site':inv.get('site',''),
            'warnings_start':warning_start,
            'sheets':[{'sheet':f'Invoice {inv["invoice_no"]}',
                       'rows':parsed['report']['source_rows'],'added':len(item['assets'])}],
            'at':datetime.datetime.now().isoformat(timespec='seconds')})
    for key in ('site','delivery_address','account_ref','customer_ref'):
        if not q.get(key) and first_invoice.get(key):q[key]=first_invoice[key]
    # With a lease invoice the purchaser/finance company is NOT automatically
    # the legal maintenance customer. Leave those customer fields for staff.
    if not first_invoice.get('customer_needs_confirmation'):
        if not q.get('customer') and first_invoice.get('customer'):
            q['customer']=first_invoice['customer']
        if not q.get('billing_address') and first_invoice.get('billing_address'):
            q['billing_address']=first_invoice['billing_address']
    if first_invoice.get('customer_needs_confirmation'):
        q['warnings'].append('Finance company invoice recipient differs from delivery site: check legal maintenance contract customer before customer issue.')
    q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
    persist(q)
    record_event(id,actor(request)['username'],'SALES_INVOICE_BATCH_IMPORT',
                 f'{len(plan["plans"])} invoices, {plan["total_added_lines"]} lines, {plan["total_added_units"]} units; {plan["duplicate_serials_skipped"]} duplicates omitted; sale prices never RRPs')
    return {**public(q),'import_report':{'invoice_count':len(plan['plans']),
            'added':plan['total_added_lines'],'equipment_units':plan['total_added_units'],
            'duplicate_serials_skipped':plan['duplicate_serials_skipped'],
            'invoices':plan['invoices']}}


@app.post('/api/quotes/{id}/agreement-import')
async def import_agreement(id:str,request:Request):
    q=getq(id);payload=await request.json();filename=str(payload.get('filename',''))
    with _lock:
        con=conn()
        already_issued=con.execute('SELECT 1 FROM quote_versions WHERE quote_id=? LIMIT 1',(id,)).fetchone()
        con.close()
    if already_issued:
        raise HTTPException(409,'This quotation has saved PDF versions. Create a New Quotation before importing another customer agreement.')
    if not filename.lower().endswith('.pdf'):raise HTTPException(400,'Select a previous Pulse maintenance agreement PDF.')
    encoded=payload.get('content_base64','')
    if len(encoded)>50*1024*1024:raise HTTPException(413,'Agreement file too large.')
    try: parsed=read_agreement_pdf(base64.b64decode(encoded,validate=True),filename)
    except Exception as e:raise HTTPException(400,str(e))
    if len(parsed['assets'])>2000:raise HTTPException(400,'Too many equipment rows.')
    mode=payload.get('mode','replace')
    if mode not in ('append','replace'):raise HTTPException(400,'Choose replace or append.')
    if mode=='replace':q['assets']=[]
    for a in parsed['assets']:
        a['id']='renewal_'+uuid.uuid4().hex[:12]
        q['assets'].append(match_asset(a))
    c=parsed['contract']
    for key in ('customer','site','delivery_address','billing_address','contract_ref'):
        if c.get(key):q[key]=c[key]
    if c.get('tier') in PRICING['tiers']:
        q['tier']=c['tier'];q['visits']=0 if c['tier']=='Silver' else 1
    original_terms=' '.join(str(c.get(k,'')) for k in ('agreement_length','exclusions'))
    fixed_option=bool(re.search(r'(?:same annual cost|same annual price|same price|same cost)', original_terms,re.I))
    q['renewal']={'source_filename':filename,'agreement_ref':c.get('contract_ref',''), 'previous_annual':c.get('previous_total',''),
         'previous_start':c.get('start_date',''),'previous_end':c.get('end_date',''),
         'previous_package':c.get('tier',''),'previous_length':c.get('agreement_length',''),
         'service_scope':c.get('visits_text',''),'fixed_price_extension':fixed_option,
         'contractual_note':original_terms[:1500], 'source_rows':len(parsed['assets'])}
    q['renewal_option_checked']=not fixed_option
    q['files'].append({'filename':filename,'type':'previous-agreement', 'sheets':parsed['sheets'],
        'imported':len(parsed['assets']),'at':datetime.datetime.now().isoformat(timespec='seconds')})
    q['warnings']+=parsed['warnings']
    # Import order must not matter: if the old calculations workbook was
    # loaded first, attach its evidence to the PDF's original serialised assets.
    if q.get('historic_calcs',{}).get('lines'):
        from historical_calcs import merge_old_calcs
        merge_old_calcs(q,q['historic_calcs'],match_asset)
    persist(q);record_event(id,actor(request)['username'],'AGREEMENT_RENEWAL_IMPORT',f'{filename}: {len(parsed["assets"])} equipment lines; old quoted total {c.get("previous_total","")}')
    return {**public(q),'import_report':{**parsed['report'],'warnings':parsed['warnings'],'added':len(parsed['assets'])}}

@app.post('/api/quotes/{id}/old-calcs-import')
async def import_old_calcs(id:str,request:Request):
    """Attach an original .xls/.xlsx maintenance calculation to a renewal.

    Prices from an old calculation are evidence, NOT modern catalogue RRPs.
    """
    from historical_calcs import parse_old_calcs,merge_old_calcs
    q=getq(id);payload=await request.json();filename=str(payload.get('filename',''))
    if not filename.lower().endswith(('.xls','.xlsx')):
        raise HTTPException(400,'Select a historic Pulse maintenance calculation in XLS or XLSX format.')
    with _lock:
        con=conn()
        issued=con.execute('SELECT 1 FROM quote_versions WHERE quote_id=? LIMIT 1',(id,)).fetchone()
        con.close()
    if issued:raise HTTPException(409,'This quotation has already been issued. Create a new quotation to import historical calculations.')
    encoded=payload.get('content_base64','')
    if len(encoded)>43*1024*1024:raise HTTPException(413,'Old calculations file too large.')
    try:
        raw=base64.b64decode(encoded,validate=True)
        parsed=parse_old_calcs(filename,raw)
        report=merge_old_calcs(q,parsed,match_asset)
    except ValueError as e:raise HTTPException(400,str(e))
    except Exception as e:raise HTTPException(400,'Unable to read historic calculations: '+str(e))
    q['warnings']+=parsed['warnings']
    persist(q)
    record_event(id,actor(request)['username'],'HISTORIC_CALCS_IMPORT',
      f"{filename}: {report['matched']} matched, {report['added']} created; original £{report['historic_total']}")
    return {**public(q),'import_report':{**report,'warnings':parsed['warnings'],
             'formula':'Historic equipment charges × 120% × 110% × 110% (source-specific; not automatically reused for renewal)'}}

@app.put('/api/quotes/{id}')
async def save(id:str,request:Request):
 q=getq(id);data=await request.json()
 allowed={'customer','site','contact','contact_email','prepared_by','billing_address','delivery_address','customer_ref','account_ref','contract_ref','valid_days','tier','term','visits','discount','approval_note','renewal_option_checked'}
 for k,v in data.items():
  if k in allowed:q[k]=v
 if q['tier'] not in PRICING['tiers']:raise HTTPException(400,'Unknown package')
 q['level']='Standard'
 try:
  if not (0<=float(q['discount'])<=60):raise ValueError()
  if not (1<=int(q['term'])<=5):raise ValueError()
  if not (0<=int(q['visits'])<=12):raise ValueError()
  if not (1<=int(q['valid_days'])<=180):raise ValueError()
 except:raise HTTPException(400,'Check discount (0-60%), term (1-5 years), and visits (0-12).')
 q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
 result=public(persist(q));record_event(id,actor(request)['username'],'QUOTE_SETTINGS_UPDATED');return result
@app.get('/api/quotes/{id}/match-review/{aid}')
def match_review(id:str,aid:str):
    """Price-source candidates and source lineage; no automatic resolution."""
    q=getq(id)
    a=next((asset for asset in q['assets'] if asset['id']==aid),None)
    if a is None:raise HTTPException(404,'Equipment row not found')
    report=eng.review_candidates(a,limit=12)
    report['reviewed_match']=memory.recall(a,admin.revision())
    report['quick_price']=quick_guide.guide(a,q.get('tier','Gold'),q.get('discount',0),eng.PRICING['tiers'],{k:v['standard'] for k,v in eng.RATES.items()})
    report['legacy_rrp_policy']=hybrid.suggest(a,admin.revision())
    report['legacy_rrp_policy']=hybrid.suggest(a,admin.revision())
    # A displayed group is a view, never a new physical source record.
    pmap={line['id']:line['price'] for line in calc_quote(q)['lines']}
    group=next((g for g in grouped_assets(q['assets'],pmap) if aid in g['ids']),None)
    report['group']={'count':len(group['ids']) if group else 1,
                     'quantity':group['qty'] if group else a.get('qty',1),
                     'ids':group['ids'] if group else [aid],
                     'source_rows':group['source_rows'] if group else [a.get('source_row')],
                     'serials':group['serials'] if group else [a.get('serial','')]}
    report['already_priced']=pmap.get(aid) is not None
    return report


def _safe_csv(value):
    """Disable spreadsheet formula execution when a customer name is opened in Excel."""
    text=str(value if value is not None else '').replace('\r',' ').replace('\n',' ')
    return "'"+text if text.lstrip().startswith(('=','+','-','@','\t')) else text


@app.get('/api/quotes/{id}/matching-report.csv')
def matching_report(id:str):
    """One review line per display group, retaining all individual source rows."""
    q=getq(id);calc=calc_quote(q)
    prices={line['id']:line['price'] for line in calc['lines']}
    groups=grouped_assets(q['assets'],prices)
    columns=['Site','Source description','SKU in quote','Model','Console','Group rows',
             'Machine quantity','Current RRP','Annual group total','Pricing basis',
             'Matching status','Source row numbers','Original asset tags','Serial numbers',
             'Review action']
    stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(columns)
    for g in groups:
        a=g['representative'];sel=a.get('selected') or {};price=g.get('price')
        action=('Excluded — '+str(a.get('exclusion_reason') or 'confirm reason') if a.get('excluded') else
            'Confirm SKU and console against source product' if price and (sel.get('price_origin')=='calculated-estimate' or sel.get('approved') not in ('Approved','Authorised')) else
            'Review current RRP and console / select an exact equipment SKU' if not price else
            'Check pricing source before customer issue')
        values=[a.get('site',''),a.get('name',''),sel.get('sku') or a.get('code',''),a.get('model',''),
                a.get('console') or sel.get('console',''),len(g['ids']),g['qty'],
                sel.get('rrp') or '',price.get('annual') if price else '',
                price.get('basis') if price else 'Not priced',a.get('match_type',''),
                ', '.join(str(x) for x in g['source_rows'] if x is not None),
                ', '.join(x.get('asset_tag','') for x in g['assets'] if x.get('asset_tag')),
                ', '.join(g['serials']),action]
        writer.writerow([_safe_csv(x) for x in values])
    return Response(content='\ufeff'+stream.getvalue(),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="SmartQuote_{id[:16]}_Matching_Review.csv"'})

@app.get('/api/quotes/{id}/asset-register.csv')
def original_asset_register(id:str):
    """Lossless original import view: one physical source row per CSV line."""
    q=getq(id)
    raw_keys=set()
    for a in q['assets']:
        for cell in a.get('source_raw_columns',[]):
            if isinstance(cell,dict) and isinstance(cell.get('column_index'),int):
                raw_keys.add((cell['column_index'],str(cell.get('header') or '')))
    keys=sorted(raw_keys)
    prefix=['Source file/sheet','Excel/CSV source row','Site / customer','Quote asset ID',
            'Original asset tag','Original description','Imported SKU','Imported model',
            'Imported make','Original serial','Corrected serial','Active serial',
            'Installed date','Quantity','Matched SKU','Review status']
    cols=[f'Original column {n+1} - {header or "no heading"}' for n,header in keys]
    stream=io.StringIO(newline='');writer=csv.writer(stream)
    writer.writerow(prefix+cols)
    for a in q['assets']:
        sheet=a.get('source_sheet','')
        bycol={(cell['column_index'],str(cell.get('header') or '')):cell.get('value','')
               for cell in a.get('source_raw_columns',[]) if isinstance(cell,dict)
               and isinstance(cell.get('column_index'),int)}
        original=a.get('source_cells') or {}
        current=a.get('selected') or {}
        prefix_values=[sheet,a.get('source_row',''),a.get('site',''),a.get('id',''),
                       a.get('asset_tag',''),a.get('source_description',a.get('name','')),
                       original.get('code',''),original.get('model',''),original.get('make',''),
                       a.get('original_serial') or original.get('serial',''),
                       original.get('correct_serial',''),a.get('serial',''),
                       original.get('install_date',''),a.get('qty',1),current.get('sku',''),
                       a.get('match_type','')]
        writer.writerow([_safe_csv(x) for x in prefix_values + [bycol.get(k,'') for k in keys]])
    return Response(content='\ufeff'+stream.getvalue(),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="SmartQuote_{id[:16]}_Original_Asset_Register.csv"'})

@app.get('/api/quotes/{id}/bulk-review/queue')
def bulk_review_queue(id:str, offset:int=0, limit:int=30):
    """Read-only triage of unresolved equipment groups and suggested SKUs."""
    return bulk_review.queue(getq(id), admin.revision(), offset, limit)


@app.post('/api/quotes/{id}/bulk-review/preview')
async def bulk_review_preview(id:str, request:Request):
    """Preview the proposed impact without changing any quote records."""
    payload=await request.json()
    if not isinstance(payload,dict):raise HTTPException(400,'Review request must be an object.')
    try:
        _, summary=bulk_review.prepare(getq(id),admin.revision(),
                    payload.get('actions'),payload.get('token'))
        return summary
    except bulk_review.ReviewError as exc:
        raise HTTPException(409,str(exc))


@app.post('/api/quotes/{id}/bulk-review/apply')
async def bulk_review_apply(id:str, request:Request):
    """Atomically commit an explicitly confirmed and still-current batch."""
    payload=await request.json()
    if not isinstance(payload,dict):raise HTTPException(400,'Review request must be an object.')
    if payload.get('acknowledge') is not True:
        raise HTTPException(400,'Read the preview and confirm the machine choices first.')
    with _lock:
        try:
            changed, summary=bulk_review.prepare(getq(id),admin.revision(),
                         payload.get('actions'),payload.get('token'))
        except bulk_review.ReviewError as exc:
            raise HTTPException(409,str(exc))
        persist(changed)
        record_event(id,actor(request)['username'],'BULK_EQUIPMENT_REVIEW',
            f"Verified {summary['groups']} groups, {summary['source_rows']} source rows, "
            f"{summary['units']} units; catalogue SKUs " + ', '.join(
            x['sku'] for x in summary['changes']))
        return {**public(changed), 'batch_review':summary}


@app.get('/api/quotes/{id}/quick-price/{aid}')
def quick_price(id:str,aid:str):
    q=getq(id)
    a=next((x for x in q['assets'] if x['id']==aid),None)
    if a is None:raise HTTPException(404,'Equipment row not found')
    guidance=quick_guide.guide(a,q.get('tier','Gold'),q.get('discount',0),
              eng.PRICING['tiers'],{k:v['standard'] for k,v in eng.RATES.items()})
    return guidance or {'status':'NOT_FOUND','message':'No current-source RRP for this exact model family; send to the pricing manager.'}

@app.post('/api/quotes/{id}/quick-price')
async def apply_quick_price(id:str,request:Request):
    q=getq(id);payload=await request.json()
    aid=str(payload.get('asset_id') or '');a=next((x for x in q['assets'] if x['id']==aid),None)
    if a is None:raise HTTPException(404,'Equipment row not found')
    if a.get('excluded'):raise HTTPException(409,'Cannot price an excluded asset.')
    if a.get('selected') and a['selected'].get('price_origin')!='staff-guided-estimate':
        raise HTTPException(409,'This equipment already has a confirmed selection. Use Edit line to change it.')
    if payload.get('acknowledge_guide_only') is not True:
        raise HTTPException(400,'Confirm this is a non-approved draft guide before continuing.')
    standard_unconfirmed=payload.get('standard_unconfirmed') is True
    if payload.get('console_verified') is not True and not standard_unconfirmed:
        raise HTTPException(400,'Confirm the installed console status, or use the unverified standard-model draft option.')
    try:
        chosen,band,entry=quick_guide.picked(a,str(payload.get('example_sku','')).upper(),
            str(payload.get('console_key','')),q.get('tier','Gold'),q.get('discount',0),
            eng.PRICING['tiers'],{k:v['standard'] for k,v in eng.RATES.items()})
    except (ValueError,TypeError) as exc:raise HTTPException(400,str(exc))
    if standard_unconfirmed:
        baseline=chosen.get('standard_reference')
        if not baseline or str(payload.get('example_sku','')).upper()!=baseline['example_sku'] or str(payload.get('console_key',''))!='not-listed' or a.get('console'):
            raise HTTPException(400,'Only a qualifying model-AAA standard reference can be used without a confirmed console.')
        if payload.get('console_verified') is True:
            raise HTTPException(400,'Do not mark an unknown console as physically verified.')
    # The supplier master lists many finish/upholstery SKUs for identical machines.
    # Never claim that the chosen source example is the physical equipment SKU.
    source_reference=entry['example_sku']; model=chosen['model']; rrp=entry['rrp']
    rate_group='Treadmill / Elliptical' if chosen['rate_fraction']==eng.RATES['Treadmill / Elliptical']['standard'] else 'Standard Equipment'
    option={'sku':'','service_key':'','model':model,'name':a.get('name') or entry['example_name'],
      'console':band['label'] if band['key']!='not-listed' else 'Console not confirmed',
      'console_status':'unverified','rrp':rrp,'rate_group':rate_group,
      'price_origin':'staff-guided-estimate','eligible':'Estimate - approval required',
      'approved':'Not approved','pricing_rule':'Provisional 2026 source RRP and maintenance tariff',
      'console_pricing':1,'reference_sku':source_reference,
      'reason':'Family-level draft guidance: exact SKU and console not verified'}
    original=tuple(str(a.get(k,'')) for k in ('code','model','name','console','site'))
    items=[a]
    if payload.get('apply_to_similar') is True:
     items += [x for x in q['assets'] if x['id']!=a['id'] and not x.get('excluded')
       and not(x.get('selected') and x['selected'].get('price_origin')!='staff-guided-estimate')
       and tuple(str(x.get(k,'')) for k in ('code','model','name','console','site'))==original]
    for item in items:
     item['selected']=dict(option)
     item['match_type']='Standard family reference (console unconfirmed)' if standard_unconfirmed else 'Draft source RRP guide - configuration unverified'
     item['issues']=['Source-price guide only. Installed console and exact SKU unconfirmed; tariff requires pricing manager approval.']
     item['match_confidence']=0
     item['guide_reference']={'source':'2026 Master RRP','example_sku':source_reference,'console_key':band['key'],
         'rrp':rrp,'reviewed_by':actor(request)['username'],
         'standard_unconfirmed':standard_unconfirmed}
    q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
    result=public(persist(q))
    record_event(id,actor(request)['username'],'UNAPPROVED_RRP_GUIDE',
      f"Draft family {model}, reference {source_reference}, console band {band['key']}, "+
      f"RRP GBP {rrp}, {len(items)} source rows, console unconfirmed={standard_unconfirmed}; never customer-approved.")
    return result

@app.post('/api/quotes/{id}/resolve')
async def resolve(id:str,request:Request):
 q=getq(id);data=await request.json();aid=data.get('asset_id')
 asset=next((a for a in q['assets'] if a['id']==aid),None)
 if not asset:raise HTTPException(404,'Asset not found')
 option=data.get('option')
 if not isinstance(option,dict):raise HTTPException(400,'Please choose a catalogue option')
 sku=str(option.get('sku','')).upper();key=str(option.get('service_key','')).upper()
 if sku in DUPLICATE_CODES:raise HTTPException(400,'Duplicate catalogue SKU: contact data owner to resolve the conflicting records before issue.')
 if sku and sku in BY_SKU:chosen=live_catalogue_option(BY_SKU[sku],'Manually confirmed SKU')
 elif key in BY_KEY:chosen=config_option(BY_KEY[key],'Manually confirmed configuration')
 else:raise HTTPException(400,'Not present in authorised catalogue')
 # A retained mapping is identity evidence only, never automatic selection.
 # Save it BEFORE mutating quote assets so a conflicting memory rule does not
 # leave the quote half-updated. Only managers may curate this shared register.
 if data.get('remember_match') is True:
  if actor(request)['role'] not in ('manager','admin'):
   raise HTTPException(403,'Manager permission required to retain a reusable equipment identity.')
  try:
   memory.remember(asset,chosen.get('sku',''),actor(request)['username'],
                   data.get('review_evidence',''),admin.revision())
  except ValueError as e:raise HTTPException(409,str(e))
 original_identity=tuple(str(asset.get(f,'')) for f in ('name','code','model','console','site'))
 if not asset.get('imported_code'):asset['imported_code']=asset.get('code','')
 if not asset.get('imported_name'):asset['imported_name']=asset.get('name','')
 if chosen.get('sku') and chosen['sku'].upper() in BY_SKU:asset['code']=chosen['sku']
 if chosen.get('model'):asset['model']=chosen['model']
 if chosen.get('console_status')=='source' and chosen.get('console'):asset['console']=chosen['console']
 asset['selected']=chosen;asset['candidates']=[];asset['issues']=selection_issues(chosen)
 if asset.get('import_batch_id'):asset['import_reviewed']=True
 asset['match_type']='Reviewed catalogue choice';asset['match_confidence']=95
 if data.get('apply_to_similar') is True:
  for other in q['assets']:
   if other['id']==asset['id'] or other.get('excluded'):continue
   if tuple(str(other.get(f,'')) for f in ('name','code','model','console','site'))!=original_identity:continue
   other['imported_name']=other.get('imported_name') or other.get('name','')
   other['imported_code']=other.get('imported_code') or other.get('code','')
   other['selected']=dict(chosen);other['match_type']='Bulk-confirmed matching equipment'
   if other.get('import_batch_id'):other['import_reviewed']=True;other['match_confidence']=95
   other['issues']=selection_issues(chosen)
   if chosen.get('sku'):other['code']=chosen['sku']
   if chosen.get('model'):other['model']=chosen['model']
   if chosen.get('console_status')=='source' and chosen.get('console'):other['console']=chosen['console']
 q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
 result=public(persist(q));record_event(id,actor(request)['username'],'EQUIPMENT_RESOLVED',f"Asset {aid} selected SKU {chosen.get('sku')}");return result
@app.put('/api/quotes/{id}/assets/{aid}')
async def edit_asset(id:str,aid:str,request:Request):
 q=getq(id);data=await request.json();asset=next((a for a in q['assets'] if a['id']==aid),None)
 if not asset:raise HTTPException(404,'Asset not found')
 # Validate before mutating; any identity edit rematches against the source catalogue.
 if 'qty' in data:
  try:
   qty=int(data['qty'])
   if not 1<=qty<=10000:raise ValueError()
  except:raise HTTPException(400,'Quantity must be a whole number from 1 to 10,000.')
 if 'manual_annual_unit' in data:
  raw=data['manual_annual_unit']
  if raw is None or str(raw).strip()=='':manual=None
  else:
   try:
    manual=float(raw)
    if not 0<manual<=1000000:raise ValueError()
   except:raise HTTPException(400,'Enter a positive annual unit price up to £1,000,000, or clear the manual rate.')
 if 'excluded' in data and not isinstance(data['excluded'],bool):raise HTTPException(400,'Invalid include/exclude setting.')
 # Contract notes are group-scoped for matching physical machines at the same
 # site. Never cross site, model, console, selection, excluded state or cost.
 def note_key(row):
  selected=row.get('selected') or {}
  return tuple(str(row.get(k,'')).strip().casefold() for k in ('site','code','model','name','console','make','manual_annual_unit','excluded','contract_note'))+(str(selected.get('sku','')).upper(),str(selected.get('reference_sku','')).upper())
 same_note_key=note_key(asset)
 identity_changed=any(str(data.get(f,asset.get(f,''))).strip()!=str(asset.get(f,'')).strip() for f in ('code','model','console','name','make'))
 if identity_changed:
  if not asset.get('imported_code'):asset['imported_code']=asset.get('code','')
  if not asset.get('imported_name'):asset['imported_name']=asset.get('name','')
  for f in ('code','model','console','name','make'):
   if f in data:asset[f]=str(data[f])[:250].strip()
  asset.update(match_asset(asset))
 for f in ('serial','site','display_name','contract_note','manual_price_source','exclusion_reason'):
  if f in data:asset[f]=str(data[f])[:500].strip()
 if data.get('note_to_same_group') is True and 'contract_note' in data and not identity_changed:
  for other in q['assets']:
   if other is not asset and note_key(other)==same_note_key:
    other['contract_note']=asset.get('contract_note','')
 if 'qty' in data:
  asset['qty']=qty;asset['qty_issue']='' 
 if 'manual_annual_unit' in data:asset['manual_annual_unit']=manual
 if 'excluded' in data:asset['excluded']=data['excluded']
 # A documented manual price is deliberately not an auto-catalogue approval.
 if asset.get('import_batch_id'):asset['import_reviewed']=True
 q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
 result=public(persist(q));record_event(id,actor(request)['username'],'EQUIPMENT_EDITED',f'Asset {aid}');return result
@app.delete('/api/quotes/{id}/assets/{aid}')
def delete_asset(id:str,aid:str,request:Request):
 q=getq(id);q['assets']=[a for a in q['assets'] if a['id']!=aid]
 q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
 result=public(persist(q));record_event(id,actor(request)['username'],'EQUIPMENT_DELETED',f'Asset {aid}');return result
@app.get('/api/catalog/search')
def catalog_search(q:str='',limit:int=20):
    results=search_products(q,max(1,min(limit,40)))
    for option in results:
        prices={}
        for tier in ('Silver','Gold','Platinum'):
            priced=price_line({'qty':1,'selected':option},'Standard',tier,0)
            prices[tier]=round(priced['unit']/12,2) if priced and not option.get('duplicate_sku') else None
        option['monthly_packages']=prices
        option['pricing_warning']= ('Conflicting duplicate SKU — fix in Catalogue Manager'
            if option.get('duplicate_sku') else
            'Calculated maintenance estimate — confirm category and eligibility' if option.get('price_origin')=='calculated-estimate'
            else 'Mapped maintenance rate — subject to source price approval')
    return {'results':results,'historical':eng.search_historical(q,limit=12),'basis':'Monthly equipment cost, 12-month equivalent, workbook standard tariff, pre-discount, ex VAT. Calculated estimates are shown and can be quoted without a separate review step.'}
@app.post('/api/quotes/{id}/approve')
async def legacy_approval(id:str,request:Request):
 # Removed in V5: no manual review step is needed to quote a valid, priced machine.
 raise HTTPException(410,'The extra approval step has been removed. Save the quote and choose Generate Quote PDF.')

@app.get('/api/quotes/{id}/pdf')
def pdf(id:str):
 q=getq(id)
 q['pilot_only']=os.getenv('SMARTQUOTE_LIVE_APPROVED')!='1'
 try:doc=create_quote_pdf(q)
 except Exception as e:raise HTTPException(500,'PDF generation failed: '+str(e))
 code=re.sub(r'[^a-zA-Z0-9-]','',q['quote_no'])
 return Response(doc,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="Pulse_Fitness_{code}_{"QUOTE" if calc_quote(q)["ready"] else "DRAFT"}.pdf"'})
@app.post('/api/quotes/{id}/manual')
async def add_manual(id:str,request:Request):
 q=getq(id);v=await request.json();sku=str(v.get('sku','')).strip().upper()
 # Unknown/duplicate codes can be recorded for review, never silently priced.
 try:
  qty=int(v.get('qty',1))
  assert 1<=qty<=1000
 except:raise HTTPException(400,'Quantity must be 1-1,000')
 s=(BY_SKU.get(sku) if sku not in DUPLICATE_CODES else None) or {}
 for field in ('name','model','make','console','serial'):
  if len(str(v.get(field,'')))>250:raise HTTPException(400,'Machine details are too long')
 a={'id':'manual_'+uuid.uuid4().hex[:12],'source_sheet':'Manual entry','source_row':'Manual','code':sku,
 'name':s.get('name') or str(v.get('name','')).strip(),
 'model':s.get('model') or str(v.get('model','')).strip(),
 'console':s.get('console') or str(v.get('console','')).strip(),
 'make':str(v.get('make','')).strip() or ('Pulse Fitness' if sku and not re.search(r'Concept2|Technogym|Life Fitness',s.get('name',''),re.I) else ''),
 'qty':qty,'serial':str(v.get('serial','')).strip(),'site':q.get('site',''),'original_qty':str(qty)}
 q['assets'].append(match_asset(a));q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
 result=public(persist(q));record_event(id,actor(request)['username'],'EQUIPMENT_ADDED',f"Manual SKU {sku or 'Unidentified'}");return result


# V4: catalogue management. This local pilot has no identity authentication;
# edits and inferred pricing must not be treated as formal company approval.
@app.get('/api/catalog/history/{identifier:path}')
def historical_catalogue_lookup(identifier:str):
    if not identifier or len(identifier)>80:raise HTTPException(400,'Enter a short equipment code or model.')
    result=eng.historical_identity(identifier)
    return result or {'lookup':identifier,'variant_count':0,'evidence_only':True,'variants':[],
                      'message':'No corresponding historical master identity found; do not infer an RRP.'}

@app.get('/api/catalog/admin/matching-memory')
def matching_memory_list():
    rules=memory.all_rules()
    return {'rules':rules,'active':sum(x['status']=='active' for x in rules),
            'notice':'Human-reviewed identity crosswalk; never auto-applied, never a source of authorised RRP.'}

@app.post('/api/catalog/admin/matching-memory/{rule_id}/revoke')
async def matching_memory_revoke(rule_id:str,request:Request):
    data=await request.json()
    try:return memory.revoke(rule_id,actor(request)['username'],data.get('reason',''))
    except ValueError as ex:raise HTTPException(400,str(ex))


def _pending_quote_payloads():
    with _lock:
        c=conn()
        records=c.execute('SELECT payload FROM quotes WHERE id NOT IN '
             '(SELECT DISTINCT quote_id FROM quote_versions) ORDER BY updated DESC LIMIT 500').fetchall()
        c.close()
    result=[]
    for record in records:
        try:
            q=json.loads(record['payload'])
            if q.get('assets'):
                result.append(getq(q['id']) if q.get('catalogue_revision',0)!=admin.revision() else q)
        except (KeyError,ValueError,TypeError,HTTPException):continue
    return result


@app.get('/api/catalog/admin/matching-gaps')
def matching_gaps():
    return analyse_gaps(_pending_quote_payloads())

@app.get('/api/catalog/admin/matching-gaps.csv')
def matching_gaps_csv():
    result=analyse_gaps(_pending_quote_payloads())
    columns=[('quote_no','Quote'),('customer','Customer'),('site','Site'),
             ('source_name','Original description'),('source_code','Original code'),
             ('model','Model'),('console','Console'),('units','Units'),
             ('source_rows','Asset rows'),('issue','Required action'),
             ('quote_id','Quote ID'),('representative_asset_id','Asset ID')]
    stream=io.StringIO(newline='');writer=csv.writer(stream)
    writer.writerow([title for _,title in columns])
    for item in result['items']:
        writer.writerow([_safe_csv(item.get(key,'')) for key,_ in columns])
    return Response(content='\ufeff'+stream.getvalue(),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':'attachment; filename="Pulse_SmartQuote_Missing_Equipment_Worklist.csv"'})


@app.get('/api/catalog/admin/hybrid-rrp')
def hybrid_rrp_register():
    return {'policy': hybrid.POLICY, 'rules': hybrid.rules(),
            'notice': 'Approved pricing basis does not approve any individual RRP, model, console, tariff or customer quotation.'}

@app.post('/api/catalog/admin/hybrid-rrp/propose')
async def propose_hybrid_rrp(request:Request):
    if actor(request)['role'] not in ('manager','admin'):
        raise HTTPException(403,'Manager permissions required for legacy RRP reviews.')
    payload=await request.json()
    try:
        return hybrid.propose(payload,actor(request)['username'],admin.revision())
    except ValueError as e:raise HTTPException(400,str(e))

@app.post('/api/catalog/admin/hybrid-rrp/{rule_id}/approve')
async def approve_hybrid_rrp(rule_id:str,request:Request):
    if actor(request)['role'] not in ('manager','admin'):
        raise HTTPException(403,'Manager permissions required for legacy RRP reviews.')
    payload=await request.json()
    if payload.get('acknowledge') is not True:
        raise HTTPException(400,'Confirm that the original evidence, machine, console and price have been independently checked.')
    try:
        return hybrid.approve(rule_id,actor(request)['username'],admin.revision(),payload.get('note',''))
    except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/catalog/admin/hybrid-rrp/{rule_id}/revoke')
async def revoke_hybrid_rrp(rule_id:str,request:Request):
    if actor(request)['role'] not in ('manager','admin'):
        raise HTTPException(403,'Manager permissions required for legacy RRP reviews.')
    payload=await request.json()
    try:
        return hybrid.revoke(rule_id,actor(request)['username'],payload.get('reason',''))
    except ValueError as e:raise HTTPException(409,str(e))

# Source-derived RRP evidence. Not an instruction to change live catalogue prices.
def _rrp_2026_rows():
    return rrp2026.reconcile(eng.CAT, eng.DUPLICATE_CODES)

@app.get('/api/catalog/admin/rrp-2026/summary')
def rrp_2026_summary():
    return rrp2026.summary(_rrp_2026_rows())

@app.get('/api/catalog/admin/rrp-2026/search')
def rrp_2026_search(q:str='',status:str='',offset:int=0,limit:int=30):
    try:return rrp2026.search(_rrp_2026_rows(),q,status,offset,limit)
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/catalog/admin/rrp-2026/family/{model}')
def rrp_2026_family(model:str):
    try:return rrp2026.family(_rrp_2026_rows(),model)
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/catalog/admin/rrp-2026/reconciliation.csv')
def rrp_2026_reconciliation_csv():
    return Response(rrp2026.export_csv(_rrp_2026_rows()),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':'attachment; filename="SmartQuote_2026_RRP_Reconciliation_Review.csv"'})

@app.get('/api/catalog/rrp-evidence')
def rrp_2026_equipment_search(q:str='',limit:int=12):
    if len(q.strip())<2:return {'total':0,'items':[],'notice':'Enter a product code or model to see unapproved source evidence.'}
    result=rrp2026.search(_rrp_2026_rows(),q,'',0,min(20,max(1,limit)))
    return {'total':result['total'], 'items':[
        {'sku':x['sku'],'model':x['model'],'name':x['name'],'console':x['console'],
         'source_rrp':x['source_rrp'],'status':x['status'],'source_prices':x['source_prices']}
        for x in result['items']],
        'notice':'2026 source RRP reference only. Not an approved quotation price or a verified replacement console.'}

@app.get('/api/catalog/admin/readiness')
def catalog_readiness():
    return evaluate_readiness(ROOT, PRICING)

@app.get('/api/catalog/admin/info')
def catalog_info():
    entries=len(CAT);dupes=len(DUPLICATE_CODES)
    estimated=sum(1 for p in CAT if live_catalogue_option(p).get('price_origin')=='calculated-estimate')
    return {'rows':entries,'unique_skus':len(eng.BY_SKU),'duplicate_sku_count':dupes,'estimate_rows':estimated,'revision':admin.revision(),'groups':list(eng.RATES),'note':'Local, unauthenticated pilot. Catalogue edits require company data-owner verification.'}

@app.get('/api/catalog/admin/item/{sku:path}')
def get_catalogue_item(sku:str):
    if sku.upper() not in eng.BY_SKU:raise HTTPException(404,'Item code not found')
    return {'item':eng.BY_SKU[sku.upper()],'pricing':live_catalogue_option(eng.BY_SKU[sku.upper()]),'conflict':sku.upper() in DUPLICATE_CODES}

@app.put('/api/catalog/admin/item/{sku:path}')
async def change_catalogue_item(sku:str,request:Request):
    payload=await request.json();item=payload.get('item') or {}
    if str(item.get('sku','')).upper()!=sku.upper():raise HTTPException(400,'Item code cannot be renamed. Create a new item with a different code.')
    try:
        with _lock:
            updated=admin.save_item(item,actor(request)['username'],payload.get('reason',''))
        return {'item':updated,'revision':admin.revision(),'message':'Item changed in the local catalogue. Open quotes will be recalculated and approvals invalidated.'}
    except ValueError as ex:raise HTTPException(400,str(ex))

@app.post('/api/catalog/admin/item')
async def create_catalogue_item(request:Request):
    payload=await request.json();item=payload.get('item') or {}
    if eng.upper(item.get('sku')) in eng.BY_SKU:raise HTTPException(409,'This item code exists. Use Edit to change it.')
    try:
        with _lock:
            updated=admin.save_item(item,actor(request)['username'],payload.get('reason',''))
        return {'item':updated,'revision':admin.revision()}
    except ValueError as ex:raise HTTPException(400,str(ex))

@app.post('/api/catalog/admin/import/preview')
async def catalogue_preview(request:Request):
    payload=await request.json();filename=str(payload.get('filename',''))
    try:
        content=base64.b64decode(payload.get('content_base64',''),validate=True)
        with _lock: result=admin.stage(filename,content)
        return result
    except Exception as ex:raise HTTPException(400,str(ex))

@app.post('/api/catalog/admin/import/apply')
async def catalogue_apply(request:Request):
    payload=await request.json()
    if not isinstance(payload,dict):raise HTTPException(400,'Review request must be an object.')
    if payload.get('acknowledge') is not True:raise HTTPException(400,'Confirm that the import preview has been reviewed.')
    try:
        with _lock:return admin.apply_stage(str(payload.get('stage_id','')),actor(request)['username'],payload.get('reason',''))
    except Exception as ex:raise HTTPException(400,str(ex))

@app.get('/api/catalog/admin/export.csv')
def export_catalogue():
    return Response(admin.as_csv(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="Pulse_SmartQuote_Catalogue_Managed.csv"'})

@app.get('/api/catalog/admin/audit')
def audit_catalogue(limit:int=35):
    c=admin.db();r=c.execute('SELECT sku,modified,operator,reason FROM catalogue_audit ORDER BY modified DESC LIMIT ?',(max(1,min(limit,100)),)).fetchall();c.close()
    return {'history':[dict(x) for x in r]}


def record_event(quote_id,who,action,note=''):
    with _lock:
        c=conn()
        c.execute('INSERT INTO quote_events VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,quote_id,datetime.datetime.now(datetime.timezone.utc).isoformat(),who,action,str(note)[:2000]))
        c.commit();c.close()

@app.post('/api/quotes/{id}/issue')
def issue_pdf(id:str,request:Request):
    q=getq(id);status=calc_quote(q)
    if not status['ready']:raise HTTPException(422,'Cannot issue an incomplete quotation. Resolve missing equipment prices and required details first.')
    who=actor(request)['username']
    pilot=os.getenv('SMARTQUOTE_LIVE_APPROVED')!='1'
    snap=json.loads(json.dumps(q))
    snap['issued_at']=datetime.date.today().isoformat()
    snap['pilot_only']=pilot
    snap['issued_by']=who
    def fingerprint(x):
        # Skip operational timestamps and derived metadata; retain all commercial inputs.
        return {k:v for k,v in x.items() if k not in ('updated','status','pricing_approved','line_reviews_approved','approver','approval_note','issued_by')}
    with _lock:
        c=conn()
        last=c.execute('SELECT version,payload,pdf,pdf_sha256 FROM quote_versions WHERE quote_id=? ORDER BY version DESC LIMIT 1',(id,)).fetchone()
        if last and fingerprint(json.loads(last['payload']))==fingerprint(snap):
            # Repeat download of the same quote; do not inflate the version register.
            if hashlib.sha256(last['pdf']).hexdigest()!=last['pdf_sha256']:
                c.close();raise HTTPException(409,'Archived PDF integrity check failed. Contact IT.')
            c.close()
            code=re.sub(r'[^a-zA-Z0-9-]','',q['quote_no'])
            suffix='PILOT' if pilot else 'QUOTE'
            return Response(last['pdf'],media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="Pulse_Fitness_{code}_v{last["version"]}_{suffix}.pdf"','X-Quote-Version':str(last['version']),'X-PDF-SHA256':last['pdf_sha256']})
        c.close()
    content=create_quote_pdf(snap)
    digest=hashlib.sha256(content).hexdigest()
    with _lock:
        c=conn()
        nextversion=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM quote_versions WHERE quote_id=?',(id,)).fetchone()[0]
        c.execute('INSERT INTO quote_versions VALUES (?,?,?,?,?,?,?,?)',(id,nextversion,datetime.datetime.now(datetime.timezone.utc).isoformat(),who,'Pilot snapshot' if pilot else 'Issued',json.dumps(snap,ensure_ascii=False),content,digest))
        c.commit();c.close()
    record_event(id,who,'SNAPSHOT_CREATED',f'Version {nextversion}; SHA-256 {digest}')
    code=re.sub(r'[^a-zA-Z0-9-]','',q['quote_no'])
    suffix='PILOT' if pilot else 'QUOTE'
    return Response(content,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="Pulse_Fitness_{code}_v{nextversion}_{suffix}.pdf"','X-Quote-Version':str(nextversion),'X-PDF-SHA256':digest})

@app.get('/api/quotes/{id}/versions')
def quote_versions(id:str):
    getq(id)
    c=conn();r=c.execute('SELECT version,created,actor,status,pdf_sha256 FROM quote_versions WHERE quote_id=? ORDER BY version DESC',(id,)).fetchall();c.close()
    return {'versions':[dict(x) for x in r]}

@app.get('/api/quotes/{id}/versions/{version}/pdf')
def historical_quote(id:str,version:int):
    getq(id)
    c=conn();r=c.execute('SELECT pdf, pdf_sha256 FROM quote_versions WHERE quote_id=? AND version=?',(id,version)).fetchone();c.close()
    if not r:raise HTTPException(404,'Issued version not found.')
    if hashlib.sha256(r['pdf']).hexdigest()!=r['pdf_sha256']:raise HTTPException(409,'The stored PDF does not match its original integrity hash. Contact IT.')
    return Response(r['pdf'],media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="Pulse_SmartQuote_v{version}.pdf"','X-PDF-SHA256':r['pdf_sha256']})

@app.get('/api/quotes/{id}/history')
def quote_history(id:str):
    getq(id)
    c=conn();r=c.execute('SELECT timestamp,actor,action,note FROM quote_events WHERE quote_id=? ORDER BY timestamp DESC LIMIT 100',(id,)).fetchall();c.close()
    return {'events':[dict(x) for x in r]}

# Local commercial pipeline recording; does not send email or create contracts.
PIPELINE_STATES={'Draft','Sent externally','Accepted','Declined','Expired'}

@app.post('/api/quotes/{id}/pipeline')
async def update_pipeline(id:str,request:Request):
    q=getq(id);data=await request.json()
    stage=str(data.get('pipeline_status',''))
    if stage not in PIPELINE_STATES:raise HTTPException(400,'Unsupported commercial status.')
    note=str(data.get('note','')).strip()[:600]
    if stage!='Draft' and len(note)<6:raise HTTPException(400,'Include a short source or reason for the status change.')
    q['pipeline_status']=stage
    q['pipeline_note']=note
    q['pipeline_updated']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    result=public(persist(q))
    record_event(id,actor(request)['username'],'PIPELINE_'+stage.upper().replace(' ','_'),note)
    return result

@app.get('/api/reporting/summary')
def reporting_summary():
    c=conn()
    records=c.execute('SELECT payload FROM quotes').fetchall()
    archive=c.execute('SELECT quote_id,version,status FROM quote_versions').fetchall()
    c.close()
    quotes=[json.loads(x[0]) for x in records]
    states={stage:sum(q.get('pipeline_status','Draft')==stage for q in quotes) for stage in sorted(PIPELINE_STATES)}
    # Prefer immutable saved quote values rather than live catalogue revaluations.
    c=conn();verified=0;accepted_with_snapshot=0
    for q in quotes:
        if q.get('pipeline_status')!='Accepted':continue
        archived=c.execute('SELECT payload FROM quote_versions WHERE quote_id=? ORDER BY version DESC LIMIT 1',(q['id'],)).fetchone()
        if archived:
            verified+=calc_quote(json.loads(archived[0]))['annual'];accepted_with_snapshot+=1
    c.close()
    value=verified
    return {'total_quotes':len(quotes),'pipeline':states,'pilot_snapshots':sum(x['status']=='Pilot snapshot' for x in archive),'issued_versions':sum(x['status']=='Issued' for x in archive),'recorded_accepted_annual':eng.money(value),'accepted_with_pdf_snapshot':accepted_with_snapshot,'note':'Local manual pipeline data only; acceptance and sales are not verified against Sage/Sicon.'}

@app.get('/api/reporting/quotes.csv')
def reporting_export():
    import io,csv
    buf=io.StringIO();writer=csv.writer(buf)
    writer.writerow(['Quote','Customer','Site','Tier','Annual ex VAT','Status','Commercial stage','Created','Updated','Revision'])
    c=conn();r=c.execute('SELECT payload FROM quotes ORDER BY updated DESC').fetchall();c.close()
    def safe(v):
        s=str(v or '')
        return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
    for (raw,) in r:
        q=json.loads(raw);summary=calc_quote(q)
        writer.writerow([safe(q.get('quote_no')),safe(q.get('customer')),safe(q.get('site')),safe(q.get('tier')),summary['annual'],safe(q.get('status')),safe(q.get('pipeline_status','Draft')),safe(q.get('created')),safe(q.get('updated')),q.get('catalogue_revision',0)])
    return Response(buf.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="Pulse_SmartQuote_Register.csv"'})

@app.get('/api/customers/suggest')
def customer_suggest(q:str='',limit:int=8):
    query=eng.descslug(q)
    if len(query)<2:return {'customers':[]}
    c=conn();records=c.execute('SELECT payload FROM quotes ORDER BY updated DESC LIMIT 700').fetchall();c.close()
    customers=[];seen=set()
    for r in records:
        x=json.loads(r['payload']);name=eng.neat(x.get('customer'))
        if not name or query not in eng.descslug(name):continue
        key=(eng.descslug(name),eng.descslug(x.get('site')))
        if key in seen:continue
        seen.add(key)
        customers.append({k:x.get(k,'') for k in ('customer','site','contact','contact_email','billing_address','delivery_address','account_ref')})
        if len(customers)>=max(1,min(limit,20)):break
    return {'customers':customers}

# V7 local administration; enterprise rollout must use centrally managed identity.
@app.get('/api/users')
def users_list(request:Request):
    return {'users':security.list_users()}

@app.post('/api/users')
async def users_create(request:Request):
    data=await request.json()
    try:user=security.create_user(str(data.get('username','')),str(data.get('password','')),str(data.get('role','coordinator')))
    except ValueError as e:raise HTTPException(400,str(e))
    return {'ok':True,'username':user}

@app.put('/api/users/{username}/status')
async def users_status(username:str,request:Request):
    data=await request.json();active=data.get('active')
    if not isinstance(active,bool):raise HTTPException(400,'Specify active true or false.')
    try:security.set_user_status(username,active,actor(request)['username'])
    except ValueError as e:raise HTTPException(400,str(e))
    return {'users':security.list_users()}

@app.put('/api/users/{username}/password')
async def users_reset(username:str,request:Request):
    data=await request.json()
    try:security.reset_password(username,str(data.get('password','')))
    except ValueError as e:raise HTTPException(400,str(e))
    return {'ok':True}
