"""Read-only importer for legacy Pulse Fitness maintenance calculation worksheets.

The original 2025 `.xls` contains cached formula values. We extract the
historic cost basis, but do NOT import its prices into the approved live
catalogue. A historic RRP is NOT a present-day sales RRP.
"""
from __future__ import annotations
import re,io,datetime
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from legacy_biff import xls_dump


def money(x):
 return float(Decimal(str(x)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
def amount(x):
 try:
  if x is None or isinstance(x,str) and x.startswith('[FORMULA_'):return None
  return float(str(x).replace(',','').replace('£',''))
 except (TypeError,ValueError):return None

def get_rows(filename,content):
 ext=Path(filename).suffix.lower()
 if ext=='.xls':
  # A strictly read-only parser. No Excel macros or embedded content are run.
  import tempfile,os
  with tempfile.NamedTemporaryFile(suffix='.xls',delete=False) as t:
   t.write(content);path=t.name
  try:
   sheets,_,_=xls_dump(path)
  finally:os.unlink(path)
  return [(k,{(r,c):v for (r,c),v in sheet.items()}) for k,sheet in sheets.items()]
 if ext=='.xlsx':
  from engine import parse_xlsx
  out=[]
  for name,records in parse_xlsx(content):
   cells={(r['_rownum'],int(k)+1):v for r in records for k,v in r.items() if isinstance(k,int)}
   out.append((name,cells))
  return out
 raise ValueError('Upload a previous Pulse calculations spreadsheet in .xls or .xlsx format.')

def parse_old_calcs(filename,content):
 if len(content)>30*1024*1024:raise ValueError('Old calculations sheet exceeds 30 MB.')
 all_sheets=get_rows(filename,content)
 best=None
 for sheet,cells in all_sheets:
  header=' '.join(str(cells.get((7,i),'')) for i in range(1,14)).lower()
  if 'unit maint' not in header and 'annual maintenance' not in header:continue
  lines=[]
  for r in range(8,350):
   code=str(cells.get((r,5),'')).strip()
   desc=str(cells.get((r,6),'')).strip()
   qty=amount(cells.get((r,7)))
   rrp=amount(cells.get((r,1)))
   percent=amount(cells.get((r,3)))
   if not code or code.startswith('[SST') or not desc or not qty or qty<1 or not rrp or rrp<=0 or percent is None:continue
   if not re.match(r'^[A-Za-z0-9._/\- ]{2,35}$',code):continue
   if not (0<percent<=50) or qty>1000:continue
   if abs(qty-round(qty))>.001:continue
   unit=amount(cells.get((r,2)))
   total=amount(cells.get((r,4)))
   calc=rrp*percent/100
   # Explicitly preserve unexpected historic overrides, but never silently
   # convert them into present-day approved customer rates.
   lines.append({'source_sheet':sheet,'source_row':r,'code':code,'description':desc,'qty':int(qty),'historic_rrp':money(rrp),
                 'historic_percent':percent,'historic_annual_unit':money(unit if unit is not None else calc),
                 'historic_line_annual':money(total if total is not None else calc*qty),'historic_line_annual_raw':float(total if total is not None else calc*qty),
                 'formula_variance':money((unit if unit is not None else calc)-calc)})
  if lines and (best is None or len(lines)>len(best[1])):best=(sheet,lines,cells)
 if best is None:raise ValueError('This spreadsheet does not contain the expected Pulse RRP / Unit Maintenance / Part No. / Quantity calculation table.')
 name,lines,cells=best
 raw_cache=amount(cells.get((346,7)))
 raw_total=sum(Decimal(str(x['historic_line_annual_raw'])) for x in lines)
 original=money(raw_cache if raw_cache is not None else raw_total)
 first_month=amount(cells.get((350,10)))
 final_month=amount(cells.get((350,13)))
 final_annual=money(final_month*12) if final_month is not None else None
 first_annual=money(first_month*12) if first_month is not None else None
 # Do not infer uplift as package multipliers: this sheet references
 # two separate 10% increases, not Gold/Platinum pricing tiers.
 notes=' | '.join(str(cells.get((r,10),'')).strip() for r in range(1,7) if cells.get((r,10)))
 warnings=[]
 if abs(float(raw_total)*1.20-float(original))>.20:warnings.append('Historic annual calculation does not match 120% of the equipment subtotal; inspect source formula.')
 if len(lines)<2:warnings.append('Only one historic equipment line found; confirm calculation worksheet selection.')
 for ln in lines:
  if abs(ln['formula_variance'])>.02:warnings.append(f"Source calculation override for {ln['code']}; historic unit amount differs from RRP x rate.")
 return {'filename':filename,'sheet':name,'lines':lines,'line_count':len(lines),'machine_count':sum(l['qty'] for l in lines),
         'original_base_annual':original,'source_line_sum':money(raw_total),'source_line_sum_unrounded':float(raw_total),'historic_source_overhead_multiplier':1.20,'first_adjusted_annual':first_annual,
         'previous_quote_annual':final_annual,'source_notes':notes,'warnings':warnings,
         'pricing_basis':'Historical RRP and percentage; NOT a current sales-price list',
         'historic_calc_adjustments': 'Source sums equipment charges, multiplies by 120%, then applies two successive 10% increases (source formula). Reason for original 20% uplift requires commercial verification; do not assume VAT.'}

def attach_historic(asset,ln,filename):
 asset.update({'historic_rrp':ln['historic_rrp'],'historic_rate_percent':ln['historic_percent'],
               'historic_annual_unit':ln['historic_annual_unit'],'historic_line_annual':ln['historic_line_annual'], 'historic_special_annual':money(ln['historic_annual_unit']-ln['historic_rrp']*ln['historic_percent']/100),
               'historic_source_file':filename,'historic_source_row':ln['source_row']})
 return asset

def codekey(s):return re.sub(r'[^A-Z0-9]','',str(s).upper())
def merge_old_calcs(quote,parsed,match_function):
 existing=quote.get('assets',[])
 had_existing=bool(existing)
 unmatched=[];matched=0;added=0
 bycode={}
 for a in existing:bycode.setdefault(codekey(a.get('code','')),[]).append(a)
 used=set()
 for ln in parsed['lines']:
  entries=bycode.get(codekey(ln['code']),[])
  current=next((a for a in entries if a['id'] not in used),None)
  if current is not None:
   used.add(current['id']);matched+=1
   attach_historic(current,ln,parsed['filename'])
  elif had_existing:
   unmatched.append(ln['code'])
  else:
   import uuid
   asset={'id':'historic_'+uuid.uuid4().hex[:12],'source_sheet':parsed['sheet'],
          'source_row':ln['source_row'],'prior_contract_ref':quote.get('contract_ref','') or 'LEGACY_CALCS',
          'code':ln['code'],'name':ln['description'],'model':ln['code'].split('-')[0],
          'qty':ln['qty'],'serial':'','site':quote.get('site',''),'original_qty':str(ln['qty'])}
   attach_historic(asset,ln,parsed['filename'])
   quote['assets'].append(match_function(asset));added+=1
 quote['historic_calcs']={key:val for key,val in parsed.items()}
 quote.setdefault('files',[]).append({'filename':parsed['filename'],'type':'historic-calculations','imported':len(parsed['lines']),
                                      'at':datetime.datetime.now().isoformat(timespec='seconds')})
 return {'matched':matched,'added':added,'unmatched_codes':unmatched,'source_lines':len(parsed['lines']),
         'historic_total':parsed['previous_quote_annual'],'historic_base':parsed['original_base_annual']}
