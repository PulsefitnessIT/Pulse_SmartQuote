"""Read-only maintenance-price identification backlog across saved draft quotes."""
from __future__ import annotations
from collections import Counter
import engine as E
from asset_intelligence import grouped_assets


def analyse(quotes, max_rows=1200):
    rows=[]
    covered=Counter()
    for quote in quotes:
        assets=quote.get('assets',[])
        if not assets:continue
        values=E.calc_quote(quote)
        price_map={line['id']:line.get('price') for line in values['lines']}
        for g in grouped_assets(assets,price_map):
            a=g['representative']
            if a.get('excluded'):
                covered['excluded_units']+=g['qty'];continue
            covered['total_units']+=g['qty']
            if g.get('price') and not a.get('qty_issue'):
                covered['priced_units']+=g['qty'];continue
            covered['unpriced_units']+=g['qty']
            covered['unpriced_groups']+=1
            if len(rows)>=max_rows:continue
            from_code=str(a.get('imported_code') or a.get('code') or '')
            item={'quote_id':quote.get('id',''),'quote_no':quote.get('quote_no',''),
                  'customer':quote.get('customer',''),'site':a.get('site') or quote.get('site',''),
                  'source_name':a.get('source_description') or a.get('imported_name') or a.get('name',''),
                  'source_code':from_code,'model':a.get('model',''),'console':a.get('console',''),
                  'representative_asset_id':g['id'],'units':g['qty'],
                  'source_rows':len(g['ids']),
                  'issue':'Check imported quantity' if a.get('qty_issue') else
                          'Unpriced – exact identity / RRP / eligibility needs confirmation',
                  'historical_evidence':bool(a.get('historic_evidence'))}
            rows.append(item)
    rows.sort(key=lambda row:(-row['units'],row['quote_no'],row['source_name']))
    return {'counts':dict(covered),'items':rows,'truncated':covered['unpriced_groups']>len(rows),
            'notice':'All prices are draft estimates until source and tariff approval. No aliases or matching rules are automatically applied.'}
