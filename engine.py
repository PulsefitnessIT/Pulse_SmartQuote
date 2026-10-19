"""Pulse Fitness SmartQuote - deterministic local quoting core.
All prices/names are source-derived snapshots. No AI is permitted to invent a price.
"""
from __future__ import annotations
import base64,csv,difflib,io,json,os,re,zipfile,xml.etree.ElementTree as ET
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from collections import Counter
from functools import lru_cache
from renewal_pricing import family_reference
from asset_intelligence import normalize_asset, grouped_assets

ROOT=Path(__file__).parent
CAT=json.loads((ROOT/'data/catalog.json').read_text())
CONFIG=json.loads((ROOT/'data/configs.json').read_text())
LEGACY=json.loads((ROOT/'data/legacy.json').read_text())
PRICING=json.loads((ROOT/'data/pricing.json').read_text())
HISTORIC_MASTER=json.loads((ROOT/'data/2025_master_legacy_index.json').read_text())
# V10 historical evidence never modifies live catalogue RRPs or tariffs.
_HISTORIC_V10_PATH=ROOT/'data/historical_catalogue_index.json'
HISTORIC_V10=json.loads(_HISTORIC_V10_PATH.read_text(encoding='utf-8')) if _HISTORIC_V10_PATH.exists() else {'records':{},'aliases':{}}
HISTORIC_V10_RECORDS=HISTORIC_V10.get('records',{})
HISTORIC_V10_ALIASES=HISTORIC_V10.get('aliases',{})
HISTORIC_V10_MODELS={}
for _history_code,_history_item in HISTORIC_V10_RECORDS.items():
 _history_model=str(_history_item.get('model','')).strip().upper()
 if _history_model and _history_model not in ('N/A','0'):
  HISTORIC_V10_MODELS.setdefault(_history_model,[]).append(_history_code)

def historical_identity(code='',model='',limit=8):
 """Return recorded historical identity evidence; never approved pricing."""
 code=str(code or '').strip().upper()
 model=str(model or '').strip().upper()
 direct=HISTORIC_V10_RECORDS.get(code)
 source='Exact historical SKU' if direct else ''
 matches=[code] if direct else []
 if not matches and code in HISTORIC_V10_ALIASES:
  matches=HISTORIC_V10_ALIASES[code]
  source='Historical alias - NOT an approved replacement'
 if not matches and (model or code) in HISTORIC_V10_MODELS:
  matches=HISTORIC_V10_MODELS[model or code]
  source='Model family - multiple variants may exist'
 total=len(matches)
 if not total:return None
 results=[]
 for key in matches[:limit]:
  item=HISTORIC_V10_RECORDS.get(key,{})
  results.append({f:item.get(f,'') for f in ('sku','name','model','console','status','year','first_seen','source')})
 return {'lookup':code or model,'basis':source,'variant_count':total,
         'ambiguous':total>1,'evidence_only':True,'variants':results,
         'message':'Historical identity evidence only. No RRP, tariff or replacement approved.'}

def search_historical(query,limit=12):
 """Fuzzy historical identity discovery without promoting unapproved RRPs."""
 term=upper(query)
 if len(term)<2:return {'results':[],'total':0,'evidence_only':True}
 direct=historical_identity(term,limit=limit)
 if direct:
  return {'results':direct['variants'],'total':direct['variant_count'],
          'basis':direct['basis'],'evidence_only':True,'ambiguous':direct['ambiguous']}
 match=descslug(term)
 ranked=[]
 for sku,item in HISTORIC_V10_RECORDS.items():
  code=upper(sku);model=upper(item.get('model',''))
  description=descslug(item.get('name',''))
  if term in code:score=500 if code.startswith(term) else 350
  elif model==term:score=450
  elif match and match in description:score=200+min(50,len(match))
  else:continue
  ranked.append((score,sku,item))
 ranked.sort(key=lambda x:(-x[0],x[1]))
 result=[{field:item.get(field,'') for field in ('sku','model','name','console','year','first_seen','source','status')}
         for _,_,item in ranked[:limit]]
 return {'results':result,'total':len(ranked),
         'basis':'Historical catalogue search — identity only, unapproved for pricing',
         'evidence_only':True,'ambiguous':False}


BY_SKU={p['sku'].upper():p for p in CAT}
ALL_SKUS={}
for _product in CAT:ALL_SKUS.setdefault(_product['sku'].upper(),[]).append(_product)
DUPLICATE_CODES={k:v for k,v in ALL_SKUS.items() if len(v)>1}
BY_KEY={p['key'].upper():p for p in CONFIG}
BY_MODEL={}
for c in CONFIG:BY_MODEL.setdefault(c['model'].upper(),[]).append(c)
BY_LEGACY={}
for l in LEGACY:
 for f in ('old_code','old_sku'):
  if l[f] and l[f] not in ('6','25','0','N/A'):
   BY_LEGACY.setdefault(l[f].upper(),[]).append(l)
