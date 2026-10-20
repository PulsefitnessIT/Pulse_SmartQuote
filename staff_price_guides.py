"""Quick coordinator-facing guide prices from the dated 2026 RRP source.

Guide RRPs are evidence and never qualify as an approved catalogue price.
The suggested selection has NO confirmed SKU; its source SKU is an audit reference.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import re
from rrp_reconciliation import source

CONSOLES = {
 'Unspecified in price list':'not-listed',
 '7-inch cardio tactile-key':'7-key',
 '10.1-inch cardio tactile-key':'10-key',
 '10.1-inch cardio touchscreen':'10-touch',
 '18.5-inch cardio touchscreen':'18-touch',
}

def _clean(x):return str(x or '').strip()
def _money(x):return float(Decimal(str(x)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))

def _model(asset):
 for field in ('code','model'):
  text=_clean(asset.get(field)).upper()
  match=re.match(r'^([0-9]{3}[A-Z])(?:-[A-Z0-9]+)?$',text)
  if match:return match.group(1)
 # Avoid guessing a family from unrelated numbers in descriptions.
 return ''

def _console_band(value):
 val=_clean(value).lower()
 if not val or 'not stated' in val or 'unspecified' in val:return 'not-listed'
 if '18.5' in val:return '18-touch'
 if '10.1' in val and ('touchscreen' in val or 'touch screen' in val):return '10-touch'
 if '10.1' in val:return '10-key'
 if '7-' in val or '7 ' in val or '7"' in val:return '7-key'
 return 'other'

@lru_cache(maxsize=1)
def _index():
 data=defaultdict(dict)
 for row in source().get('rows',[]):
  sku=_clean(row.get('sku')).upper();model=sku.split('-',1)[0]
  if not re.fullmatch(r'[0-9]{3}[A-Z]',model):continue
  try:
   rrp=Decimal(str(row['rrp']))
   if rrp<=0 or not rrp.is_finite():continue
  except (ValueError,KeyError,TypeError):continue
  console=_console_band(row.get('console'))
  entry=data[model].setdefault(sku,[])
  entry.append({'sku':sku,'rrp':rrp,'console_key':console,'console_label':_clean(row.get('console')),
                'name':_clean(row.get('name')),'sheet':_clean(row.get('sheet')),'source_row':row.get('row')})
 return data

def guide(asset,tier='Gold',discount=0,tiers=None,rates=None):
 # A coincidental model number on a third-party machine must not trigger a
 # Pulse RRP. Unstated/zero manufacturer fields are common in messy exports.
 external=('technogym','life fitness','matrix','concept2','concept 2','keiser','wattbike','precor','stairmaster')
 make=_clean(asset.get('make')).lower()
 if any(v in make for v in external):return None
 model=_model(asset)
 if not model or model not in _index():return None
 model_map=_index()[model]
 choices=[]
 for sku,rows in model_map.items():
  rrps={row['rrp'] for row in rows};consoles={row['console_key'] for row in rows}
  if len(rrps)!=1 or len(consoles)!=1:continue # conflicting source records held for review
  row=rows[0]
  choices.append({**row,'rrp':float(row['rrp']), 'source_conflict':False})
 if not choices:return None
 choices.sort(key=lambda v:(v['console_key']!='not-listed',v['rrp'],v['sku']))
 rates=rates or {'Standard Equipment':.03,'Treadmill / Elliptical':.0375}
 tiers=tiers or {'Gold':1,'Silver':.8,'Platinum':1.3}
 name=' '.join(x['name'] for x in choices[:4]).lower()
 is_cardio=bool(re.search(r'treadmill|elliptical|cross trainer|cross-trainer',name))
 pct=float(rates.get('Treadmill / Elliptical' if is_cardio else 'Standard Equipment',.03))
 factor=max(0,1-float(discount)/100)*float(tiers.get(tier,1))*pct/12
 bands=defaultdict(list)
 for row in choices:bands[row['console_key']].append(row)
 result=[]
 for band in sorted(bands,key=lambda b:(b!='not-listed',b)):
  entries=bands[band]
  prices=sorted(set(x['rrp'] for x in entries))
  representative={p:next(x for x in entries if x['rrp']==p) for p in prices}
  options=[{'rrp':p,'guide_monthly_unit':_money(p*factor),'example_sku':representative[p]['sku'],
            'example_name':representative[p]['name'],'sku_count':sum(x['rrp']==p for x in entries)} for p in prices]
  labels={'not-listed':'Console not specified in master','7-key':'7-inch tactile-key','10-key':'10.1-inch tactile-key',
          '10-touch':'10.1-inch touchscreen','18-touch':'18.5-inch touchscreen','other':'Other / unspecified console'}
  result.append({'key':band,'label':labels.get(band,band),'variants':len(entries),'prices':options,
    'min_monthly_unit':options[0]['guide_monthly_unit'],'max_monthly_unit':options[-1]['guide_monthly_unit'],
    'min_rrp':prices[0],'max_rrp':prices[-1]})
 minimum=min(v['min_monthly_unit'] for v in result)
 maximum=max(v['max_monthly_unit'] for v in result)
 return {'model':model,'source':'Full Master Price List 24-08-2026.xlsx',
  'basis':'Provisional maintenance guide from source RRP and unapproved tariff, not a verified exact configuration',
  'status':'GUIDE_ONLY','console_unconfirmed':not bool(_clean(asset.get('console'))),
  'min_monthly_unit':minimum,'max_monthly_unit':maximum,'bands':result,
  'rate_fraction':pct,'tier':tier,'discount':float(discount),
  'notice':'Guide price only. Exact console, finish, SKU, source RRP and contract tariff require commercial confirmation.'}

def picked(asset,example_sku,console_key,tier='Gold',discount=0,tiers=None,rates=None):
 g=guide(asset,tier,discount,tiers,rates)
 if not g:raise ValueError('No 2026 master RRP evidence for this equipment. Ask the pricing manager.')
 if console_key=='unknown':raise ValueError('Choose the installed console or the non-console variant first.')
 for band in g['bands']:
  if band['key']==console_key:
   for entry in band['prices']:
    if entry['example_sku']==example_sku:
     return g,band,entry
 raise ValueError('The selected RRP/console combination is not in the current source catalogue.')
