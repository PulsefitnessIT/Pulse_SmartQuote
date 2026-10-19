"""Pulse Fitness quotation in the visual language of the supplied Sage invoice 654351.
No bank-payment instructions are copied into a quotation. Source price provenance is preserved.
"""
from __future__ import annotations
from io import BytesIO
from datetime import date,timedelta
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether,PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT,TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from engine import PACKAGES,calc_quote,ROOT,money
from asset_intelligence import grouped_assets

INK=HexColor('#101813');BORDER=colors.black;MUTED=HexColor('#536166');CYAN=HexColor('#15B9E5');WHITE=colors.white;PULSE_DARK=HexColor('#07190D')
def e(x):return escape(str(x if x is not None else ''))
def gbp(v):return '£'+format(float(v or 0),',.2f')
def addr(x,fallback='Address not supplied'):
 lines=[v.strip() for v in str(x or '').splitlines() if v.strip()]
 return '<br/>'.join(e(v) for v in (lines or [fallback]))

def create_quote_pdf(q):
 s=calc_quote(q);buff=BytesIO();ss=getSampleStyleSheet()
 ss.add(ParagraphStyle(name='invTitle',fontName='Helvetica-Bold',fontSize=21,leading=24,textColor=INK,spaceAfter=4))
 ss.add(ParagraphStyle(name='invBase',fontName='Helvetica',fontSize=8,leading=11,textColor=INK))
 ss.add(ParagraphStyle(name='invCell',fontName='Helvetica',fontSize=7.9,leading=10.5,textColor=INK))
 ss.add(ParagraphStyle(name='invHead',fontName='Helvetica-Bold',fontSize=8.2,leading=11.2,textColor=INK))
 ss.add(ParagraphStyle(name='invMuted',fontName='Helvetica',fontSize=7.4,leading=10.2,textColor=MUTED))
 ss.add(ParagraphStyle(name='invSmall',fontName='Helvetica',fontSize=7.1,leading=9.5,textColor=INK))
 ss.add(ParagraphStyle(name='invWarning',fontName='Helvetica-Bold',fontSize=8.5,leading=12,textColor=HexColor('#A34920')))
 st=ss
 def P(x,style='invBase'):return Paragraph(str(x),st[style])
 def table_base(rows,widths,commands=(),padding=5,rowheights=None):
  t=Table(rows,colWidths=widths,rowHeights=rowheights,hAlign='LEFT')
  t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),padding),('RIGHTPADDING',(0,0),(-1,-1),padding),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]+list(commands)))
  return t
 story=[]
 issued=str(q.get('issued_at') or date.today().isoformat())[:10]
 try:
  issued_day=date.fromisoformat(issued);valid_until=issued_day+timedelta(days=int(q.get('valid_days',30)))
  dt_str=issued_day.strftime('%d/%m/%Y');valid_str=valid_until.strftime('%d/%m/%Y')
 except (ValueError,TypeError):dt_str=issued;valid_str='Please confirm'
 story.append(P('Quotation','invTitle'))
 if not s['ready']:
  story.append(P('DRAFT — EQUIPMENT OR PRICING REQUIRES CONFIRMATION','invWarning'))
 story.append(Spacer(1,1*mm))
 customer=e(q.get('customer') or 'Customer name not supplied')
 client_lines=customer+('<br/>'+addr(q.get('billing_address'),'Billing address not supplied'))
 site_lines=e(q.get('site') or 'Site name not supplied')+('<br/>'+addr(q.get('delivery_address'),'Site address not supplied'))
 address_lines=max(1+len([v for v in str(q.get('billing_address') or '').splitlines() if v.strip()]),1+len([v for v in str(q.get('delivery_address') or '').splitlines() if v.strip()]))
 address_body_height=max(25,address_lines*5.0)*mm
 left=table_base([[P('<b>Customer / Billing Address</b>','invHead')],[P(client_lines)]],[88*mm],[('BOX',(0,0),(-1,-1),.65,BORDER),('LINEBELOW',(0,0),(-1,0),.4,HexColor('#CCCCCC'))],padding=6,rowheights=[7*mm,address_body_height])
 right=table_base([[P('<b>Site / Delivery Address</b>','invHead')],[P(site_lines)]],[88*mm],[('BOX',(0,0),(-1,-1),.65,BORDER),('LINEBELOW',(0,0),(-1,0),.4,HexColor('#CCCCCC'))],padding=6,rowheights=[7*mm,address_body_height])
 # Keep both blocks at matching height: equivalent to invoice address panels.
 addresses=table_base([[left,'',right]],[88*mm,4*mm,88*mm],[],padding=0)
 story.append(addresses);story.append(Spacer(1,3*mm))
 refs=[
  [P('<b>Quotation</b>','invHead'),P(e(q.get('quote_no') or 'DRAFT')),P('<b>Customer Ref:</b> '+e(q.get('customer_ref') or '—')),P('<b>Account Ref:</b> '+e(q.get('account_ref') or '—'))],
  [P('<b>Quote Date</b>','invHead'),P(e(dt_str)),P('<b>Valid Until:</b> '+e(valid_str)),P('<b>Contract Ref:</b> '+e(q.get('contract_ref') or '—'))],
 ]
 meta=table_base(refs,[31*mm,35*mm,67*mm,47*mm],[('BOX',(0,0),(-1,-1),.6,BORDER),('INNERGRID',(0,0),(-1,-1),.45,BORDER)],padding=5)
 story.append(meta);story.append(Spacer(1,3*mm))
 tier=q.get('tier','Gold');pkg=PACKAGES.get(tier,PACKAGES['Gold'])
 summaryrow=table_base([[P(f'<b>Maintenance Agreement:</b> {e(tier)}'),P(f'<b>Agreement Term:</b> {e(s["term"])} year(s)'),P(f'<b>Planned Service Visits:</b> {e(q.get("visits",1))} / year')]],[75*mm,51*mm,54*mm], [('BOX',(0,0),(-1,-1),.45,BORDER)],padding=5)
 story.append(summaryrow);story.append(Spacer(1,2*mm))
 columns=['Line','Item Code','Description','Quantity','Unit Price','Net']
 widths=[12*mm,30*mm,74*mm,17*mm,23*mm,24*mm]
 line_items=[[P('<b>'+x+'</b>','invHead') for x in columns]]
 costs={a['id']:a['price'] for a in s['lines']}
 display_groups=[g for g in grouped_assets(q.get('assets',[]),costs) if not g['representative'].get('excluded')]
 includes=[a for a in q.get('assets',[]) if not a.get('excluded')]
 for i,g in enumerate(display_groups,1):
  a=g['representative'];sel=a.get('selected') or {};cost=g['price'];label=(a.get('display_name') or a.get('name') or sel.get('name') or 'Unresolved equipment')
  extra=[]
  m=sel.get('model') or a.get('model')
  con=(a.get('console') or (sel.get('console_display') if sel.get('console_status') in ('source','description_only') else '')) or ''
  if m and not sel:extra.append('Model: '+e(m))
  if con and con not in ('Not Applicable',) and 'console' not in label.lower():extra.append('Console: '+e(con))
  if g['serials']:extra.append(('Serial: '+e(g['serials'][0])) if len(g['serials'])==1 else f"{len(g['serials'])} serials retained in attached asset schedule")
  sites={str(v.get('site','')).strip() for v in q.get('assets',[]) if str(v.get('site','')).strip()}
  if len(sites)>1 and a.get('site'):extra.append('Site: '+e(a['site']))
  if sel.get('price_origin')=='historic-family-estimate':
   extra.append('Indicative price basis: reference model '+e(sel.get('reference_model',''))+' (not confirmed exact SKU)')
  if cost and cost.get('basis')=='historic-reference':
   extra.append('HISTORIC RRP ONLY - update price before issuing a customer quote')
  description=P(e(label)+('<br/><font color="#536166" size="6.6">'+' · '.join(extra)+'</font>' if extra else ''),'invCell')
  sku=a.get('code') or sel.get('sku') or sel.get('model') or '—'
  line_items.append([P(str(i),'invCell'),P(e(sku),'invCell'),description,P(str(g['qty']),'invCell'),P(gbp(cost['unit']) if cost else 'TBC','invCell'),P(gbp(cost['annual']) if cost else 'TBC','invCell')])
 if not includes:line_items.append([P('—')]*6)
 lines=Table(line_items,colWidths=widths,repeatRows=1,hAlign='LEFT')
 lines.setStyle(TableStyle([('BOX',(0,0),(-1,0),.7,BORDER),('LINEBELOW',(0,0),(-1,0),.7,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,0),6),('BOTTOMPADDING',(0,0),(-1,0),6),('TOPPADDING',(0,1),(-1,-1),3),('BOTTOMPADDING',(0,1),(-1,-1),4),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('LINEBELOW',(0,1),(-1,-1),.25,HexColor('#DDDDDD'))]))
 story.append(lines)
 if s['priced_rows']!=len(includes):story.append(P('<b>INCOMPLETE QUOTATION: unpriced equipment must be resolved or formally excluded.</b>','invWarning'))
 historic_only=sum(1 for a in includes if costs.get(a['id']) and costs[a['id']].get('basis')=='historic-reference')
 if historic_only:story.append(P(f'<b>DRAFT PRICING: {historic_only} lines use an OLD RRP reference, not a current approved sales price. Do not issue until revalidated.</b>','invWarning'))
 if s.get('excluded_rows'):
  story.append(Spacer(1,4*mm))
  story.append(P('<b>Equipment excluded from this quotation</b>','invHead'))
  for a in q.get('assets',[]):
   if a.get('excluded'):story.append(P('• '+e(a.get('display_name') or a.get('name') or a.get('code') or 'Unidentified machine')+' — '+e(a.get('exclusion_reason') or 'Reason not supplied'),'invMuted'))
 # The original invoice leaves a large flexible area between lines and totals.
 # Use a modest gap so busy item lists still paginate naturally.
 story.append(Spacer(1,0 if len(includes)>4 else 12*mm))
 net=s['annual'];vat=money(net*.20);gross=money(net+vat)
 totals=table_base([[P('<b>PRICED LINES NET</b>' if s['priced_rows']!=len(includes) else '<b>NET (ANNUAL)</b>','invHead'),P(gbp(net),'invHead')],[P('<b>VAT (20%)</b>','invHead'),P(gbp(vat),'invHead')],[P('<b>GROSS (ANNUAL)</b>','invHead'),P(gbp(gross),'invHead')]], [42*mm,29*mm], [('BOX',(0,0),(-1,-1),.7,BORDER),('INNERGRID',(0,0),(-1,-1),.5,BORDER)],padding=6)
 totals.hAlign='RIGHT'
 story.append(totals)
 story.append(Spacer(1,2*mm))
 summary_title = 'PARTIAL QUOTED LINES SUBTOTAL' if s['priced_rows']!=len(includes) else ('PROVISIONAL ANNUAL TOTAL — HISTORIC RRPs INCLUDED' if historic_only else 'Annual maintenance quotation')
 scope_note = 'This is NOT a full price for the contracted equipment; unpriced machines are excluded from this subtotal.' if s['priced_rows']!=len(includes) else 'Future indexation not included.'
 story.append(P(f'<b>{e(summary_title)}:</b> {gbp(net)} excluding VAT. <b>Term equivalent ({s["term"]} year(s)):</b> {gbp(s["term_total"])} excluding VAT. {e(scope_note)}','invSmall'))
 if s.get('estimated_rows'):
  story.append(P('INDICATIVE EQUIPMENT PRICING: Some lines use a current product-family retail price because the historic machine SKU or console generation is not in the current price list. These are reference comparisons, not verified like-for-like replacements. Confirm the equipment and coverage before sending a binding quotation.','invMuted'))
 if (q.get('renewal') or {}).get('fixed_price_extension'):
  story.append(P('EXISTING CONTRACT OPTION: This agreement may contain an extension at the previously agreed annual price. Check that option and its terms before offering a replacement rate.','invWarning'))
 story.append(Spacer(1,3*mm))
 notes=[P('<b>Quotation Information</b>','invHead'),P('<b>Maintenance package:</b> '+e(tier)+' — '+e(pkg['subtitle']),'invSmall'),P('<b>Included:</b> '+e('; '.join(pkg['highlights'])),'invSmall'),P('<b>Exclusions:</b> '+e(pkg['exclusions']),'invSmall'),P('Prices exclude VAT unless stated. Figures describe the annual cover of the included equipment only. The monthly equivalent is not a confirmed Direct Debit payment plan. Any additional preventative maintenance visits or site-specific works require separate written approval. The signed Pulse Fitness Maintenance Agreement governs service obligations, payment arrangements and exclusions.','invSmall')]
 story.append(KeepTogether(notes))
 story.append(Spacer(1,2*mm))
 story.append(P('<b>Prepared by:</b> '+e(q.get('prepared_by') or 'Pulse Fitness Aftersales')+' &nbsp;&nbsp; | &nbsp;&nbsp; <b>For enquiries:</b> +44 (0)1260 294600 · info@pulsefitness.com','invMuted'))
 # A separate technical asset schedule retains every imported serial, source row,
 # original description and identification. It never inflates the quote lines.
 if any(len(g['assets'])>1 for g in display_groups):
  story.append(PageBreak());story.append(P('<b>Equipment asset schedule — source detail</b>','invHead'))
  story.append(P('The quotation groups identical equipment for readability. Every original machine below remains individually traceable; the schedule is part of this draft.','invSmall'))
  for line_no,g in enumerate(display_groups,1):
   a=g['representative'];story.append(P('<b>Line '+str(line_no)+' · '+e(a.get('name') or a.get('model') or a.get('code') or 'Unidentified')+' · '+str(g['qty'])+' units</b>','invSmall'))
   rows=[[P('<b>Sheet / row</b>','invHead'),P('<b>Asset ID</b>','invHead'),P('<b>Serial number</b>','invHead'),P('<b>Original description / install date</b>','invHead')]]
   for detail in g['assets']:
    rows.append([P(e(str(detail.get('source_sheet') or '')+' / '+str(detail.get('source_row') or '')),'invSmall'),P(e(detail.get('asset_tag') or '—'),'invSmall'),P(e(detail.get('serial') or '—'),'invSmall'),P(e(detail.get('source_description') or '—')+(' · Installed '+e(detail.get('install_date')) if detail.get('install_date') else ''),'invSmall')])
   tab=Table(rows,colWidths=[30*mm,23*mm,39*mm,88*mm],repeatRows=1,hAlign='LEFT')
   tab.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.4,BORDER),('LINEBELOW',(0,1),(-1,-1),.2,HexColor('#DDDDDD')),('BOTTOMPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),3)]))
   story.append(tab);story.append(Spacer(1,2*mm))

 def headerfooter(c,doc):
  c.saveState();w,h=A4
  logo=str(ROOT/'static/pulse_logo.png')
  c.drawImage(logo,18*mm,h-30*mm,width=74*mm,height=26*mm,mask='auto',preserveAspectRatio=True)
  c.setFillColor(INK);c.setFont('Helvetica',7.3)
  c.drawString(111*mm,h-14*mm,'Pulse Fitness')
  c.drawString(111*mm,h-18*mm,'Part of The Pulse Group')
  c.drawString(111*mm,h-22*mm,'Radnor Park, Greenfield Road')
  c.drawString(111*mm,h-26*mm,'Congleton, Cheshire CW12 4TW')
  c.drawString(160*mm,h-14*mm,'+44 (0)1260 294600')
  c.drawString(160*mm,h-18*mm,'info@pulsefitness.com')
  c.drawString(160*mm,h-22*mm,'www.pulsefitness.com')
  c.drawString(160*mm,h-26*mm,'#pulsefitness')
  c.setFont('Helvetica',7);c.setFillColor(MUTED)
  c.drawString(18*mm,18*mm,str(doc.page))
  c.drawString(99*mm,18*mm,'A Pulse Global Company')
  c.setFont('Helvetica',6.3)
  c.drawString(99*mm,13*mm,'Registered Office: Pulse Fitness Limited, Radnor Park, Greenfield Road, Congleton, Cheshire CW12 4TW')
  c.drawString(99*mm,10*mm,'Company Registration No 4354059 · VAT Registration No 785413509')
  c.setFillColor(PULSE_DARK);c.rect(0,0,w,6*mm,stroke=0,fill=1)
  if not s['ready'] or q.get('pilot_only'):
   c.saveState();c.setFillColor(HexColor('#D8D8D8'))
   try:c.setFillAlpha(.32)
   except Exception:pass
   c.translate(w/2,h/2);c.rotate(35);c.setFont('Helvetica-Bold',36);c.drawCentredString(0,0, 'PILOT - NOT FOR CUSTOMER ISSUE' if q.get('pilot_only') and s['ready'] else 'DRAFT - INCOMPLETE')
   c.restoreState()
  c.restoreState()
 doc=SimpleDocTemplate(buff,pagesize=A4,leftMargin=15*mm,rightMargin=15*mm,topMargin=33*mm,bottomMargin=25*mm,title='Pulse Fitness | Quotation',author='Pulse Fitness')
 doc.build(story,onFirstPage=headerfooter,onLaterPages=headerfooter)
 return buff.getvalue()