RATES={r['group']:r for r in PRICING['rates']}
CONSOLES={r['name']:r for r in PRICING['console_rules']}

def money(x):return float(Decimal(str(x)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
def neat(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def celltext(s):return str(int(s)) if isinstance(s,float) and s.is_integer() else neat(s)
def upper(s):return neat(s).upper()
def descslug(s):return re.sub(r'[^a-z0-9]+',' ',neat(s).lower()).strip()
def blank(x):return x is None or (isinstance(x,str) and not x.strip())
def num(x,default=1):
 try:
  n=float(str(x).replace(',','').replace('£','').strip())
  return n if n>0 and n<100000 else default
 except: return default

M='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
def colnum(r):
 n=0
 for c in re.match(r'[A-Z]+',r or '').group(0):n=n*26+ord(c)-64
 return n-1

def parse_xlsx(data:bytes):
 """Pure stdlib XLSX reader. Reads values (not untrusted Excel formulas/macros)."""
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  names=set(z.namelist())
  if 'xl/workbook.xml' not in names:raise ValueError('This is not a valid .xlsx workbook.')
  wb=ET.fromstring(z.read('xl/workbook.xml'))
  rel=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
  refs={v.attrib['Id']:v.attrib['Target'] for v in rel}
  ss=[]
  if 'xl/sharedStrings.xml' in names:
   with z.open('xl/sharedStrings.xml') as f:
    for _,e in ET.iterparse(f,events=('end',)):
     if e.tag==M+'si':
      ss.append(''.join(t.text or '' for t in e.iter(M+'t')));e.clear()
  output=[]
  for sheet in wb.find(M+'sheets'):
   target=refs.get(sheet.attrib.get(R+'id'),'')
   path=target.lstrip('/') if target.startswith('/') else 'xl/'+target
   if path not in names:continue
   records=[]
   with z.open(path) as fh:
    for ev,el in ET.iterparse(fh,events=('end',)):
     if el.tag!=M+'row':continue
     vals={}
     for c in el.findall(M+'c'):
      a=c.attrib.get('r','A1'); t=c.attrib.get('t',''); v=c.find(M+'v')
      if t=='inlineStr': val=''.join(x.text or '' for x in c.iter(M+'t'))
      elif v is None:continue
      else:
       val=v.text or ''
       if t=='s':
        try:val=ss[int(val)]
        except:val=''
       elif t not in ('str','e'):
        try:val=float(val)
        except:pass
      if not blank(val):vals[colnum(a)]=str(val) if not isinstance(val,(str,int,float)) else val
     if vals:
      vals['_rownum']=int(el.attrib.get('r','0'));records.append(vals)
     el.clear()
     if len(records)>15000:raise ValueError('Please split asset lists above 15,000 non-empty rows.')
   output.append((sheet.attrib['name'],records))
  return output

def parse_csv(data:bytes):
 try:s=data.decode('utf-8-sig')
 except:s=data.decode('cp1252',errors='replace')
 try:d=csv.Sniffer().sniff(s[:4096],delimiters=',;\t|')
 except:d=csv.excel
 reader=csv.reader(io.StringIO(s),dialect=d)
 return [('Imported CSV',[{**{i:v for i,v in enumerate(row) if neat(v)},'_rownum':ri} for ri,row in enumerate(reader,start=1) if any(neat(v) for v in row)])]

HEADERS={
 'code':['model code','itemcode','productcode','sku','product code','stock code','item code','asset code','equipment code','product id','sage code','resale code','stock item code','part number'],
 'name':['name','equipment description','asset description','item description','equipment name','machine description','description','equipment','asset name','machine','product name','item','product'],
 'model':['model number','model no','model','machine model','equipment model'],
 'make':['make','manufacturer','brand','supplier'],
 'qty':['quantity','qty','no of','units','number of units','count','number','amount'],
 'serial':['serialnumber','serial number','serial no','serial numbers','serial','s n','serials'],
 'console':['console type','console','screen','display'],
 'site':['site name','site','facility'],
 'location':['location','site location','facility location'],
 'note':['notes','repair','status','warranty','remarks'],
 'install_date':['install date','installation date','date installed'],
 'correct_serial':['correct serial number','correct serial','verified serial number'],
}
def normalized_header(s):return descslug(str(s).replace('\n',' '))
def head_key(s):
 s=normalized_header(s)
 for k,variants in HEADERS.items():
  if s in variants:return k
 return None

def ingest(name:str,content:bytes):
 if len(content)>25*1024*1024:raise ValueError('This prototype accepts files up to 25 MB. Split larger customer asset registers.')
 ext=Path(name).suffix.lower()
 if ext=='.xlsx':sheets=parse_xlsx(content)
 elif ext in ('.csv','.tsv','.txt'):sheets=parse_csv(content)
 elif ext in ('.xls','.xlk','.xlsm'):raise ValueError('Legacy Excel or macro-enabled format detected. Export a copy to .xlsx or .csv before importing; originals stay unchanged.')
 else:raise ValueError('Please upload an .xlsx or .csv asset list.')
 assets=[];warnings=[];meta=[]
 for sheet,records in sheets:
  if not records:continue
  opts=[]
  for ix,r in enumerate(records[:40]):
   h={head_key(v):c for c,v in r.items() if head_key(v)}
   weight=len(h)+(2 if 'name' in h or 'code' in h or 'model' in h else 0)
   if weight>=3:opts.append((weight,ix,h))
  if opts:
   _,start,h=sorted(opts,reverse=True)[0]
   mode='Detected column headings'
  else:
   # Do not guess which column is a price, model or serial on an unstructured sheet.
   warnings.append(f'{sheet}: No recognisable asset headings. Please add columns such as Equipment, Qty and Model/SKU.')
   meta.append({'sheet':sheet,'rows':len(records),'added':0,'detected':False})
   continue
  start_added=len(assets)
  for ix,r in enumerate(records[start+1:],start+2):
   val={k:celltext(r.get(c,'')) for k,c in h.items()}
   if not any(val.get(k) for k in ('code','model','name')):continue
   if re.search(r'^(grand total|subtotal|total|vat|summary|equipment list|product code|sku)$',val.get('name',''),re.I):continue
   rawqty=val.get('qty','')
   quantity_issue=''
   try:
    if rawqty=='':
     quantity=1
     # One row with its own serial number is normally one individual machine.
     quantity_issue='' if val.get('serial') else 'Quantity missing and no serial number; confirm it is one.'
    else:
     quantity_decimal=Decimal(str(rawqty).replace(',','').strip())
     if not quantity_decimal.is_finite() or quantity_decimal!=quantity_decimal.to_integral_value() or not (1<=quantity_decimal<=10000):raise ValueError()
     quantity=int(quantity_decimal)
   except (ValueError,ArithmeticError):
    quantity=1  # UI placeholder only — quote generation is blocked until corrected
    quantity_issue=f'Imported quantity {rawqty!r} is invalid. Please enter the actual equipment quantity.'
   if quantity_issue:warnings.append(f'{sheet} row {r.get("_rownum",ix)}: {quantity_issue}')
   if len(assets)>=2000:raise ValueError('Limit of 2,000 equipment lines per quotation; split multi-site imports.')
   location=val.get('location','')
   site_status=val.get('site','')
   if location and site_status:
    site=(site_status.removeprefix('Relocated to ').strip() if re.match(r'(?i)^relocated to\s+',site_status) else
          location if site_status.lower() in ('n/a','na','-') or 'warranty' in site_status.lower() or 'agreement' in site_status.lower() else site_status)
   else:site=location or site_status
   assets.append(normalize_asset({'id':f'a{len(assets)+1:04d}','source_sheet':sheet,'source_row':r.get('_rownum',ix),'code':val.get('code',''), 'model':val.get('code','') or val.get('model',''), 'name':val.get('name',''), 'make':val.get('make',''), 'console':val.get('console',''), 'serial':val.get('serial',''),'site':site, 'source_location':location, 'site_status':site_status,'source_note':val.get('note',''), 'qty':quantity,'original_qty':rawqty,'qty_issue':quantity_issue,'install_date':val.get('install_date',''),
                    'correct_serial':val.get('correct_serial','')}))
  meta.append({'sheet':sheet,'rows':len(records),'added':len(assets)-start_added,'detected':True,'columns':list(h)})
 if not assets:raise ValueError('No usable equipment rows were detected. Check the spreadsheet headings and select the correct sheet.')
 return {'file':name,'assets':assets,'warnings':warnings,'sheets':meta}

# V4: explainable catalogue-wide maintenance estimates. Values are calculated from
# actual source RRPs and workbook tariffs; estimates are NOT authorised prices.
# Console multipliers remain 1.0 unless approved tariff data explicitly provides otherwise.
def infer_rate_group(product):
    model=upper(product.get('model'))
    candidates=[c for c in BY_MODEL.get(model,[]) if c.get('rate_group') in RATES and c.get('rate_group')!='Manual Review']
    groups={c['rate_group'] for c in candidates}
    if len(groups)==1:
        return next(iter(groups)),'Model family', 'High'
    name=descslug(product.get('name','')+' '+product.get('group','')+' '+product.get('category',''))
    if 'stepmill' in name or 'stairmaster' in name or 'stair climber' in name: return 'Stepmill','Equipment type: StepMill','Medium'
    if 'fluid' in name and ('rower' in name or 'rowing' in name):return 'Fluid Rower','Equipment type: Fluid Rower','Medium'
    if 'fluid' in name and any(w in name for w in ('ube','recumbent')):return 'Fluid UBE / Recumbent','Equipment type: Fluid UBE/recumbent','Medium'
    if any(w in name for w in ('treadmill','cross trainer','cross-trainer','elliptical')):return 'Treadmill / Elliptical','Equipment type: cardio','Medium'
    # Third-party machines are deliberately put through manual eligibility review.
    if any(w in name for w in ('concept2','concept 2','technogym','life fitness','wattbike','matrix','stairmaster')):
        return 'Concept2 / Third Party','Named third-party manufacturer','Low'
    return 'Standard Equipment','Default equipment tariff','Low'

def live_catalogue_option(raw,reason='Catalogue SKU'):
    option=sku_option(raw,reason)
    if raw.get('rate_group_override') in RATES:
        option['rate_group']=raw['rate_group_override']
        option['pricing_rule']='Approved register rate-group override'
        option['estimate_confidence']='High'
    elif not option.get('rate_group') or option.get('rate_group')=='Manual Review':
        group,basis,conf=infer_rate_group(raw)
        option['rate_group']=group
        option['pricing_rule']=basis
        option['estimate_confidence']=conf
    else:
        option['pricing_rule']='Source service configuration'
        option['estimate_confidence']='High'
    source_mapped=raw.get('match')!='Price list only - review' and option.get('eligible')=='Yes'
    approved_override=raw.get('coverage_override')=='Approved for maintenance' and bool(raw.get('rate_group_override'))
    option['price_origin']=('approved-register' if approved_override else ('mapped' if source_mapped else 'calculated-estimate'))
    option['eligible']='Yes' if source_mapped or approved_override else 'Estimate - approval required'
    option['approved']='Data owner approved override' if approved_override else option.get('approved','Unmapped')
    option['console_pricing']=float(raw.get('console_multiplier_override') or 1)
    option['coverage_status']=raw.get('coverage_override') or ''
    if raw.get('coverage_override')=='Not eligible':option['eligible']='No'
    return option

def refresh_source_indexes():
    if "search_products" in globals():search_products.cache_clear()
    global BY_SKU, ALL_SKUS, DUPLICATE_CODES
    BY_SKU.clear(); BY_SKU.update({v['sku'].upper():v for v in CAT})
    ALL_SKUS.clear()
    for v in CAT:ALL_SKUS.setdefault(v['sku'].upper(),[]).append(v)
    DUPLICATE_CODES.clear();DUPLICATE_CODES.update({k:v for k,v in ALL_SKUS.items() if len(v)>1})

def update_catalogue(item):
    """Apply a vetted catalogue register edit in memory, preserving source snapshot."""
    code=upper(item['sku'])
    CAT[:]=[p for p in CAT if upper(p['sku'])!=code]
    CAT.append(item)
    refresh_source_indexes()

def sku_option(s,reason='Exact SKU'):
 c=BY_KEY.get(upper(s.get('service_key')))
 return decorate_option({'sku':s['sku'],'name':s['name'],'model':s['model'],'console':s['console'],'rrp':s.get('rrp'),'service_key':s.get('service_key'), 'rate_group':c.get('rate_group') if c else None, 'eligible':c.get('eligible') if c else 'Review','approved':c.get('approval') if c else 'Unmapped','match':s.get('match'),'reason':reason})

def config_option(c,reason='Model matching'):
 return decorate_option({'sku':c['reference_sku'] or '', 'name':c['name'],'model':c['model'],'console':c['console'],'rrp':c.get('override') or c.get('reference_rrp'),'service_key':c['key'],'rate_group':c['rate_group'],'eligible':c['eligible'],'approved':c['approval'],'match':c['match_quality'],'reason':reason,'spread':c['rrp_spread']})

# Display-console recovery is for presentation only: it never changes the
# underlying approved service configuration or price calculation.
def display_console(product):
    source=neat(product.get('console'))
    if source and source!='No Console / N/A':
        return {'label':source,'status':'source'}
    description=neat(product.get('name'))
    patterns=[
        (r'(18\.5[\"″]?).{0,35}(?:Cirrus V4|Touchscreen)', '18.5" Cirrus V4 Touchscreen Console'),
        (r'(10\.1[\"″]?).{0,35}(?:Cirrus V4|Touchscreen)', '10.1" Cirrus V4 Touchscreen Console'),
        (r'(10\.1[\"″]?).{0,35}Tactile Key', '10.1" Tactile Key Console'),
        (r'(7[\"″]?).{0,35}Tactile Key', '7" Tactile Key Console'),
        (r'PM5\s+Console|PM5\b', 'PM5 Console'),
    ]
    for pattern,label in patterns:
        if re.search(pattern,description,re.I):
            return {'label':label,'status':'description_only'}
    if re.search(r'\bconsole\b|\btouchscreen\b',description,re.I):
        return {'label':'Console mentioned - type unconfirmed','status':'description_only'}
    return {'label':'Not specified in source','status':'unknown'}

def decorate_option(option):
    info=display_console(option)
    option['console_display']=info['label']
    option['console_status']=info['status']
    option['duplicate_sku']=bool(option.get('sku') and option['sku'].upper() in DUPLICATE_CODES)
    return option

@lru_cache(maxsize=2048)
def search_products(query,limit=20):
    """Description-first search, not just SKU-prefix matching.
    Advisory matches only: duplicate codes stay blocked from auto-issue.
    """
    exact_code=upper(query)
    if exact_code in ALL_SKUS:
        return [live_catalogue_option(item,'Exact SKU search - confirm description') for item in ALL_SKUS[exact_code]][:limit]
    q=descslug(query)
    if len(q)<2:return []
    aliases={'rowing':'rower','rowing machine':'rower','cross trainer':'cross-trainer',
      'spin bike':'group cycle','exercise bike':'bike','spinning':'group cycle',
      'stair climber':'stepmill','stepper':'stepmill','weight rack':'storage rack',
      'running machine':'treadmill','ergometer':'erg'}
    for k,v in aliases.items():
        if k in q:q=q.replace(k,v)
    words=[w for w in q.split() if w not in {'pulse','fitness','machine','equipment','please','unknown','the','a','with','old','existing','original','model','code','product','make','manufacturer'}]
    if not words:return []
    query_clean=' '.join(words)
    ranked=[]
    for item in CAT:
        name=descslug(item.get('name'))
        code=descslug(item.get('sku'))
        model=descslug(item.get('model'))
        score=0
        if query_clean==code:score=1200
        elif query_clean==model:score=950
        elif code.startswith(query_clean):score=830
        elif query_clean in name:score=700+min(len(query_clean),30)
        elif query_clean in code or query_clean in model:score=600
        else:
            hits=sum(1 for w in words if w in name.split() or w in code or w==model)
            if hits==0:continue
            score=hits*85 + int(difflib.SequenceMatcher(None,query_clean,name).ratio()*90)
            if len(words)>1 and hits==1:score-=80
        if score:
            if item['sku'].upper() in DUPLICATE_CODES:score-=30
            ranked.append((score,item))
    ranked.sort(key=lambda t:(-t[0],len(descslug(t[1]['name'])),t[1]['name'],t[1]['sku']))
    # Diversify description suggestions: avoid pages of almost identical variants.
    if any(w in query_clean for w in ('rower','bike','rack','stepmill','treadmill')) and len(query_clean)<18:
        diverse=[];seen=set()
        for score,item in ranked:
            family=(item['model'],descslug(item['name'])[:37])
            if family in seen:continue
            seen.add(family);diverse.append((score,item))
            if len(diverse)>=limit:break
        ranked=diverse
    return [live_catalogue_option(item,'Catalogue search - confirm exact variant') for score,item in ranked[:limit]]

def suggest_unknown(asset,limit=5):
    values=[neat(asset.get(k)) for k in ('name','make','model') if neat(asset.get(k))]
    if not values:return []
    query=' '.join(values)
    opts=search_products(query,limit=limit)
    # If source has an unmatched obsolete identifier, recommend by description,
    # not by a guessed replacement part number.
    if not opts and asset.get('name'):opts=search_products(asset['name'],limit=limit)
    return [{**o,'reason':'Suggested from text - verify exact machine and console before selection',
       'recommendation':'Possible match, not confirmed'} for o in opts]

def score_name(name,p):
 return difflib.SequenceMatcher(None,descslug(name),descslug(p['name'])).ratio()

def match_asset(a):
 code=upper(a.get('code'));model=upper(a.get('model'));desc=neat(a.get('name'));console=upper(a.get('console'))
 out={**a,'selected':None,'candidates':[],'issues':[],'match_type':'Unmatched','match_confidence':0}
 if code and code in DUPLICATE_CODES:
  out['match_type']='Conflicting duplicate SKU';out['match_confidence']=0
  out['issues'].append('This SKU appears more than once in the source catalogue. Ask the data owner to confirm the correct product/RRP before quoting.')
 elif code and code in BY_SKU:
  s=BY_SKU[code];out['selected']=live_catalogue_option(s);out['match_type']='Exact SKU';out['match_confidence']=100
 elif code and code in BY_LEGACY:
  matches=BY_LEGACY[code];
  variants=[]
  for m in matches:
   if m['new_sku'].upper() in BY_SKU:variants.append(live_catalogue_option(BY_SKU[m['new_sku'].upper()],'Legacy crosswalk'))
   elif m['service_key'].upper() in BY_KEY:variants.append(config_option(BY_KEY[m['service_key'].upper()],'Legacy service match'))
  uniq={v['sku']+'|'+v['service_key']:v for v in variants}
  if len(uniq)==1:out['selected']=next(iter(uniq.values()))
  else:out['candidates']=list(uniq.values())[:8]
  out['match_type']='Legacy code';out['match_confidence']=90 if out['selected'] else 70
 elif code and code in BY_MODEL:
  model=code
 if not out['selected'] and not out['candidates'] and code not in DUPLICATE_CODES:
  if not model and desc:
   m=re.search(r'\b([0-9]{3}[A-Z](?:-[A-Z])?)\b',desc,re.I)
   if m:model=m.group(1).upper()
  opts=BY_MODEL.get(model,[]) if model else []
  if opts:
   if console:
    direct=[c for c in opts if upper(c['console'])==console or upper(c['series'])==console]
    if len(direct)==1:out['selected']=config_option(direct[0],'Model + console');out['match_type']='Model + console';out['match_confidence']=83
   # A genuinely unique legacy model can be mapped safely when its name also agrees,
   # but never when the prior agreement mentions a different/unverified console.
   if not out['selected'] and len(opts)==1 and not console and desc and (score_name(desc,opts[0])>=.65 or (model and descslug(desc)==descslug(model) and len([p for p in CAT if upper(p.get('model'))==model])==1)):
    out['selected']=config_option(opts[0],'Unique model and description match')
    out['match_type']='Unique model configuration';out['match_confidence']=88
   if not out['selected']:
    out['candidates']=[config_option(c) for c in opts[:12]]
    out['match_type']='Model candidate';out['match_confidence']=60
  elif desc:
   # Narrow fuzzy search to model/description candidates. Advisory only, never auto-priced.
   tokens=set(descslug(desc).split());scored=[]
   for c in CONFIG:
    ratio=score_name(desc,c)
    if ratio>.49 or (tokens and set(descslug(c['name']).split()) & tokens and ratio>.36):scored.append((ratio,c))
   scored=sorted(scored,key=lambda z:-z[0])[:5]
   if scored:
    out['candidates']=[config_option(c, f'Possible description match ({round(ratio*100)}%)') for ratio,c in scored]
    out['match_type']='Description suggestion';out['match_confidence']=round(scored[0][0]*100)
 # Historic agreements give FAMILY codes (e.g. 305H), not exact SKUs.
 # Use a traceable RRP reference, preserving old code/description/serial.
 if not out['selected'] and code not in DUPLICATE_CODES and a.get('prior_contract_ref'):
  family=family_reference(a,CAT,DUPLICATE_CODES,infer_rate_group)
  if family is not None:
   out['selected']=family;out['candidates']=[]
   out['match_type']='Historic family RRP estimate'
   out['match_confidence']=65 if family['reference_model']==code else 45
   out['issues'].append('Historical equipment identity is not an exact current product SKU; verify the family/console against the existing machine.')
 if not out['selected'] and not out['candidates']:
  out['candidates']=suggest_unknown(a)
  if out['candidates']:
   if code not in DUPLICATE_CODES:out['match_type']='Suggested equipment - confirmation required'
   out['match_confidence']=0
 if not out['selected'] and out['candidates']:
  out['issues'].append('Suggested matches are possibilities only. Confirm the exact machine and console before applying a price.')
 elif not out['selected'] and code not in DUPLICATE_CODES:
  out['issues'].append('Equipment could not be identified. Enter the exact SKU or use manual review.')
 if out['selected']:out['issues']+=selection_issues(out['selected'])
 family_model=(model or code).split('-')[0].upper()
 evidence=historical_identity(code,model)
 if evidence:
  out['historic_evidence']=evidence
 if family_model in HISTORIC_MASTER:
  meta=HISTORIC_MASTER[family_model]
  out['historic_master']={'model':family_model,'variant_rows':meta['variant_rows'],
                           'consoles':meta['consoles'][:8],'sku_examples':meta['sku_examples'][:6],
                           'provenance':'2025 Master Input — Assembled Database (identity only; not current RRP)'}
 return out

def selection_issues(p):
 issues=[]
 if not isinstance(p.get('rrp'),(int,float)) or p['rrp']<=0:issues.append('No verified numerical RRP; pricing on hold.')
 if not p.get('rate_group') or p['rate_group']=='Manual Review':issues.append('No approved service rate group; manual quote needed.')
 if p.get('reason')=='Legacy service match':issues.append('Legacy code resolved to a model-level service configuration rather than a confirmed exact current SKU; commercial exception required.')
 if p.get('approved') not in ('Approved','Authorised'):issues.append('Price/configuration is provisional or held pending sign-off.')
 if p.get('eligible')!='Yes':issues.append('Calculated maintenance estimate; contract eligibility and category must be approved.')
 if p.get('match')=='Price list only - review':issues.append('Service configuration not mapped: the system uses an RRP-based estimate for review.')
 if p.get('spread',0) and p['spread']>.1:issues.append('Model/console family RRP spread exceeds 10%; use exact SKU.')
 group=p.get('rate_group')
 if group in RATES and RATES[group]['status']!='Active':issues.append('Pricing rate group requires approval.')
 return issues

def price_line(asset,level,tier,discount):
 if asset.get('excluded'):return None
 qty=max(1,int(asset.get('qty',1)))
 manual=asset.get('manual_annual_unit')
 if manual is not None and manual != '':
  try:
   unit=Decimal(str(manual))
   if unit<=0 or unit>Decimal('1000000'):return None
   discounted=unit*(Decimal('1')-Decimal(str(discount))/Decimal('100'))
   shown_unit=money(discounted)
   net=Decimal(str(shown_unit))*qty
   return {'unit':shown_unit,'annual':money(net),'minimum':money(0),'base_unit':money(unit),'rrp':None,'qty':qty,'rate':None,'manual':True,'basis':'manual','rule':'Evidence-backed annual unit rate before quotation discount'}
  except (ValueError,ArithmeticError):return None
 s=asset.get('selected')
 if not s and asset.get('historic_rrp') and asset.get('historic_rate_percent'):
  # Historical evidence can populate a comparison estimate, but is not a
  # verified current RRP and cannot make a customer quotation issue-ready.
  try:
   old=Decimal(str(asset['historic_rrp']))
   historic_rate=Decimal(str(asset['historic_rate_percent']))/Decimal('100')
   special=Decimal(str(asset.get('historic_annual_unit') or 0))-old*historic_rate
   raw=(old*historic_rate+special)*Decimal(str(PRICING['tiers'][tier]))
   unit=money(raw*(Decimal('1')-Decimal(str(discount))/Decimal('100')))
   return {'unit':unit,'annual':money(Decimal(str(unit))*qty),'minimum':0,'base_unit':money(raw),
           'rrp':money(old),'qty':qty,'rate':float(historic_rate),'basis':'historic-reference',
           'rule':'Historic RRP ONLY — update to current RRP before customer issue',
           'historic_special_annual':money(special)}
  except (ValueError,ArithmeticError):return None
 if not s or s.get('eligible')=='No' or not isinstance(s.get('rrp'),(int,float)) or s['rrp']<=0:return None
 rate=RATES.get(s.get('rate_group') or '')
 if not rate:return None
 base=float(s['rrp'])*float(rate.get(level.lower(),rate['standard']))
 console=CONSOLES.get(s.get('console',''),{'multiplier':1,'uplift':0}); console={**console, 'multiplier':float(s.get('console_pricing',console['multiplier']))}
 annualunit=(base*float(console['multiplier'])+float(console['uplift'])+rate['uplift'])*PRICING['tiers'][tier]
 unit=money(annualunit*(1-discount/100))
 line=unit*qty
 minimum=(float(s['rrp'])*rate['minimum']*float(console['multiplier'])+float(console['uplift'])+rate['uplift'])*PRICING['tiers'][tier]*qty
 return {'unit':unit,'annual':money(line),'minimum':money(minimum),'base_unit':money(base),'rrp':money(s['rrp']),'qty':qty,'rate':rate.get(level.lower(),rate['standard']),'basis':s.get('price_origin','mapped'),'rule':s.get('pricing_rule','Source tariff')}

def calc_quote(q):
 """Fast coordinator flow: accurate, complete lines are immediately quotable.

 A source-derived estimate is informative, not a mandatory second approval.
 Truly missing prices, below-minimum discounts, or unsupported PPM scope
 remain blockers. Source issues remain attached to assets for traceability.
 """
 level='Standard';tier=q.get('tier','Gold');discount=float(q.get('discount') or 0)
 if tier not in PRICING['tiers']:tier='Gold'
 discount=max(0,min(100,discount))
 term=max(1,min(5,int(q.get('term') or 1)))
 summary={'rows':0,'units':0,'priced_rows':0,'excluded_rows':0,'annual':0,'monthly':0,'term_total':0,'issues':[],'advisories':[],'estimated_rows':0,'ready':False,'tier':tier,'level':level,'discount':discount,'term':term,'lines':[]}
 rows=q.get('assets',[]);summary['rows']=len(rows)
 for a in rows:
  if a.get('excluded'):
   summary['excluded_rows']+=1
   if len(neat(a.get('exclusion_reason')))<5:
    summary['issues'].append(f"Row {a.get('source_row','?')}: excluded line requires a short reason")
   summary['lines'].append({'id':a.get('id'),'price':None,'issues':[],'excluded':True})
   continue
  qty=int(a.get('qty',1));summary['units']+=qty
  if a.get('qty_issue'):
   summary['issues'].append(f"Row {a.get('source_row','?')}: {a['qty_issue']}")
  price=price_line(a,level,tier,discount)
  if price:summary['annual']+=price['annual'];summary['priced_rows']+=1
  manual=a.get('manual_annual_unit') is not None and a.get('manual_annual_unit')!=''
  if manual:
   if len(neat(a.get('manual_price_source')))<12:
    summary['issues'].append(f"Row {a.get('source_row','?')}: enter a source/reference for the manual rate")
   if not neat(a.get('name') or a.get('display_name')) or not (neat(a.get('code')) or neat(a.get('model'))):
    summary['issues'].append(f"Row {a.get('source_row','?')}: manual rate needs a description and code/model")
  elif price and price.get('basis')=='historic-reference':
   summary['estimated_rows']+=1
   summary['issues'].append(f"Row {a.get('source_row','?')}: £{a['historic_rrp']:,.2f} RRP is historical only; confirm a current RRP or approved renewal rate before issuing.")
  elif not a.get('selected'):
   summary['issues'].append(f"Row {a.get('source_row','?')}: choose a machine or enter a sourced manual price")
  elif not price:
   summary['issues'].append(f"Row {a.get('source_row','?')}: no usable price for this machine")
  else:
   selected=a['selected']
   if selected.get('price_origin') in ('calculated-estimate','historic-family-estimate'):
    summary['estimated_rows']+=1
    if selected.get('price_origin')=='historic-family-estimate':
     summary['advisories'].append(f"Row {a.get('source_row','?')}: historic model {a.get('code')} has estimated pricing from current model {selected.get('reference_model')}, reference SKU {selected.get('reference_sku')} (not an exact equipment match)")
    else:
     summary['advisories'].append(f"Row {a.get('source_row','?')}: contract price calculated from RRP and equipment tariff")
   if a.get('match_type')=='Legacy code':
    summary['advisories'].append(f"Row {a.get('source_row','?')}: older equipment code mapped to a current product")
   if selected.get('console_status')=='description_only':
    summary['advisories'].append(f"Row {a.get('source_row','?')}: console inferred from product description")
  if price and price['annual']<price['minimum']-0.01:
   summary['issues'].append(f"Row {a.get('source_row','?')}: discount reduces price below configured minimum; reduce discount")
  summary['lines'].append({'id':a.get('id'),'price':price,'issues':a.get('issues',[])})
 summary['annual']=money(summary['annual']);summary['monthly']=money(summary['annual']/12);summary['term_total']=money(summary['annual']*term)
 if not neat(q.get('customer')) or not neat(q.get('site')):summary['issues'].append('Enter the customer and site.')
 visits=int(q.get('visits',1))
 if tier=='Silver' and visits!=0:summary['issues'].append('Silver does not include planned maintenance; select 0 PPM visits.')
 if tier!='Silver' and visits!=1:summary['issues'].append('The current tariff supports 1 PPM visit only; select 1 visit or agree a separate price.')
 unique_sites={descslug(a.get('site')) for a in rows if neat(a.get('site'))}
 if len(unique_sites)>1:summary['advisories'].append('Imported equipment appears to span more than one site; check the quote scope.')
 if not rows or summary['excluded_rows']==len(rows):summary['issues'].append('Include at least one machine.')
 renewal=q.get('renewal') or {}
 if renewal.get('fixed_price_extension'):
  summary['advisories'].append('Previous agreement contains an option to extend at the same annual price. Check contractual entitlement before substituting newly calculated prices.')
  if not q.get('renewal_option_checked'):summary['issues'].append('Existing agreement offers a same-price extension. Confirm the contract option has been checked before issuing a new quotation.')
 summary['ready']=not summary['issues'] and summary['priced_rows']==len(rows)-summary['excluded_rows']
 return summary

PACKAGES={
 'Silver': {'subtitle':'Essential breakdown support','highlights':['Technical call centre, online support and 24/7 portal','Call-out and labour support'], 'exclusions':'Preventative maintenance, major parts, organised response time, toolbox, software updates, consumables, treadmill beds and belts, upholstery, carriage and insurance.'},
 'Gold': {'subtitle':'Planned care and repair cover','highlights':['Call-out and labour','Preventative maintenance and major parts','Organised response time and toolbox','10% off wear-and-tear and aesthetic parts'], 'exclusions':'Treadmill beds and belts, wear-and-tear parts, upholstery, carriage and insurance.'},
 'Platinum': {'subtitle':'Most comprehensive package','highlights':['Full technical support and local service engineer','Preventative maintenance and associated training','Call-out, labour, major parts and wear-and-tear parts','Treadmill beds and belts, upholstery, priority response, software updates, carriage and insurance'], 'exclusions':'No package-specific exclusions are listed in the supplied package summary; general contractual exceptions (including misuse) still apply. Written approval of this wording is required.'}
}
