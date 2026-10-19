"""Pulse SmartQuote local pilot. NOT hardened for the public internet.
Run: python -m uvicorn main:app --host 127.0.0.1 --port 8765
"""
import base64,json,os,sqlite3,threading,uuid,datetime,re,hashlib
from io import BytesIO
import engine as eng
import catalogue_admin as admin
import security
from pathlib import Path
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse,FileResponse,Response,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from engine import ROOT,PRICING,PACKAGES,ingest,match_asset,calc_quote,selection_issues,BY_SKU,BY_KEY,DUPLICATE_CODES,CAT,CONFIG,sku_option,config_option,search_products,price_line,decorate_option,suggest_unknown,live_catalogue_option
from quote_pdf import create_quote_pdf
from agreement_import import read_agreement_pdf

app=FastAPI(title='Pulse Fitness SmartQuote',version='0.9.0',docs_url=None,redoc_url=None)

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
 return {'quote':q,'summary':calc_quote(q)}

@app.get('/')
def home():return FileResponse(ROOT/'static/index.html')
@app.get('/api/health')
def health():return {'ok':True,'name':'Pulse Fitness SmartQuote','mode':'local controlled pilot','version':'V9','auth_setup_required':security.enabled() and security.count()==0}
@app.get('/api/bootstrap')
def bootstrap():
 return {'source':PRICING['source'],'counts':PRICING['source_counts'],'tiers':PRICING['tiers'],'packages':PACKAGES,'rates':PRICING['rates'],'mode':'Local pilot with user sign-in; not a production identity provider'}
@app.get('/api/quotes')
def list_quotes():
 with _lock:
  c=conn();r=c.execute('SELECT id,quote_no,created,updated,status,payload FROM quotes ORDER BY updated DESC LIMIT 60').fetchall();c.close()
 out=[]
 for x in r:
  q=json.loads(x['payload']);s=calc_quote(q)
  out.append({'id':q['id'],'quote_no':q['quote_no'],'customer':q['customer'],'site':q['site'],'tier':q['tier'],'status':q['status'],'pipeline_status':q.get('pipeline_status','Draft'),'annual':s['annual'],'lines':s['rows'],'updated':q['updated']})
 return {'quotes':out}
@app.post('/api/quotes')
def create():return public(persist(defaults()))
@app.get('/api/quotes/{id}')
def load(id:str):return public(getq(id))
@app.post('/api/quotes/{id}/import')
async def upload(id:str,request:Request):
 q=getq(id)
 payload=await request.json();filename=payload.get('filename','')
 encoded=payload.get('content_base64','')
 if len(encoded)>82*1024*1024:raise HTTPException(413,'File is too large (60 MB maximum).')
 try:data=base64.b64decode(encoded,validate=True);parsed=ingest(filename,data)
 except Exception as e:raise HTTPException(400,str(e))
 if len(q['assets'])+len(parsed['assets'])>2000:raise HTTPException(400,'Maximum 2,000 asset rows per quotation.')
 existing={a['id'] for a in q['assets']};index=len(existing)
 for a in parsed['assets']:
  index+=1;a['id']=f'asset_{index}_{uuid.uuid4().hex[:6]}'
  q['assets'].append(match_asset(a))
 q['warnings']+=parsed['warnings']
 q['files'].append({'filename':filename,'sheets':parsed['sheets'],'imported':len(parsed['assets']),'at':datetime.datetime.now().isoformat(timespec='seconds')})
 q['pricing_approved']=False;q['line_reviews_approved']=False;q['approver']=''
 persist(q);record_event(id,actor(request)['username'],'ASSET_IMPORT',f"File {filename}, {len(parsed['assets'])} machine rows");return {**public(q),'import_report':{'files':parsed['sheets'],'warnings':parsed['warnings'],'added':len(parsed['assets'])}}
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
 original_identity=tuple(str(asset.get(f,'')) for f in ('name','code','model','console','site'))
 if not asset.get('imported_code'):asset['imported_code']=asset.get('code','')
 if not asset.get('imported_name'):asset['imported_name']=asset.get('name','')
 if chosen.get('sku') and chosen['sku'].upper() in BY_SKU:asset['code']=chosen['sku']
 if chosen.get('model'):asset['model']=chosen['model']
 if chosen.get('console_status')=='source' and chosen.get('console'):asset['console']=chosen['console']
 asset['selected']=chosen;asset['candidates']=[];asset['issues']=selection_issues(chosen)
 asset['match_type']='Reviewed catalogue choice';asset['match_confidence']=95
 if data.get('apply_to_similar') is True:
  for other in q['assets']:
   if other['id']==asset['id'] or other.get('excluded'):continue
   if tuple(str(other.get(f,'')) for f in ('name','code','model','console','site'))!=original_identity:continue
   other['imported_name']=other.get('imported_name') or other.get('name','')
   other['imported_code']=other.get('imported_code') or other.get('code','')
   other['selected']=dict(chosen);other['match_type']='Bulk-confirmed matching equipment';other['match_confidence']=95
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
 identity_changed=any(str(data.get(f,asset.get(f,''))).strip()!=str(asset.get(f,'')).strip() for f in ('code','model','console','name','make'))
 if identity_changed:
  if not asset.get('imported_code'):asset['imported_code']=asset.get('code','')
  if not asset.get('imported_name'):asset['imported_name']=asset.get('name','')
  for f in ('code','model','console','name','make'):
   if f in data:asset[f]=str(data[f])[:250].strip()
  asset.update(match_asset(asset))
 for f in ('serial','site','display_name','manual_price_source','exclusion_reason'):
  if f in data:asset[f]=str(data[f])[:500].strip()
 if 'qty' in data:
  asset['qty']=qty;asset['qty_issue']=''
 if 'manual_annual_unit' in data:asset['manual_annual_unit']=manual
 if 'excluded' in data:asset['excluded']=data['excluded']
 # A documented manual price is deliberately not an auto-catalogue approval.
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
    return {'results':results,'basis':'Monthly equipment cost, 12-month equivalent, workbook standard tariff, pre-discount, ex VAT. Calculated estimates are shown and can be quoted without a separate review step.'}
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
