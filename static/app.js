/* Pulse SmartQuote: offline-friendly frontend, no third-party scripts. */
let state={quote:null,summary:null,bootstrap:null,view:'builder',filter:'all',sort:{key:null,direction:'asc'},groups:[],token:sessionStorage.getItem('smartquote_token'),user:null};
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>'£'+Number(n||0).toLocaleString('en-GB',{minimumFractionDigits:2,maximumFractionDigits:2});
const toast=(message,error=false)=>{const t=$('toast');t.innerText=message;t.className='toast'+(error?' error':'');setTimeout(()=>{t.className='toast hidden'},5000)};
let saveQueue=Promise.resolve();
function saveMessage(message,bad=false){const el=$('saveStatus');if(el){el.textContent=message;el.className=bad?'save-failed':''}}
async function diagnoseConnection(error){
  // A JavaScript "Failed to fetch" does not identify a bad workbook. Check the
  // actual backend instead; never silently retry write requests after a drop.
  try{
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),2500);
    let response;
    try{response=await fetch('/api/health',{signal:controller.signal,cache:'no-store'})}finally{clearTimeout(timer)}
    if(response.ok){
      const health=await response.json();
      if(health.api_contract!==10)return 'This browser is connected to an older SmartQuote server (possibly V9), not the downloaded V10. Close the older black command window, double-click start_windows.bat in the new V10 folder, then use the address it opens.';
      return 'SmartQuote V10 is running but the request was interrupted. Your equipment may not have been imported. Check the quote before retrying. If this persists, restart from start_windows.bat and review the command window for errors.';
    }
  }catch(ignored){}
  return 'Cannot contact the local SmartQuote server. Leave the black SmartQuote V10 command window open. If it has closed, double-click start_windows.bat again and use the exact address shown there. Your original spreadsheet has not been changed.';
}
async function api(path,options={}){
  let r;
  try{r=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(state.token?{'Authorization':'Bearer '+state.token}:{}),...(options.headers||{})}})}
  catch(e){throw new Error(await diagnoseConnection(e))}
  let data;try{data=await r.json()}catch(e){data={detail:`SmartQuote server returned an invalid response (HTTP ${r.status}). Check the black command window for details.`}}
  if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;
}
async function init(){
 $('loginForm').onsubmit=async e=>{e.preventDefault();try{
  const result=await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:$('loginName').value,password:$('loginPassword').value})});
  state.token=result.token;sessionStorage.setItem('smartquote_token',result.token);$('loginPassword').value='';$('loginGate').classList.add('hidden');await launchWorkspace();
 }catch(ex){$('loginError').textContent=ex.message}};
 try{const health=await api('/api/health');if(health.api_contract!==10)throw new Error('This browser is showing an older SmartQuote server. Close the old command window and launch this V10 download using start_windows.bat.');const indicator=document.querySelector('.local-indicator');if(indicator)indicator.textContent='● V10 connected · '+location.host;if(health.auth_setup_required){$('loginError').textContent='No administrator account yet. In the application folder run: python manage_users.py bootstrap';$('loginGate').classList.remove('hidden');return}
 await launchWorkspace();}
 catch(e){$('loginGate').classList.remove('hidden');$('loginError').textContent=e.message||'Cannot connect to SmartQuote. Check the application command window.';sessionStorage.removeItem('smartquote_token');state.token=null}
}
async function launchWorkspace(){
 const profile=await api('/api/auth/me');state.user=profile.user;
 $('navManager').style.display='none';
 $('catalogManageTab').classList.toggle('hidden',!['admin','manager'].includes(profile.user.role));
 $('navUsers').style.display=profile.user.role==='admin'?'':'none';
 $('managerOperator').value=profile.user.username;$('managerOperator').readOnly=true;
 state.bootstrap=await api('/api/bootstrap');const old=localStorage.getItem('pulse_quote_id');if(old){try{apply(await api('/api/quotes/'+old))}catch(e){await newQuote()}}else{await newQuote()}
 render();if(!state.bound){bind();state.bound=true}
 $('loginGate').classList.add('hidden');
}
async function newQuote(){const d=await api('/api/quotes',{method:'POST'});apply(d);localStorage.setItem('pulse_quote_id',d.quote.id);render();showView('builder')}
function apply(data){state.quote=data.quote;state.summary=data.summary;state.groups=data.display_groups||[]}
function viewData(){return {q:state.quote,s:state.summary}}
function sortEquipmentGroups(groups, priceById, summaryLines){
 const spec=state.sort||{};if(!spec.key)return groups;
 const collator=new Intl.Collator('en-GB',{numeric:true,sensitivity:'base'});
 const guides=Object.fromEntries(summaryLines.map(line=>[line.id,line.guide]));
 function getValue(g){
  const a=g.representative||{},price=g.price||priceById[a.id],guide=guides[a.id];
  switch(spec.key){
   case 'machine':return a.code||a.model||'';
   case 'description':return a.display_name||a.name||'';
   case 'qty':return Number(g.qty)||0;
   case 'unit':return price?Number(price.unit)/12:guide?Number(guide.min_monthly_unit):null;
   case 'annual':return price?Number(price.annual):guide?Number(guide.min_monthly_unit)*Number(g.qty)*12:null;
   case 'status':return a.excluded?'Excluded':a.qty_issue?'Check quantity':!price?'Needs a price':price.basis==='staff-guided-estimate'?'Draft - review':'Priced';
   default:return '';
  }
 }
 return groups.map((g,i)=>({g,i,value:getValue(g)})).sort((a,b)=>{
  if(a.value==null&&b.value!=null)return 1;
  if(b.value==null&&a.value!=null)return -1;
  let cmp=typeof a.value==='number'&&typeof b.value==='number'?a.value-b.value:collator.compare(String(a.value??''),String(b.value??''));
  return cmp?(spec.direction==='desc'?-cmp:cmp):a.i-b.i;
 }).map(item=>item.g);
}
function bindAssetSort(){
 document.querySelectorAll('[data-asset-sort]').forEach(button=>{
  const key=button.dataset.assetSort;
  button.onclick=()=>{const old=state.sort||{};state.sort={key,direction:old.key===key&&old.direction==='asc'?'desc':'asc'};render()};
  const active=state.sort?.key===key;
  button.querySelector('.asset-sort-arrow').textContent=active?(state.sort.direction==='asc'?'↑':'↓'):'↕';
  button.parentElement.setAttribute('aria-sort',active?(state.sort.direction==='asc'?'ascending':'descending'):'none');
 });
}
function compactMachineDescription(value){
 const full=String(value||'').replace(/\s+/g,' ').trim();
 if(full.length<90)return full;
 const spec=full.match(/\b(?:1\s*x\s*\d+\s*kg|\d+\s*kg weight stack|weight stack tower)\b/i);
 if(!spec||spec.index<20)return full;
 const name=full.slice(0,spec.index).trim().replace(/\s+(?:with|in)$/i,'');
 const screen=full.match(/(?:10\.1|18\.5|7)(?:["″]|-?inch)[^,;]{0,48}?(?:touchscreen|touch screen|tactile key)/i);
 const console=screen?screen[0].replace(/\s+/g,' ').replace(/.*?(10\.1|18\.5|7)/,'$1').replace(/\bconsole\b/gi,'').trim():'';
 return (name+(console?' · '+console:'')).slice(0,135);
}
function render(){if(!state.quote)return;const{q,s}=viewData();$('quoteNumber').textContent=q.quote_no;$('summaryCode').textContent=q.quote_no;$('pipelineStatus').value=q.pipeline_status||'Draft';$('pipelineNote').value=q.pipeline_note||'';
 ['customer','site','contact','contact_email','prepared_by','billing_address','delivery_address','customer_ref','account_ref','contract_ref','valid_days','term','discount','visits'].forEach(k=>{if($(k))$(k).value=(k==='valid_days'?q[k]??30:q[k]??'')});
 $('tierOptions').innerHTML=Object.entries(state.bootstrap.packages).map(([tier,p])=>`<button class="tier-card ${q.tier===tier?'active':''}" data-tier="${tier}"><span>${tier==='Silver'?'ESSENTIAL':tier==='Gold'?'RECOMMENDED':'COMPREHENSIVE'}</span><strong>${esc(tier)}</strong><small>${esc(p.subtitle)}</small></button>`).join('');
 document.querySelectorAll('[data-tier]').forEach(btn=>btn.onclick=async()=>{state.quote.tier=btn.dataset.tier;$('visits').value=btn.dataset.tier==='Silver'?'0':(Number($('visits').value)===0?'1':$('visits').value);await saveDetails(true)});
 $('metrics').innerHTML=[['Equipment rows',s.rows,'▣'],['Units on register',s.units,'◫'],['Guide prices available',s.guide_rows||0,'£'],['Needs a price',s.rows-s.excluded_rows-s.priced_rows,'!']].map(([l,v,i])=>`<div class="metric"><div><span>${esc(l)}</span><strong>${esc(v)}</strong></div><div class="m-icon">${esc(i)}</div></div>`).join('');
 $('sumAnnualLabel').textContent=s.priced_rows<s.rows-s.excluded_rows?'PARTIAL subtotal (unpriced machines excluded)':s.lines.some(x=>x.price?.basis==='staff-guided-estimate')?'DRAFT guide total — not approved':'Proposed annual maintenance';
 $('annual').textContent=money(s.annual);$('monthly').textContent=money(s.monthly);$('termTotal').textContent=money(s.term_total);$('sumTier').textContent=q.tier;$('sumUnits').textContent=s.units;$('sumLines').textContent=`${s.priced_rows} / ${s.rows}`;$('sumTerm').textContent=s.term+' year'+(s.term>1?'s':'');$('assetCount').textContent=s.rows;
 $('uploadedText').textContent=q.files.length?`${q.files.length} file(s) imported`:'No files uploaded yet';
 const invoiced=q.files.filter(x=>x.type==='historical-sales-invoice');const invoiceHistory=$('invoiceImportedHistory');if(invoiceHistory)invoiceHistory.innerHTML=invoiced.length?`<b>${invoiced.length} invoice(s) already on this draft</b><small>${invoiced.map(x=>esc(x.invoice_no||x.filename)).join(' · ')}</small>`:'';
 $('undoLastImport').classList.toggle('hidden',!q.files.at(-1)?.batch_id);
 const oldCalc=q.historic_calcs||null;const comp=$('oldCalcBanner');if(comp){comp.classList.toggle('hidden',!oldCalc);if(oldCalc){comp.innerHTML=`<b>Previous calculations:</b> ${esc(oldCalc.filename)} · ${oldCalc.line_count} lines / ${oldCalc.machine_count} machines · historic equipment total ${money(oldCalc.source_line_sum)} · historic annual contract ${money(oldCalc.previous_quote_annual)}.<br><small>New catalogue-priced quotation: ${money(s.annual)} / year ex VAT${s.issues.length?' · DRAFT, outstanding current-RRP/contract checks':''}. Historical prices are for audit and comparison, never automatic approved 2026 RRPs.</small>`;}}
 const renewal=q.renewal||null;const rb=$('renewalBanner');rb.classList.toggle('hidden',!renewal);
 if(renewal){rb.innerHTML=`<b>Renewal imported:</b> ${esc(renewal.agreement_ref||'Previous agreement')} · ${esc(renewal.previous_package||'')} cover · Previous annual charge ${esc(renewal.previous_annual||'unknown')} · Ends ${esc(renewal.previous_end||'unknown')}.<br><small>Equipment is priced afresh using today's SmartQuote catalogue; the old total is a comparison only.</small>${renewal.fixed_price_extension?'<div class="contract-issue">Important: the previous agreement offers an extension at the SAME annual price. Check whether the customer is entitled to exercise this option before proposing different pricing.</div><label><input type="checkbox" id="renewalOptionChecked" '+(q.renewal_option_checked?'checked':'')+'> I have checked the existing fixed-price extension option and confirmed how to proceed.</label>':''}`;const checkbox=$('renewalOptionChecked');if(checkbox)checkbox.onchange=()=>saveDetails(true)}
 const pmap=Object.fromEntries(s.lines.map(l=>[l.id,l.price]));
 const needs=a=>(!a.excluded&&(!pmap[a.id]||pmap[a.id]?.basis==='historic-reference'||pmap[a.id]?.review_required===true||a.qty_issue)) || (a.excluded&&!(a.exclusion_reason||'').trim());
 const todo=q.assets.filter(needs);
 const exceptions=s.pricing_exceptions||[];
 const coverage=$('pricingCoverage');
 if(coverage){
  const total=Math.max(0,s.rows-s.excluded_rows);
  const mismatched=s.source_rrp_reconciled_rows||0;
  coverage.classList.toggle('hidden',!total);
  if(total)coverage.innerHTML=`<b>${s.priced_rows} of ${total} included equipment lines have a numerical price</b>${exceptions.length?` · <strong>${exceptions.length} require RRP/scope review</strong>`:' · No missing prices'}${mismatched?` · ${mismatched} stale catalogue RRPs replaced with provisional 2026 source figures`:''}${exceptions.length?`<div class="coverage-exceptions">${exceptions.map(x=>`<span title="${esc(x.reason)}"><b>${esc(x.code||'Unknown')}</b> — ${esc(x.reason)}</span>`).join('')}</div>`:''}<small>${s.automatic_rrp_rows||0} lines priced automatically from the exact 2026 RRP source. Commercial tariff approval is separate and required before customer issue.</small>`;
 }
 $('reviewIssuesCount').textContent=todo.length;
 $('reviewAll').classList.toggle('active',state.filter==='all');$('reviewIssues').classList.toggle('active',state.filter==='issues');
 const displayed=state.groups.length?state.groups:q.assets.map(a=>({representative:a,qty:a.qty,ids:[a.id],serials:a.serial?[a.serial]:[],source_rows:[a.source_row],price:pmap[a.id]}));
 const filtered=state.filter==='issues'?displayed.filter(g=>g.ids.some(id=>todo.some(a=>a.id===id))):displayed;
 const shown=sortEquipmentGroups(filtered,pmap,s.lines);bindAssetSort();
 $('assetBody').innerHTML=shown.length?shown.map(g=>{
  const a={...g.representative,qty:g.qty};
  const selected=a.selected,pr=g.price;
  const guideRow=s.lines.find(line=>line.id===a.id);
  const guide=guideRow?.guide;
  const guideText=guide?guide.min_monthly_unit===guide.max_monthly_unit?money(guide.min_monthly_unit):money(guide.min_monthly_unit)+'–'+money(guide.max_monthly_unit):'';
  const label=a.excluded?'Excluded':a.qty_issue?'Check quantity':!pr?'RRP review':pr.basis==='source-rrp-calculated'?'RRP calculated':pr.basis==='staff-guided-estimate'?'Draft – review':pr.basis==='historic-reference'?'Historic RRP':a.manual_annual_unit!=null?'Manual rate':selected?.price_origin==='historic-family-estimate'?'Family estimate':selected?.price_origin==='calculated-estimate'?'Calculated':'Priced';
  const cls=a.excluded?'':a.qty_issue?'bad':!pr?'bad':pr.basis==='source-rrp-calculated'?'rrp-calculated':(pr.review_required===true)||['calculated-estimate','historic-family-estimate'].includes(selected?.price_origin)?'warning':'ok';
  const identifier=a.code||a.model||selected?.model||'Model not supplied';
  const name=a.display_name||a.name||selected?.name||'Equipment description not supplied';
  const visibleName=compactMachineDescription(name);
  const serials=(g.serials||[]).filter(Boolean);
  const serialText=serials.length?serials.join(', '):'Not provided';
  const shortPrice=a.excluded?'—':pr?(pr.basis==='staff-guided-estimate'?'Draft '+money(pr.unit/12):money(pr.unit/12)):guide?`Guide ${guideText}`:'TBC';
  return `<tr class="${a.excluded?'is-excluded':''}"><td class="contract-machine"><b>${esc(identifier)}</b><small class="machine-serials">Serial${serials.length===1?'':'s'}: ${esc(serialText)}</small></td><td class="contract-description"><b title="${esc(name)}">${esc(visibleName)}</b>${a.contract_note?`<small>${esc(a.contract_note)}</small>`:''}</td><td>${esc(a.qty)}</td><td><span class="price-col">${shortPrice}</span><small>${!pr&&guide?'Range only · source RRP':pr?.basis==='source-rrp-calculated'?'Source RRP · tariff sign-off at quote level':pr?.basis==='staff-guided-estimate'?'Source RRP · configuration review':'per machine · ex VAT'}</small></td><td><span class="price-col">${a.excluded?'EXCLUDED':pr?(pr.basis==='staff-guided-estimate'?'Draft '+money(pr.annual):money(pr.annual)):guide?'Guide '+(guide.min_monthly_unit===guide.max_monthly_unit?money(guide.min_monthly_unit*g.qty*12):money(guide.min_monthly_unit*g.qty*12)+'–'+money(guide.max_monthly_unit*g.qty*12)):'TBC'}</span></td><td><span class="status ${cls}">${label}</span><br><button class="review-btn" data-review="${esc(a.id)}">Edit machine</button><button class="tiny-del" title="Permanently remove line" data-delete="${esc(a.id)}">✕</button></td></tr>`;
 }).join(''):'<tr><td colspan="6" class="empty-table">'+(state.filter==='issues'?'All included equipment has a price. Choose All equipment or generate your PDF.':'Drop in an asset list or try the sample import to begin.')+'</td></tr>';
 document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>review(b.dataset.review));document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>removeAsset(b.dataset.delete));
 let matched=q.assets.filter(a=>a.selected&&!a.excluded).length,excluded=q.assets.filter(a=>a.excluded).length;
 $('matchBreakdown').textContent=`${s.priced_rows} prices calculated · ${todo.length} equipment exceptions · ${excluded} excluded`;
 const health=s.issues.slice(0,9);$('healthList').innerHTML=health.length?health.map(v=>`<div class="health-item">${esc(v)}</div>`).join('')+(s.issues.length>9?`<div class="health-item">+${s.issues.length-9} more issues — see equipment list</div>`:''):'<div class="health-item healthy">Everything needed is in place. Click Generate Quote PDF.</div>';
 $('healthBadge').className='health-badge '+(s.ready?'ok':'warning');$('healthBadge').textContent=s.ready?'Ready to generate':`${s.issues.length} detail${s.issues.length===1?'':'s'} needed`;
 if(!q.assets.length){$('healthList').innerHTML='<div class="health-item">Upload equipment and complete the customer details to begin.</div>'}
 $('advisoryNote').textContent=s.estimated_rows?`${s.estimated_rows} equipment line(s) use catalogue-derived estimates (including possible historic-model comparisons). Check the reference details before customer issue; this is not an exact old-SKU price.`:'Matching and pricing do not require a separate review step.';
 updateGuidance();
}
function updateGuidance(){
 const q=state.quote,s=state.summary;if(!q||!s)return;
 const active=q.assets.filter(a=>!a.excluded);
 const pmap=Object.fromEntries(s.lines.map(l=>[l.id,l.price]));
 const unresolved=active.filter(a=>!pmap[a.id]||a.qty_issue||pmap[a.id]?.basis==='historic-reference');
 const count=unresolved.length,imported=q.assets.length;
 let heading='',detail='',cta='',action;
 let phase=0;
 if(!imported){heading='Start with an equipment list';detail='Upload Excel or CSV to check the detected machines before adding them. You can also add equipment manually.';cta='Choose asset list →';action=()=>$('filePicker').click();phase=0}
 else if(count){heading=`Review ${count} machine${count===1?'':'s'} needing attention`;detail=`${imported} source rows are retained and grouped by machine. Confirm model/console or missing quantities; incomplete prices stay outside the quoted subtotal.`;cta='Review next machine →';action=()=>reviewNext();phase=1}
 else if(!q.customer?.trim()||!q.site?.trim()){heading='Add the customer and site';detail='Equipment has been reviewed. Complete the customer and site details to prepare the proposal.';cta='Open quote details →';action=()=>$('quoteDetails').scrollIntoView({behavior:'smooth',block:'start'});phase=2}
 else if(!s.ready){heading=`Resolve ${s.issues.length} quotation requirement${s.issues.length===1?'':'s'}`;detail=(s.issues[0]||'Review agreement cover and price assumptions.')+' Open the checklist for the full details.';cta='Review proposal →';action=()=>$('quoteDetails').scrollIntoView({behavior:'smooth',block:'start'});phase=2}
 else{heading='Draft quotation prepared';detail='All current application checks pass. Prices remain provisional until Pulse Fitness commercial approval; verify contract terms before customer issue.';cta='Generate quotation PDF →';action=downloadPdf;phase=3}
 $('workflowTitle').textContent=heading;$('workflowDetail').textContent=detail;
 const btn=$('workflowAction');btn.textContent=cta;btn.onclick=action;
 document.querySelectorAll('.stepbar .step').forEach((el,i)=>{el.classList.toggle('active',i===phase);el.classList.toggle('complete',i<phase)});
}

function collect(){let v={};['customer','site','contact','contact_email','prepared_by','billing_address','delivery_address','customer_ref','account_ref','contract_ref','valid_days','term','discount','visits'].forEach(k=>v[k]=$(k).value);v.tier=state.quote.tier;if(state.quote.renewal?.fixed_price_extension)v.renewal_option_checked=!!$('renewalOptionChecked')?.checked;return v}
function saveDetails(quiet=false){
 const quoteId=state.quote.id,values=collect();saveMessage('Saving changes…');
 const task=saveQueue.catch(()=>{}).then(async()=>{
  try{
   const d=await api('/api/quotes/'+quoteId,{method:'PUT',body:JSON.stringify(values)});
   if(state.quote.id!==quoteId)return;
   apply(d);
   // A slow response must not erase details entered while the request ran.
   if(JSON.stringify(collect())===JSON.stringify(values)){
    render();saveMessage('Saved · changes are retained');
   }else saveMessage('Newer changes pending…');
   if(!quiet)toast('Quote settings saved. Prices recalculated automatically.');
  }catch(e){saveMessage('Could not save. Use Save quote settings to retry.',true);toast(e.message,true)}
 });
 saveQueue=task;return task;
}
function quickHelp(){
 $('modalTitle').textContent='SmartQuote — 60-second staff guide';
 $('modalContent').innerHTML=`<div class="quick-help"><p><b>1. Import a file:</b> Excel and CSV go through a preview first. Check the machine count, grouped lines and quantity warnings. The original spreadsheet is never changed.</p>
 <p><b>2. Review equipment:</b> Select <strong>Needs a price</strong> or <strong>Your next step</strong> to work through unresolved machines. One correct selection can be applied to identical source lines. Always check the physical model and console before confirming.</p>
 <p><b>3. Complete the quote:</b> Fill in the customer, site and maintenance cover. Quote settings save when you leave a field. Missing prices remain outside the partial subtotal.</p>
 <p><b>4. Generate the PDF:</b> The current library still has unapproved historical configurations and provisional tariffs. Treat outputs as pilot drafts until commercial sign-off.</p>
 <div class="editor-help"><b>Made a mistake?</b> Undo an untouched last import. If equipment has been edited, undo is deliberately blocked so staff corrections cannot disappear.</div>
 <p><b>Keyboard:</b> Ctrl+S saves quote details; Alt+N opens the next unresolved machine; Esc closes a dialogue.</p>
 <button class="primary-btn" id="closeHelp" type="button">Got it — back to my quote</button></div>`;
 $('modal').classList.remove('hidden');$('closeHelp').onclick=()=>$('modal').classList.add('hidden');
}


// All document types share one uploader. A file is only removed after a
// successful, confirmed import; classification never modifies stored quote data.
let stagedUploads=[];
let nextStagedUploadId=1;
function uploadTypesFor(file){
 const name=String(file.name||'').toLowerCase();
 if(name.endsWith('.pdf'))return [['invoice','Sales invoice (PDF)'],['agreement','Previous maintenance agreement (PDF)']];
 if(name.endsWith('.xls'))return [['calculations','Previous calculations (Excel)']];
 if(name.endsWith('.xlsx'))return [['assets','Equipment / asset list'],['calculations','Previous calculations (Excel)']];
 if(/\.(csv|tsv|txt)$/.test(name))return [['assets','Equipment / asset list']];
 return [];
}
function suggestedUploadType(file){
 const types=uploadTypesFor(file);
 if(!types.length)return '';
 if(types[0][0]==='invoice'){
  if(/invoice|sales.?bill/i.test(file.name))return 'invoice';
  if(/agreement|maintenance.?contract|renewal/i.test(file.name))return 'agreement';
  return ''; // PDFs without meaningful names need a staff selection.
 }
 if(types.some(x=>x[0]==='calculations')&&/calculat|old.?calc|historic.?pric|quote.?calc/i.test(file.name))return 'calculations';
 return types[0][0];
}
function removeStagedUpload(id){
 stagedUploads=stagedUploads.filter(item=>item.id!==id);
 if(invoicePending && invoicePending.queueEntryIds && invoicePending.queueEntryIds.includes(id))invoiceReviewClear();
 renderStagedUploads();
}
async function identifyStagedUpload(entry){
 try{
  // Content classification changes no quotation data, and never commits imports.
  if(entry.file.size>70*1024*1024)throw new Error('File exceeds 70 MB detection limit');
  const bytes=new Uint8Array(await entry.file.arrayBuffer());let binary='';
  for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
  const detected=await api('/api/documents/detect',{method:'POST',body:JSON.stringify({filename:entry.file.name,content_base64:btoa(binary)})});
  if(!stagedUploads.includes(entry))return;
  entry.detectedReason=detected.reason||'';
  if(!entry.userChosenKind){
   entry.kind=uploadTypesFor(entry.file).some(x=>x[0]===detected.kind)?detected.kind:'';
   entry.detected=!!entry.kind&&detected.confidence==='high';
  }
 }catch(error){
  if(stagedUploads.includes(entry)){
   entry.detectedReason='Could not identify automatically. Please choose the file type.';
   if(!entry.userChosenKind)entry.kind='';
  }
 }finally{
  entry.detecting=false;
  if(stagedUploads.includes(entry))renderStagedUploads();
 }
}
async function stageUploadFiles(inputFiles){
 const incoming=Array.from(inputFiles||[]);
 let skipped=0;const added=[];
 for(const file of incoming){
  if(!uploadTypesFor(file).length){skipped++;continue;}
  if(stagedUploads.some(item=>item.file.name===file.name&&item.file.size===file.size&&item.file.lastModified===file.lastModified)){
   skipped++;continue;
  }
  const entry={id:nextStagedUploadId++,file,kind:'',detected:false,detecting:true,userChosenKind:false,detectedReason:''};
  stagedUploads.push(entry);added.push(entry);
 }
 if(skipped)toast(skipped+' unsupported or already queued file(s) skipped.',true);
 renderStagedUploads();
 if(!added.length)return;
 await Promise.all(added.map(identifyStagedUpload));
 // One known asset list or a same-site invoice group goes straight to PREVIEW.
 // No file is automatically imported. Agreements and historic calculations use
 // direct-write APIs and must retain their explicit Review click.
 if(stagedUploads.length!==added.length||added.some(x=>!stagedUploads.includes(x)||!x.detected||x.userChosenKind))return;
 if(added.every(x=>x.kind==='invoice')){reviewStagedInvoices();return;}
 if(added.length===1&&added[0].kind==='assets')reviewStagedUpload(added[0].id);
}

function renderStagedUploads(){
 const queue=$('uploadQueue'),items=$('uploadQueueItems');
 queue.classList.toggle('hidden',!stagedUploads.length);
 items.replaceChildren();
 $('uploadQueueCount').textContent=stagedUploads.length+' file'+(stagedUploads.length===1?'':'s');
 for(const entry of stagedUploads){
  const row=document.createElement('div');row.className='upload-queue-row';
  const info=document.createElement('div');info.className='upload-queue-file';
  const name=document.createElement('strong');name.textContent=entry.file.name;name.title=entry.file.name;
  const size=document.createElement('small');size.textContent=(entry.file.size/1024/1024).toFixed(2)+' MB';
  const detected=document.createElement('small');detected.textContent=entry.detecting?'Recognising document…':(entry.detectedReason||'Select a document type');
  info.append(name,size,detected);
  const label=document.createElement('label');label.className='upload-queue-type';
  const caption=document.createElement('span');caption.textContent='Document type';
  const select=document.createElement('select');select.setAttribute('aria-label','Document type for '+entry.file.name);
  const choices=uploadTypesFor(entry.file);
  if(!entry.kind){const option=document.createElement('option');option.value='';option.textContent=entry.detecting?'Recognising…':'Choose a document type';select.append(option);}
  select.disabled=entry.detecting;
  for(const [value,title] of choices){const option=document.createElement('option');option.value=value;option.textContent=title;select.append(option);}
  select.value=entry.kind;
  select.onchange=()=>{
   entry.kind=select.value;entry.detected=false;entry.userChosenKind=true;entry.detectedReason='Type selected by staff';
   if(invoicePending && invoicePending.queueEntryIds && invoicePending.queueEntryIds.includes(entry.id))invoiceReviewClear();
   renderStagedUploads();
  };
  label.append(caption,select);
  const actions=document.createElement('div');actions.className='upload-queue-row-actions';
  if(entry.kind!=='invoice'){
   const review=document.createElement('button');review.type='button';review.className='secondary-btn';
   review.textContent='Review';review.disabled=!entry.kind||entry.detecting;
   review.onclick=()=>reviewStagedUpload(entry.id);actions.append(review);
  }else{
   const note=document.createElement('small');note.textContent='Included in invoice review';actions.append(note);
  }
  const remove=document.createElement('button');remove.type='button';remove.className='upload-queue-remove';
  remove.textContent='Remove';remove.setAttribute('aria-label','Remove '+entry.file.name+' from queue');
  remove.onclick=()=>removeStagedUpload(entry.id);actions.append(remove);
  row.append(info,label,actions);items.append(row);
 }
 const invoices=stagedUploads.filter(e=>e.kind==='invoice');
 const batch=$('reviewInvoiceBatch');batch.classList.toggle('hidden',!invoices.length);
 if(invoices.length)batch.textContent=invoices.length>10?'Review first 10 of '+invoices.length+' sales invoices →':'Review '+invoices.length+' sales invoice'+(invoices.length===1?'':'s')+' →';
 batch.disabled=false;
 batch.title=invoices.length>10?'Remaining invoices stay in the queue for the next review.':'';
}
function reviewStagedUpload(id){
 const entry=stagedUploads.find(x=>x.id===id);
 if(!entry || !entry.kind){toast('Choose the document type before reviewing.',true);return;}
 if(entry.kind==='invoice'){reviewStagedInvoices();return;}
 if(entry.kind==='agreement')return importAgreement(entry.file,entry.id);
 if(entry.kind==='calculations')return importOldCalcs(entry.file,entry.id);
 return importFile(entry.file,entry.id);
}
function reviewStagedInvoices(){
 const invoices=stagedUploads.filter(x=>x.kind==='invoice');
 if(!invoices.length)return;
 const group=invoices.slice(0,10); // Keep extra invoices staged, avoiding needless removals.
 previewInvoices(group.map(x=>x.file),group.map(x=>x.id));
}

async function importFile(file,entryId=null){
 if(!file)return;
 const z=$('dropzone');z.classList.add('busy');$('uploadedText').textContent='Previewing '+file.name+'…';
 try{
  if(file.size>25*1024*1024)throw new Error('Maximum file size is 25 MB. Split this spreadsheet before importing.');
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
  for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
  const request={filename:file.name,content_base64:btoa(binary)};
  const data=await api('/api/quotes/'+state.quote.id+'/import-preview',{method:'POST',body:JSON.stringify(request)});
  const sheets=data.sheets.map(s=>`${esc(s.sheet)} (${s.assets_found} assets${s.headings_recognised?'':' · headings NOT recognised'})`).join(' · ');
  const warn=data.warnings.slice(0,6).map(w=>`<li>${esc(w)}</li>`).join('');
  $('modalTitle').textContent='Check equipment before importing';
  $('modalContent').innerHTML=`<div class="import-preview-intro"><b>${esc(file.name)}</b><p>${esc(data.notice)}</p></div>
   <div class="import-preview-stats"><div><strong>${data.source_rows}</strong><small>Original asset rows</small></div><div><strong>${data.physical_units}</strong><small>Machine units</small></div><div><strong>${data.equipment_groups}</strong><small>Condensed groups</small></div><div><strong>${data.draft_priced_rows}</strong><small>Draft-priced rows</small></div></div>
   <div class="import-preview-details"><p><b>Detected worksheets:</b> ${sheets||'None'}</p>
   <p><b>Recognised identities:</b> ${data.identified_rows} of ${data.source_rows} source rows · <b>Quantity checks:</b> ${data.quantity_checks}</p>
   ${data.existing_quote_rows?`<p class="import-warning">This quote already contains ${data.existing_quote_rows} asset rows. Importing will APPEND these rows, not replace the existing equipment.</p>`:''}
   ${data.already_imported?'<p class="import-error"><b>This exact file is already in this quotation.</b> Import is blocked to prevent duplicate machines.</p>':''}
   ${warn?`<details open><summary>Review source warnings (${data.warnings.length+data.more_warnings})</summary><ul>${warn}${data.more_warnings||data.warnings.length>6?'<li>More warnings will remain attached to the quotation.</li>':''}</ul></details>`:''}
   <h3>Sample of grouped equipment</h3><div class="import-preview-rows">${data.sample_groups.map(g=>`<div><b>${esc(g.units)} × ${esc(g.description)}</b><small>${esc(g.code||'No model code')} · ${g.source_rows} source rows · ${g.draft_priced?'Draft price found':'Price requires review'}</small></div>`).join('')}</div></div>
   <div class="editor-actions"><button class="secondary-btn" id="cancelImport" type="button">Cancel — make no changes</button><button class="primary-btn" id="confirmImport" type="button" ${data.already_imported?'disabled':''}>Add ${data.source_rows} asset rows to quote →</button></div>`;
  $('modal').classList.remove('hidden');$('cancelImport').onclick=()=>{$('modal').classList.add('hidden');$('uploadedText').textContent=state.quote.files.length?`${state.quote.files.length} file(s) imported`:'No files uploaded yet'};
  $('confirmImport').onclick=async()=>{
   const button=$('confirmImport');button.disabled=true;button.textContent='Importing assets…';
   try{
    const d=await api('/api/quotes/'+state.quote.id+'/import',{method:'POST',body:JSON.stringify({...request,content_sha256:data.content_sha256})});
    apply(d);state.filter='issues';$('modal').classList.add('hidden');if(entryId!==null)removeStagedUpload(entryId);render();
    toast(`${d.import_report.added} source assets added as ${d.import_report.grouped_lines} groups. Review equipment needing attention.`);
    document.querySelector('.assets-panel').scrollIntoView({behavior:'smooth',block:'start'});
   }catch(e){toast(e.message,true);button.disabled=false;button.textContent='Retry confirmed import →'}
  };
 }catch(e){toast(e.message,true);$('uploadedText').textContent='Import not completed — '+e.message;}
 finally{z.classList.remove('busy');$('filePicker').value=''}
}
async function undoLastImport(){
 const file=state.quote.files.at(-1);if(!file?.batch_id)return;
 if(!confirm(`Undo the last spreadsheet import, ${file.filename} (${file.imported} original asset rows)?\n\nThis removes ONLY the untouched last import. All other assets are retained.`))return;
 try{
  const result=await api('/api/quotes/'+state.quote.id+'/imports/undo-last',{method:'POST'});
  apply(result);state.filter='all';render();toast(`Undid ${result.undone_rows} asset rows from ${result.filename}.`);
 }catch(e){toast(e.message,true)}
}
function issueAssets(){const cost=Object.fromEntries(state.summary.lines.map(x=>[x.id,x.price]));return state.quote.assets.filter(a=>!a.excluded&&(!cost[a.id]||cost[a.id]?.review_required===true||a.qty_issue))}
function reviewNext(afterId=null){const list=issueAssets();let next=list[0];if(afterId){const all=state.quote.assets,ix=all.findIndex(a=>a.id===afterId);next=all.slice(ix+1).concat(all.slice(0,ix+1)).find(a=>list.some(t=>t.id===a.id));}if(next)review(next.id);else{$('modal').classList.add('hidden');toast('All included equipment is priced. Finish the customer details and generate the quote.');}}
function review(id){
 const a=state.quote.assets.find(x=>x.id===id);if(!a)return;
 state.reviewingId=id;
 $('modalTitle').textContent=`Edit equipment line · ${a.source_sheet||'Manual'}`;
 const idx=state.quote.assets.findIndex(x=>x.id===id);
 const problems=a.issues||[];
 const price=state.summary.lines.find(l=>l.id===a.id)?.price;
 const priced=!!price&&!a.qty_issue;const issueHtml=a.qty_issue?`<div class="issue-banner"><b>Check imported quantity</b><p>${esc(a.qty_issue)}</p></div>`:priced?`<div class="editor-help"><b>${price?.basis==='source-rrp-calculated'?'RRP calculated automatically from the exact source SKU. Tariff sign-off is handled once per quotation.':price?.basis==='staff-guided-estimate'?'Draft reference only — review the installed configuration.':a.selected?.price_origin==='historic-family-estimate'?'Indicative historic-family estimate — verify old SKU / console.':'Price ready.'}</b> This machine has a calculated amount in the draft. You can still change its details below.${a.selected?.reference_warning?'<br>'+esc(a.selected.reference_warning):''}</div>`:problems.length?`<div class="issue-banner"><b>Machine or price missing</b><ul>${problems.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:'<div class="editor-help">Search for the machine to calculate its cost.</div>';
 const options=[...(a.selected?[a.selected]:[]),...(a.candidates||[])];
 const choices=options.map((v,i)=>`<div class="match-choice"><div><b>${esc(v.name||'Unknown equipment')}</b><p>${esc(v.sku||v.service_key||'No SKU')} · ${esc(v.console_display||v.console||'Console unknown')} · RRP ${v.rrp?money(v.rrp):'not supplied'}</p></div>${v.price_origin==='historic-family-estimate'?'<span class="editor-hint">Family-price reference only. Search for a verified machine to replace it.</span>':`<button data-choose="${i}" ${v.duplicate_sku?'disabled title="Conflicting duplicate SKU"':''}>${a.selected&&i===0?'Reconfirm':'Confirm this machine'}</button>`}</div>`).join('');
 $('modalContent').innerHTML=`<div class="edit-toolbar"><span>LINE ${idx+1} OF ${state.quote.assets.length} · ORIGINAL SPREADSHEET ROW ${esc(a.source_row)}</span><button id="editorNext" class="secondary-btn" type="button">Next unpriced line →</button></div>${issueHtml}
  <div id="staffQuickPrice" class="staff-quick-price"><p class="staff-quick-loading">Loading a simple price guide…</p></div>
  <div class="editor-help"><b>Current proposed price:</b> ${price?money(price.unit/12)+' per unit per month · '+money(price.unit)+' per unit per year':'Select a machine to calculate the price'} (ex VAT, ${esc(state.quote.tier)}, after discount)</div><div class="editor-section">1 · Correct the imported equipment details</div>
  <div class="form-grid"><label>Imported machine description<input id="modalName" value="${esc(a.name||'')}" placeholder="e.g. Pulse Club Line Treadmill"></label><label>Product / item code (SKU)<input id="modalCode" value="${esc(a.code||'')}" placeholder="e.g. 260G-AAS"><span class="field-aside">Changing the SKU triggers new catalogue matching when saved.</span></label><label>Model<input id="modalModel" value="${esc(a.model||'')}" placeholder="e.g. 260G"></label><label>Console / display (optional)<input id="modalConsole" list="consoleList" value="${esc(a.console||'')}" placeholder="Select a console or type your own"><datalist id="consoleList"><option value="Console 3.5 (Series 1)"><option value="Console 5 (Series 2)"><option value="Console 6 (Series 3)"><option value="Console 8 (Series 3 Mini)"><option value="7-inch Tactile Key Console"><option value="10.1-inch Tactile Key Console"><option value="10.1-inch Cirrus V4 Touchscreen"><option value="18.5-inch Cirrus V4 Touchscreen"><option value="19-inch monitor"><option value="PM5 Console"><option value="Other / Third Party"><option value="Strength Console"></datalist><span class="field-aside">Select the actual console where known. A different console may require a different SKU/RRP; check the catalogue variant.</span></label><label>Manufacturer<input id="modalMake" value="${esc(a.make||'')}" placeholder="Pulse Fitness / Third-party"></label><label>Quantity<input id="modalQty" type="number" min="1" step="1" value="${esc(a.qty)}"></label><label>Serial number(s)<input id="modalSerial" value="${esc(a.serial||'')}"></label><label>Equipment location / site<input id="modalSite" value="${esc(a.site||'')}"></label></div>
  <label>Customer-facing quotation description<input id="modalDisplay" value="${esc(a.display_name||'')}" placeholder="Leave blank to use the catalogue's official description"><span class="field-aside">Only affects the PDF description. It does not change the SKU or underlying price.</span></label>
  <label>Additional contract line note (optional)<input id="modalContractNote" maxlength="500" value="${esc(a.contract_note||'')}" placeholder="e.g. Includes bench, special accessories or site-specific information"><span class="field-aside">Appears beneath the equipment description in the customer quotation. Colour and upholstery are optional.</span></label>
  ${state.groups.some(g=>g.ids.includes(a.id)&&g.ids.length>1)?`<label class="contract-note-all"><input id="modalNoteAll" type="checkbox" checked> Use the same contract note for identical machines at this site (serial numbers remain separate)</label>`:''}
  <details class="technical-asset-details"><summary>Original asset and catalogue details (${esc(a.code||a.model||'unknown')})</summary><div class="technical-asset-inner">
  <p><b>Source:</b> ${esc(a.source_sheet||'Unknown sheet')} · row ${esc(a.source_row||'unknown')} · ${esc(a.site||'Site not supplied')}</p>
  <p><b>Imported description:</b> ${esc(a.source_description||a.name||'Not provided')}</p>
  <p><b>Original SKU / matching result:</b> ${esc(a.code||'Unspecified')} · ${esc(a.match_type||'Unmatched')}${a.selected?.reference_sku?' · Reference only: '+esc(a.selected.reference_sku):''}</p>
  <p><b>Individual serial numbers:</b> ${esc((state.groups.find(g=>g.ids.includes(a.id))?.serials||[a.serial||'']).filter(Boolean).join(', ')||'Not supplied')}</p>
  ${a.historic_evidence?`<p><b>Historical catalogue:</b> ${esc(a.historic_evidence.basis)} · ${esc(a.historic_evidence.variant_count)} variant(s)</p>`:''}
  ${a.historic_master?`<p><b>Older revisions:</b> ${esc(a.historic_master.variant_rows)} recorded variants; ${esc((a.historic_master.consoles||[]).join(', '))}</p>`:''}
  </div></details>
  <button class="secondary-btn" type="button" id="saveAndMatch" style="margin:12px 0">Save these details & re-check catalogue</button>
  <details class="advanced-equipment-matches"><summary>Show full catalogue search and detailed machine variants (optional)</summary><div class="editor-section">Detailed catalogue matches</div><p class="editor-hint">Suggestions use the imported name or model, not a verified match. Check the full product description and correct console before selecting. Search by description, make, model or item code.</p>
  <div id="smartReviewSuggestions" class="smart-review"><p class="editor-hint">Looking up source catalogue and historical evidence…</p></div>
  <div class="match-choices-scroll">${choices||'<p class="editor-hint">No automatic match was found. Search the catalogue, or add an evidenced manual annual unit rate below.</p>'}</div>
  <div class="searchline"><input id="modalSearch" placeholder="e.g. rower, Concept2, storage rack, 260G"><button id="modalFind" class="secondary-btn">Find machine</button></div><div id="modalResults"></div>
  </details>
  ${['manager','admin'].includes(state.user?.role)?`<div class="match-memory-control"><label class="checkline"><input type="checkbox" id="rememberMatch"> Remember an exact, physically verified SKU for future imports (manager only)</label><label>Source evidence / who checked the machine<input id="rememberEvidence" placeholder="e.g. 2026 approved equipment drawing and console photographed"></label><small>Identity reference only. Other quotes always require a human to confirm; this will not approve a price or replace the catalogue.</small></div>`:''}
  <div class="editor-section">3 · Exceptional handling (only when needed)</div><div class="manual-box"><label class="edit-check"><input type="checkbox" id="enableManual" ${a.manual_annual_unit!=null?'checked':''}> Use an externally verified manual annual maintenance rate</label><div id="manualFields" class="${a.manual_annual_unit==null?'hidden':''}"><div class="form-grid"><label>Annual unit price (ex VAT)<input id="modalManualRate" type="number" step="0.01" min="0.01" value="${esc(a.manual_annual_unit??'')}" placeholder="£ per unit per year"></label><label>Manual price source/reference<input id="modalManualSource" value="${esc(a.manual_price_source||'')}" placeholder="Approved price list / manager email, date"></label></div><p class="editor-hint"><b>Commercial control:</b> manual rates are not invented or auto-approved. Enter a genuine authorised source and include a source for the manual price. This replaces automated pricing for this line. The quotation discount is applied to this manual base rate. Review the final discounted amount.</p></div></div>
  <div class="exclude-box"><label class="edit-check"><input type="checkbox" id="modalExclude" ${a.excluded?'checked':''}> Exclude this machine from the maintenance quotation</label><div id="excludeFields" class="${a.excluded?'':'hidden'}"><label>Reason for exclusion <span class="required-label">(required)</span><input id="modalExcludeReason" value="${esc(a.exclusion_reason||'')}" placeholder="e.g. Customer declined cover for this machine"></label><p class="editor-hint">Excluded equipment remains traceable and will be shown separately on the PDF. It contributes £0 to the quote.</p></div></div>
  <div class="editor-actions"><button class="secondary-btn" id="modalCancel">Close without saving</button><button class="secondary-btn" id="modalSaveNext">Save & next unpriced line →</button><button class="primary-btn" id="modalSave">Save changes ✓</button></div>`;
 const same=state.quote.assets.filter(b=>!b.excluded&&b.id!==a.id&&b.name===a.name&&b.model===a.model&&b.code===a.code&&b.console===a.console&&b.site===a.site);
 if(same.length){$('modalContent').querySelector('.editor-actions').insertAdjacentHTML('beforebegin',`<label class="checkline scope-checkbox-row"><input id="bulkSameEquipment" type="checkbox" checked><span>Apply this choice to ${same.length} other identical machine(s) at this site. Serial numbers stay separate.</span></label>`)}
 document.querySelectorAll('[data-choose]').forEach(b=>b.onclick=()=>choose(a,options[Number(b.dataset.choose)]));
 $('modalFind').onclick=()=>searchModal(a);$('modalSearch').onkeydown=e=>{if(e.key==='Enter')searchModal(a)};
 $('modalSave').onclick=()=>updateAsset(a,false);$('modalSaveNext').onclick=()=>updateAsset(a,true);
 $('saveAndMatch').onclick=()=>updateAsset(a,false,true);$('modalCancel').onclick=()=>$('modal').classList.add('hidden');$('editorNext').onclick=()=>reviewNext(a.id);
 $('enableManual').onchange=e=>$('manualFields').classList.toggle('hidden',!e.target.checked);
 $('modalExclude').onchange=e=>$('excludeFields').classList.toggle('hidden',!e.target.checked);
 $('modal').classList.remove('hidden');
 loadSmartReview(a);
}
function showStaffQuickPrice(asset,guide,group,showAlternatives=false){
 const panel=$('staffQuickPrice');if(!panel)return;
 if(!guide || guide.status!=='GUIDE_ONLY'){
  panel.innerHTML='<b>Step 1 · Identify the machine</b><p class="editor-hint">No current equivalent was found for this model. Use full catalogue search below or ask the pricing manager to identify it.</p>';
  return;
 }
 const calculated=state.summary?.lines.find(line=>line.id===asset.id)?.price;
 if(calculated?.basis==='staff-guided-estimate'&&calculated.preview_confidence==='exact_source_configuration'&&!showAlternatives){
  panel.innerHTML=`<div class="standard-machine-guide"><b>Price calculated from this machine's detailed description</b>
   <p><strong>${money(calculated.unit/12)} per month / machine</strong> · ${money(calculated.annual)} per year (for ${asset.qty||1} unit${asset.qty===1?'':'s'})</p>
   <small>August 2026 source RRP ${money(calculated.rrp)} · Reference variant ${esc(calculated.reference_sku)}. The console size and features identify one source-price configuration, but the physical SKU and maintenance tariff still need checking.</small>
   <button type="button" id="staffChangeSourceConfiguration" class="secondary-btn">Change or confirm console configuration →</button></div>`;
  panel.querySelector('#staffChangeSourceConfiguration').onclick=()=>showStaffQuickPrice(asset,guide,group,true);
  return;
 }
 const count=group?.quantity||asset.qty||1;
 const haveConsole=!!(asset.console||'').trim();
 const label=g=>g.key==='not-listed'?'No console stated on price list — check whether one is fitted':g.label;
 const baseline=guide.standard_reference;
 const consoleBands=guide.bands.filter(b=>b.key!=='not-listed');
 panel.innerHTML=`<h3>Draft maintenance guide <small>${esc(count)} machine${count===1?'':'s'} · ${esc(guide.model)}</small></h3>
  ${baseline?`<div class="standard-machine-guide"><b>Standard ${esc(guide.model)} reference: ${esc(baseline.example_sku)}</b><p><strong>${money(baseline.guide_monthly_unit)} per machine/month</strong> · Source RRP ${money(baseline.rrp)}</p><small>This is a model-family PRICE REFERENCE. It does not confirm the installed SKU, colour, upholstery or console.</small><button class="primary-btn" type="button" id="staffApplyStandard">Use standard model draft price →</button></div>`:
  `<p>Source RRP guide: <b>${money(guide.min_monthly_unit)}–${money(guide.max_monthly_unit)}/month</b> per machine. The console or specification must be selected for this model.</p>`}
  <details class="staff-console-details" ${baseline?'':'open'}><summary>${baseline?'Has a console or different specification? Choose it here':'Choose the console or equipment configuration'}</summary>
   <p class="editor-hint">Only select a console if the site or engineer has confirmed it. Upholstery/frame colours do not need selecting unless they change the RRP.</p>
   <div class="staff-console-choices">${consoleBands.map(band=>`<label class="staff-console-choice"><input type="radio" name="staffConsoleBand" value="${esc(band.key)}"><span><b>${esc(label(band))}</b><small>Guide ${money(band.min_monthly_unit)}–${money(band.max_monthly_unit)} / month</small></span></label>`).join('')}
    ${guide.bands.some(b=>b.key==='not-listed')?`<label class="staff-console-choice"><input type="radio" name="staffConsoleBand" value="not-listed"><span><b>Standard / no console in price list</b><small>Confirm whether a console is actually fitted</small></span></label>`:''}
   </div>
  </details>
  <div class="staff-quick-step"><b>Choose a price basis (only when different from standard)</b><div id="staffQuickVariants"><small>Choose a configuration above to see source RRP price levels.</small></div></div>
  <div class="staff-quick-footer"><label class="checkline"><input id="staffVerified" type="checkbox"> I have checked the installed configuration. This is a draft using the 2026 RRP; the maintenance tariff still needs commercial sign-off.</label>
   <label class="checkline"><input id="staffSimilar" type="checkbox" ${group?.count>1?'checked':''}> Apply to ${group?.count||1} identical imported row(s), preserving every serial number.</label>
   <button id="staffQuickApply" class="primary-btn" type="button" disabled>Use selected draft configuration</button>
   <small>Why draft? The model RRP comes from the August 2026 master, but the Silver/Gold/Platinum rates have not yet been commercially approved. Staff can prepare the quote while pricing is reviewed.</small></div>`;
 let selectedPrice=null,selectedBand=null;
 const baselineButton=panel.querySelector('#staffApplyStandard');
 if(baselineButton)baselineButton.onclick=async()=>{
   if(!confirm(`Use the standard ${guide.model} / ${baseline.example_sku} RRP as a DRAFT reference only? The actual console, exact SKU and maintenance rate remain unverified.`))return;
   baselineButton.disabled=true;
   try{
     const result=await api(`/api/quotes/${state.quote.id}/quick-price`,{method:'POST',body:JSON.stringify({asset_id:asset.id,console_key:'not-listed',example_sku:baseline.example_sku,standard_unconfirmed:true,console_verified:false,apply_to_similar:panel.querySelector('#staffSimilar').checked,acknowledge_guide_only:true})});
     apply(result);render();$('modal').classList.add('hidden');toast('Standard family guide applied as a draft. Console and final price still need review.');
   }catch(e){toast(e.message,true);baselineButton.disabled=false}
 };
 const applyBtn=panel.querySelector('#staffQuickApply');
 const refresh=()=>{applyBtn.disabled=!(selectedPrice&&selectedBand&&panel.querySelector('#staffVerified').checked)};
 panel.querySelectorAll('input[name="staffConsoleBand"]').forEach(r=>r.onchange=()=>{
  const target=panel.querySelector('#staffQuickVariants');selectedBand=r.value;selectedPrice=null;
  if(r.value==='unknown'){target.innerHTML='<div class="staff-quick-warning">Leave this group in review. Ask the engineer or site which console is fitted. No configuration will be chosen automatically.</div>';refresh();return}
  const band=guide.bands.find(b=>b.key===r.value);if(!band){refresh();return}
  target.innerHTML='<small>Choose the applicable source RRP. Variants with identical RRP are combined.</small>'+band.prices.map((v,i)=>`<label class="staff-price-option"><input type="radio" name="staffPriceLevel" value="${i}"><span><b>${money(v.guide_monthly_unit)} per month</b> · RRP ${money(v.rrp)}<small>Example reference: ${esc(v.example_sku)} · ${esc(v.sku_count)} SKU(s) at this RRP</small></span></label>`).join('');
  target.querySelectorAll('input[name="staffPriceLevel"]').forEach(v=>v.onchange=()=>{selectedPrice=band.prices[Number(v.value)];refresh()});
  refresh();
 });
 panel.querySelector('#staffVerified').onchange=refresh;
 applyBtn.onclick=async()=>{
  if(!selectedPrice||!selectedBand)return;
  applyBtn.disabled=true;
  try{
   const result=await api(`/api/quotes/${state.quote.id}/quick-price`,{method:'POST',body:JSON.stringify({asset_id:asset.id,console_key:selectedBand,example_sku:selectedPrice.example_sku,apply_to_similar:panel.querySelector('#staffSimilar').checked,acknowledge_guide_only:true,console_verified:true})});
   apply(result);render();$('modal').classList.add('hidden');toast('Draft prices added. The quote remains blocked from customer issue until commercial verification.');
  }catch(e){toast(e.message,true);applyBtn.disabled=false}
 };
}
async function loadSmartReview(asset){
 const panel=$('smartReviewSuggestions');
 if(!panel)return;
 try{
  const data=await api(`/api/quotes/${state.quote.id}/match-review/${encodeURIComponent(asset.id)}`);
  if(state.reviewingId!==asset.id || !$('smartReviewSuggestions'))return;
  const hybrid=data.legacy_rrp_policy;
  const hybridText=hybrid?.status==='reviewed' ? (hybrid.basis==='current_equivalent' && hybrid.current_equivalent?
    `Manager-reviewed current equivalent: ${esc(hybrid.current_equivalent.sku)} · RRP ${money(hybrid.current_equivalent.rrp)} · Console ${esc(hybrid.current_equivalent.console||'Not confirmed')}. Confirm this physical configuration before selecting a SKU.`:
    `Manager-reviewed legacy exception: ${esc(hybrid.legacy_code)} · Evidence-only historical RRP ${money(hybrid.exception_rrp_evidence_only)}. This cannot automatically change pricing.`):
    hybrid?.status==='stale'||hybrid?.status==='expired'?`Previous legacy mapping is ${esc(hybrid.status)}: ${esc(hybrid.warning||'recheck required')}`:
    'Hybrid RRP policy: use a verified current equivalent. If not identifiable, refer to a pricing manager for a documented legacy exception. Never guess the installed console.';
  const hybridHtml=`<div class="editor-help"><b>Legacy equipment pricing basis:</b> ${hybridText}</div>`;
  const previously=data.reviewed_match;
  const memoryHtml=previously?`<div class="memory-recommendation"><b>Previously verified matching identity: ${esc(previously.sku)}</b><small>${esc(previously.reason)}. ${previously.available?'Still in catalogue':'No longer usable'}. ${previously.stale?'Catalogue updated since review — check all pricing/console evidence.':''}</small>${previously.available?'<button class="secondary-btn" id="selectMemory" type="button">Review saved SKU</button>':''}</div>`:'';
  const notice=data.source_variant?`<p class="smart-alert">Legacy model variant: ${esc(data.source_variant)}. Check the physical machine before choosing a base-family SKU.</p>`:'';
  const evidence=data.historical?`<small>Historical records: ${esc(data.historical.variant_count)} variant(s) · ${esc(data.historical.basis)}. Historical codes are not approved alternatives.</small>`:'<small>No exact historical identity recorded for this model/SKU in the currently loaded archive.</small>';
  showStaffQuickPrice(asset,data.quick_price,data.group);
  const top=data.candidates||[];
  panel.innerHTML=`<div class="smart-review-title"><b>Catalogue match assistant</b><span>${esc(data.group.quantity)} units · ${esc(data.group.count)} source rows</span></div><p class="editor-hint">${esc(data.explanation)}</p>${notice}${evidence}${memoryHtml}${hybridHtml}<div class="smart-review-results">${top.slice(0,8).map((c,i)=>`<div class="match-choice"><div><b>${esc(c.sku)} · ${esc(c.name)}</b><p>${esc(c.model)} · ${esc(c.console_display||c.console||'Console unverified')} · RRP ${c.rrp?money(c.rrp):'Not available'}</p><small>${esc(c.reason)}${c.review_flags?.length?' · '+esc(c.review_flags.join('; ')):''}</small></div><button data-smartchoose="${i}" ${c.duplicate_sku?'disabled':''}>Review & select</button></div>`).join('')||'<p class="editor-hint">No reliable current catalogue candidates found. Record the equipment for commercial review; never invent its RRP.</p>'}</div>`;
  if(previously?.available){const b=panel.querySelector('#selectMemory');if(b)b.onclick=()=>{
   if(!confirm(`Verify ${previously.sku} against this physical machine and actual console before applying it. Continue?`))return;
   choose(asset,previously.catalogue_option);
  };}
  panel.querySelectorAll('[data-smartchoose]').forEach(b=>b.onclick=()=>{
   const o=top[Number(b.dataset.smartchoose)];
   if(!o)return;
   if(!confirm(`You must verify the actual SKU, configuration and RRP. Apply ${o.sku} to this equipment${$('bulkSameEquipment')?.checked?' and identical source lines':''}?`))return;
   choose(asset,o);
  });
 }catch(e){if($('smartReviewSuggestions')&&state.reviewingId===asset.id)$('smartReviewSuggestions').innerHTML=`<p class="editor-hint">Catalogue assistant unavailable: ${esc(e.message)}. Use manual catalogue search.</p>`;}
}
/** Review multiple distinct equipment groups with a read-only impact preview. */
async function openBulkReview(offset=0){
 if(!state.quote?.assets?.length){toast('Import equipment before reviewing matching groups.');return}
 const quoteId=state.quote.id;
 $('modalTitle').textContent='Match several equipment groups';
 $('modalContent').innerHTML='<p class="editor-hint">Loading unresolved equipment groups…</p>';
 $('modal').classList.remove('hidden');
 try{
  const data=await api(`/api/quotes/${quoteId}/bulk-review/queue?offset=${offset}&limit=30`);
  if(state.quote.id!==quoteId)return;
  const rows=data.groups;
  $('modalContent').innerHTML=`<div class="bulk-review-intro"><b>${data.total_groups} equipment groups needing catalogue identification</b><p>Choose exact catalogue SKUs for verified machines. Suggestions are <strong>not approved equivalents</strong>. All consoles, source rows and serials remain distinct. One preview confirms the impact before any changes are saved.</p></div>
   <div class="bulk-review-list">${rows.map((g,i)=>`<section class="bulk-group" data-group-index="${i}">
    <div class="bulk-group-heading"><b>${esc(g.units)} × ${esc(g.description)}</b><span>${esc(g.rows)} source row${g.rows===1?'':'s'}</span></div>
    <small>${esc(g.source_code||'No confirmed model')} · ${esc(g.site||'Unspecified site')} · Console: ${esc(g.source_console||'not specified')}</small>
    ${g.variant_notice?`<div class="bulk-caution">Variant ${esc(g.variant_notice)} — physical variant must be verified.</div>`:''}
    <details class="bulk-source"><summary>View serials and original row numbers</summary><small>Source rows: ${esc(g.source_rows.slice(0,30).join(', '))}${g.source_rows.length>30?' and '+(g.source_rows.length-30)+' more':''}</small><small>Serial numbers: ${esc(g.serials.slice(0,30).join(', ')||'not provided')}${g.serials.length>30?' and '+(g.serials.length-30)+' more':''}</small></details>
    <label>Catalogue match for this group<select class="bulk-select" aria-label="Matching SKU for ${esc(g.description)}" ${!g.can_bulk_review?'disabled':''}>
     <option value="">Leave unmatched for now</option>${g.candidates.map(c=>`<option value="${esc(c.sku)}" ${!c.batch_selectable?'disabled':''}>${esc(c.sku)} · ${esc(c.name)} · ${c.rrp?money(c.rrp):'RRP missing'}${c.batch_selectable?'':' — individual review required'}</option>`).join('')}</select></label>
    ${!g.can_bulk_review?'<p class="bulk-caution">No batch-safe match. Use the individual editor to investigate historical variants, missing RRPs or different machine families.</p>':''}
    <p class="bulk-choice-risk hidden" role="status"></p>
    <div class="bulk-confirm-fields hidden"><label>Evidence for this exact SKU and console<input class="bulk-evidence" maxlength="400" placeholder="e.g. Checked actual model plate and console with engineer" aria-label="Evidence for ${esc(g.description)}"></label>
     <label class="bulk-verified"><input type="checkbox" class="bulk-check"> I have verified the physical model and console for this group</label></div>
    <button class="secondary-btn bulk-individual" data-individual="${i}" type="button">Review individually →</button>
   </section>`).join('')||'<p class="editor-hint">There are no remaining unpriced groups eligible for identity review. Check quantities, price approval and the quotation readiness checklist.</p>'}</div>
   <div class="bulk-actions"><small>Showing ${data.shown} of ${data.total_groups} groups · ${data.remaining} more after this page</small><div><button id="bulkNextPage" class="secondary-btn" type="button" ${!data.remaining?'disabled':''}>Next groups →</button><button id="bulkPreview" class="primary-btn" type="button" ${!rows.length?'disabled':''}>Preview selected matches →</button></div></div>
   <div id="bulkImpact" role="status" aria-live="polite"></div>`;
  const panel=$('modalContent');
  const impact=panel.querySelector('#bulkImpact');
  let previewActions=null;
  function invalidate(){previewActions=null;impact.innerHTML=''}
  panel.querySelectorAll('.bulk-group').forEach((node)=>{
   const select=node.querySelector('.bulk-select');
   const fields=node.querySelector('.bulk-confirm-fields');
   select.onchange=()=>{
    fields.classList.toggle('hidden',!select.value);
    const item=rows[Number(node.dataset.groupIndex)].candidates.find(c=>c.sku===select.value);
    const status=node.querySelector('.bulk-choice-risk');
    status.classList.toggle('hidden',!item);
    status.textContent=item?`Evidence: ${item.reason}. Reference RRP: ${item.rrp?money(item.rrp):'unavailable'}. ${item.review_flags?.join('; ')||'Current RRP/tariff still needs commercial approval.'}`:'';
    invalidate()
   };
   node.querySelector('.bulk-evidence').oninput=invalidate;
   node.querySelector('.bulk-check').onchange=invalidate;
  });
  panel.querySelectorAll('[data-individual]').forEach(btn=>btn.onclick=()=>{
   const group=rows[Number(btn.dataset.individual)];$('modal').classList.add('hidden');review(group.asset_id);
  });
  panel.querySelector('#bulkNextPage').onclick=()=>openBulkReview(offset+rows.length);
  panel.querySelector('#bulkPreview').onclick=async()=>{
   const actions=[];
   for(const [i,group] of rows.entries()){
    const node=panel.querySelector(`[data-group-index="${i}"]`);
    const sku=node.querySelector('.bulk-select').value;
    if(!sku)continue;
    const verified=node.querySelector('.bulk-check').checked;
    const evidence=node.querySelector('.bulk-evidence').value.trim();
    if(!verified||evidence.length<12){toast('For each selected group, check the verification box and enter detailed evidence (12+ characters).',true);node.scrollIntoView({block:'center'});return}
    actions.push({asset_id:group.asset_id,sku,verified,evidence});
   }
   if(!actions.length){toast('Select at least one catalogue match, or review a machine individually.',true);return}
   if(actions.length>20){toast('Review no more than 20 groups in one confirmation.',true);return}
   const button=panel.querySelector('#bulkPreview');button.disabled=true;
   try{
    const result=await api(`/api/quotes/${quoteId}/bulk-review/preview`,{method:'POST',body:JSON.stringify({token:data.token,actions})});
    previewActions=actions;
    impact.innerHTML=`<div class="bulk-impact"><h3>Review impact — nothing has been changed</h3>
     <p><b>${result.groups} groups</b> · ${result.source_rows} original asset rows · ${result.units} machines · ${result.draft_priced_assets} draft-priced assets after selection.</p>
     <div class="bulk-impact-list">${result.changes.map(c=>`<div><b>${esc(c.units)} × ${esc(c.description)} → ${esc(c.sku)}</b><small>${esc(c.site)} · ${esc(c.source_rows)} source rows · ${c.draft_priced_assets} draft-priced assets</small>${c.warnings?.length?`<p>${esc(c.warnings.join('; '))}</p>`:''}</div>`).join('')}</div>
     <p class="bulk-caution"><b>Not commercially approved.</b> Current RRPs and maintenance tariffs remain provisional. An identity match does not authorise a customer quotation.</p>
     <label class="bulk-verified"><input type="checkbox" id="bulkFinalAck"> I have checked all selections, source evidence, machine variants and consoles above.</label>
     <button class="primary-btn" id="bulkCommit" type="button" disabled>Confirm ${esc(result.groups)} groups and save changes</button>
    </div>`;
    impact.querySelector('#bulkFinalAck').onchange=e=>impact.querySelector('#bulkCommit').disabled=!e.target.checked;
    impact.querySelector('#bulkCommit').onclick=async()=>{
     const confirmBtn=impact.querySelector('#bulkCommit');confirmBtn.disabled=true;confirmBtn.textContent='Saving reviewed equipment…';
     try{
      const applied=await api(`/api/quotes/${quoteId}/bulk-review/apply`,{method:'POST',body:JSON.stringify({token:data.token,actions:previewActions,acknowledge:true})});
      if(state.quote.id===quoteId){apply(applied);state.filter='issues';render();$('modal').classList.add('hidden');toast(`${applied.batch_review.groups} groups confirmed · ${applied.batch_review.source_rows} original assets retained.`)}
     }catch(e){toast(e.message,true);confirmBtn.disabled=false;confirmBtn.textContent='Confirm matches and save'}
    };
    impact.scrollIntoView({block:'nearest',behavior:'smooth'});
   }catch(e){invalidate();toast(e.message,true)}finally{button.disabled=false}
  };
  panel.querySelector('.bulk-select:not([disabled])')?.focus();
 }catch(e){toast(e.message,true);$('modalContent').innerHTML=`<p class="bulk-caution">${esc(e.message)}. No changes were made.</p>`}
}

async function downloadAssetRegister(){
 try{
  const response=await fetch(`/api/quotes/${state.quote.id}/asset-register.csv`,{headers:state.token?{'Authorization':'Bearer '+state.token}:{}});
  if(!response.ok)throw new Error('Original source asset register could not be exported');
  const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');
  link.href=url;link.download=`Pulse_SmartQuote_${state.quote.quote_no}_Original_Asset_Register.csv`;
  link.click();setTimeout(()=>URL.revokeObjectURL(url),12000);
 }catch(e){toast(e.message,true)}
}
async function downloadMatchingReport(){
 try{
  const path=`/api/quotes/${state.quote.id}/matching-report.csv`;
  const res=await fetch(path,{headers:state.token?{'Authorization':'Bearer '+state.token}:{}});
  if(!res.ok)throw new Error('Unable to export matching report');
  const url=URL.createObjectURL(await res.blob());const a=document.createElement('a');
  a.href=url;a.download=`Pulse_SmartQuote_${state.quote.quote_no}_Matching_Review.csv`;a.click();
  setTimeout(()=>URL.revokeObjectURL(url),12000);
 }catch(e){toast(e.message,true)}
}
async function choose(a,option){
 try{const d=await api(`/api/quotes/${state.quote.id}/resolve`,{method:'POST',body:JSON.stringify({asset_id:a.id,option,apply_to_similar:!!$('bulkSameEquipment')?.checked,remember_match:!!$('rememberMatch')?.checked,review_evidence:$('rememberEvidence')?.value||''})});apply(d);render();$('modal').classList.add('hidden');toast('Machine selected and priced. Other identical assets were updated when requested.');}
 catch(e){toast(e.message,true)}
}
async function updateAsset(a,next=false,rematch=false){
 try{
  const manual=$('enableManual').checked;
  const data={name:$('modalName').value,code:$('modalCode').value,model:$('modalModel').value,console:$('modalConsole').value,make:$('modalMake').value,qty:Number($('modalQty').value),serial:$('modalSerial').value,site:$('modalSite').value,display_name:$('modalDisplay').value,contract_note:$('modalContractNote').value,note_to_same_group:!!$('modalNoteAll')?.checked,excluded:$('modalExclude').checked,exclusion_reason:$('modalExcludeReason').value,manual_annual_unit:manual?$('modalManualRate').value:null,manual_price_source:manual?$('modalManualSource').value:''};
  if(manual&&(!data.manual_annual_unit||data.manual_price_source.trim().length<12))throw new Error('Enter the annual unit amount and the source of your manual price (minimum 12 characters).');
  if(data.excluded&&data.exclusion_reason.trim().length<5)throw new Error('Explain why this equipment is excluded (at least 5 characters).');
  if(!Number.isInteger(data.qty)||data.qty<1)throw new Error('Quantity must be a positive whole number.');
  const d=await api(`/api/quotes/${state.quote.id}/assets/${a.id}`,{method:'PUT',body:JSON.stringify(data)});
  apply(d);render();toast('Equipment saved. Quotation total updated.');
  if(next)reviewNext(a.id);else if(rematch)review(a.id);else $('modal').classList.add('hidden');
 }catch(e){toast(e.message,true)}
}
async function searchModal(a){
 try{
  const v=$('modalSearch').value.trim();if(v.length<2){toast('Enter at least two characters to search.',true);return}
  const d=await api('/api/catalog/search?q='+encodeURIComponent(v)+'&limit=20');
  $('modalResults').innerHTML=d.results.length?d.results.map((s,i)=>`<div class="match-choice"><div><b>${esc(s.name)}</b><p>${esc(s.sku)} · ${esc(s.model)} · ${esc(s.console_display)}${s.console_status==='description_only'?' (check)': ''} · RRP ${s.rrp?money(s.rrp):'missing'}</p></div><button data-sel="${i}" ${s.duplicate_sku?'disabled title="Duplicate SKU — data owner to resolve"':''}>${s.duplicate_sku?'Duplicate SKU - blocked':'Confirm this machine'}</button></div>`).join(''):'<div class="issue-banner">No catalogue match found. Check the code, or use an evidenced manual price / exclusion below.</div>';
  document.querySelectorAll('[data-sel]').forEach(btn=>btn.onclick=()=>choose(a,d.results[Number(btn.dataset.sel)]));
 }catch(e){toast(e.message,true)}
}
async function removeAsset(id){if(!confirm('Remove this line from the current quotation?'))return;try{apply(await api(`/api/quotes/${state.quote.id}/assets/${id}`,{method:'DELETE'}));render()}catch(e){toast(e.message,true)}}
async function downloadPdf(){try{
 const saved=await api('/api/quotes/'+state.quote.id,{method:'PUT',body:JSON.stringify(collect())});apply(saved);render();
 const ready=state.summary.ready,url='/api/quotes/'+state.quote.id+(ready?'/issue':'/pdf');
 const r=await fetch(url,{method:ready?'POST':'GET',headers:state.token?{'Authorization':'Bearer '+state.token}:{}});
 if(!r.ok){let e=await r.json();throw new Error(e.detail||'Could not create PDF')}
 const blob=await r.blob(),obj=URL.createObjectURL(blob),link=document.createElement('a');link.href=obj;
 const cd=r.headers.get('content-disposition')||'';link.download=(cd.match(/filename="([^"]+)"/)||[])[1]||`Pulse_Fitness_${state.quote.quote_no}_${ready?'QUOTE':'DRAFT'}.pdf`;
 document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(obj),15000);
 toast(ready?'PDF saved as a versioned, permanent quotation snapshot.':'Draft PDF generated. Complete missing details to finish it.');
 }catch(e){toast(e.message,true)}}
async function recordPipeline(){try{
 const result=await api('/api/quotes/'+state.quote.id+'/pipeline',{method:'POST',body:JSON.stringify({pipeline_status:$('pipelineStatus').value,note:$('pipelineNote').value})});
 apply(result);render();toast('Commercial status recorded. This is a manual status, not a Sage-confirmed sale.');
 }catch(e){toast(e.message,true)}}
async function versions(){try{
 const d=await api('/api/quotes/'+state.quote.id+'/versions');let target=$('versionList');target.classList.toggle('hidden');
 target.innerHTML=d.versions.length?d.versions.map(v=>`<button data-version="${v.version}">Version ${v.version} · ${esc(v.status)} · ${esc(v.created.slice(0,16))}</button>`).join(''):'No saved quote PDF versions yet.';
 target.querySelectorAll('[data-version]').forEach(b=>b.onclick=()=>downloadVersion(Number(b.dataset.version)));
 }catch(e){toast(e.message,true)}}
async function downloadVersion(version){try{
 const r=await fetch(`/api/quotes/${state.quote.id}/versions/${version}/pdf`,{headers:state.token?{'Authorization':'Bearer '+state.token}:{}});
 if(!r.ok)throw new Error('Could not retrieve historical quotation');const u=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=u;a.download=`Pulse_Fitness_${state.quote.quote_no}_v${version}.pdf`;a.click();setTimeout(()=>URL.revokeObjectURL(u),15000);
 }catch(e){toast(e.message,true)}}
function sampleCsv(){const s=`Random export title,24 September 2026,,,,\nPlease quote the equipment at Riverside Leisure,,,,\nEquipment Description, Qty , Product Code, Serial No, Model, Console\nClub Line Treadmill,3,260G-AAS,SN1000-SN1002,260G,Console 5 (Series 2)\nClub Line StepMill,2,200H-AAE,SN301-302,200H,Console 8 (Series 3 Mini)\nInclusive Shoulder Press,1,305H-AGC,SN511,305H,Strength Console\nExisting older treadmill,1,R260G-5.00DRPW,AB-099,260G,Console 5 (Series 2)\nRowing machine - please confirm model,2,,N/A,,\nTOTAL,9,,,,`;return new File([s],'Messy_Leisure_Centre_Assets.csv',{type:'text/csv'})}
function showView(v){
 if(v==='manager'&&!['admin','manager'].includes(state.user?.role))v='catalogue';
 state.view=v;
 const catalog=v==='catalogue'||v==='manager';
 ['builder','register','catalogue','users'].forEach(id=>$(id+'View').classList.toggle('hidden',id==='catalogue'?!catalog:id!==v));
 ['navBuilder','navRegister','navCatalogue','navUsers'].forEach((id,i)=>$(id).classList.toggle('selected',['builder','register','catalogue','users'][i]===(catalog?'catalogue':v)));
 $('catalogueBrowseArea').classList.toggle('hidden',v==='manager');
 $('managerView').classList.toggle('hidden',v!=='manager');
 $('catalogBrowseTab').classList.toggle('active',v==='catalogue');
 $('catalogManageTab').classList.toggle('active',v==='manager');
 $('crumbTitle').textContent={builder:'Smart Quote Builder',register:'Quote Register',catalogue:'Equipment & Prices',manager:'Equipment & Prices',users:'Staff Users'}[v];
 if(v==='register')loadRegister();
 if(v==='manager')loadManager();
 if(v==='catalogue'&&$('catalogSearch').value.trim().length>1)searchCatalogue();
 if(v==='users')loadUsers();
}
let registerRequestId=0;
async function loadRegister(){try{
 const requestId=++registerRequestId;
 const term=$('quoteFind')?.value.trim()||'';
 const status=$('quoteStatusFilter')?.value||'';
 const [d,metrics]=await Promise.all([
  api('/api/quotes?q='+encodeURIComponent(term)+'&pipeline_status='+encodeURIComponent(status)+'&limit=150'),
  api('/api/reporting/summary')]);
 if(requestId!==registerRequestId)return;
 $('pipelineStats').innerHTML=`<div><strong>${metrics.total_quotes}</strong><small>Saved quotes</small></div><div><strong>${metrics.pilot_snapshots}</strong><small>Pilot PDFs archived</small></div><div><strong>${metrics.pipeline['Accepted']||0}</strong><small>Recorded acceptances</small></div><div><strong>${money(metrics.recorded_accepted_annual)}</strong><small>Recorded accepted annual</small></div>`;
 $('quotesList').innerHTML=d.quotes.length?d.quotes.map(q=>`<div class="quote-list-row" data-open="${esc(q.id)}"><div><strong>${esc(q.quote_no)}</strong><p>${esc(q.customer||'Unnamed customer')} · ${esc(q.site||'No site')} · ${esc(q.tier)} · ${esc(q.pipeline_status||'Draft')}</p></div><div class="qval">${money(q.annual)} / yr</div></div>`).join(''):'<p>No quotations match these filters.</p>';
 document.querySelectorAll('[data-open]').forEach(b=>b.onclick=async()=>{apply(await api('/api/quotes/'+b.dataset.open));localStorage.setItem('pulse_quote_id',b.dataset.open);render();showView('builder')})
 }catch(e){toast(e.message,true)}}
async function exportRegister(){try{const r=await fetch('/api/reporting/quotes.csv',{headers:state.token?{'Authorization':'Bearer '+state.token}:{}});if(!r.ok)throw new Error('Could not export register');let url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download='Pulse_SmartQuote_Register.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),20000)}catch(e){toast(e.message,true)}}
async function updateCustomerHints(){try{
 const needle=$('customer').value.trim(),panel=$('customerHints');if(needle.length<3){panel.innerHTML='';return}
 const matches=(await api('/api/customers/suggest?q='+encodeURIComponent(needle))).customers;
 panel.innerHTML=matches.map((c,i)=>`<button type="button" data-customer="${i}">${esc(c.customer)} · ${esc(c.site)}</button>`).join('');
 panel.querySelectorAll('[data-customer]').forEach(b=>b.onclick=()=>{let c=matches[Number(b.dataset.customer)];['customer','site','contact','contact_email','billing_address','delivery_address','account_ref'].forEach(k=>{if(c[k])$(k).value=c[k]});panel.innerHTML='';saveDetails(true)});
 }catch(e){/* optional lookup failure never blocks quoting */}}
async function searchCatalogue(){
 const query=$('catalogSearch').value.trim();
 if(query.length<2){$('catalogResults').innerHTML='<p class="modal-lead">Enter at least two letters or digits.</p>';return}
 const [d,rrpEvidence]=await Promise.all([api('/api/catalog/search?q='+encodeURIComponent(query)+'&limit=30'),api('/api/catalog/rrp-evidence?q='+encodeURIComponent(query)+'&limit=12')]);
 const pkg=(s,t)=>s.monthly_packages?.[t]!=null?money(s.monthly_packages[t]):'RRP / SKU needs review';
 $('catalogResults').innerHTML=`<div class="catalogue-basis">${esc(d.basis)}. Actual quote discount is applied in the quotation builder, not here.</div>`+
 (d.results.map(s=>`<div class="catalogue-result"><div class="catalogue-result-head"><b>${esc(s.sku)} · ${esc(s.name)}</b><span><strong>RRP</strong> ${s.rrp?money(s.rrp):'Unverified'}</span></div><small>Model ${esc(s.model||'not supplied')} · Console: ${esc(s.console_display||s.console)} ${s.console_status==='description_only'?'(description-derived; mapping not verified)':''}</small><div class="catalogue-tiers"><span>Silver <b>${pkg(s,'Silver')}</b></span><span>Gold <b>${pkg(s,'Gold')}</b></span><span>Platinum <b>${pkg(s,'Platinum')}</b></span></div><div class="catalogue-note">${esc(s.duplicate_sku?'Conflicting source SKU – automatic quote blocked':s.pricing_warning)}${s.pricing_rule?' · '+esc(s.rate_group)+' · '+esc(s.pricing_rule):''}</div></div>`).join('')||'<p>No current priced catalogue results. Check historical evidence below.</p>')+
 (d.historical?.results?.length?`<div class="history-heading"><b>Historical equipment library (${d.historical.total} matches)</b><small>Identity evidence only — a historical item is not an approved replacement or current RRP.</small></div>${d.historical.results.map(h=>`<div class="history-result"><b>${esc(h.sku)} · ${esc(h.name||'Unnamed historical item')}</b><small>Model ${esc(h.model||'unknown')} · Console ${esc(h.console||'unverified')} · Seen ${esc(h.first_seen||'?')}–${esc(h.year||'?')} · ${esc(h.source||'Original master')} · ${esc(h.source_revisions?.length||1)} recorded revision(s)${h.source_row?' · source row '+esc(h.source_row):''}</small></div>`).join('')}`:'')+
 (rrpEvidence.items?.length?`<div class="history-heading"><b>August 2026 RRP source (${rrpEvidence.total} potential variants)</b><small>Unapproved RRP evidence — not a quote price. Confirm exact SKU, console and commercial authorisation.</small></div>${rrpEvidence.items.map(x=>`<div class="history-result"><b>${esc(x.sku)} · ${esc(x.name)}</b><small>Console: ${esc(x.console||'Not confirmed')} · Source RRP: ${x.source_rrp!=null?money(x.source_rrp):'Conflicting or unavailable'} · ${esc(rrp2026Labels[x.status]||x.status)} · <b>Source pending approval</b></small></div>`).join('')}`:'');
 attachCatalogueRowActions(d.results);
}

// The catalogue and master price list are a single feature. Staff browse;
// authorised managers open the editing/workbench tab without a second menu.
const catalogueSelection=new Set();
function updateCataloguePrintCount(){
 const n=catalogueSelection.size;
 $('printCatalogSelection').textContent='Print selection ('+n+')';
 $('printCatalogSelection').disabled=n===0||n>75;
 $('clearCatalogSelection').disabled=n===0;
 $('printCatalogSelection').title=n>75?'Maximum 75 machines per printout':'';
}
function attachCatalogueRowActions(products){
 const rows=$('catalogResults').querySelectorAll('.catalogue-result');
 rows.forEach((row,index)=>{
  const item=products[index];
  if(!item)return;
  const header=row.querySelector('.catalogue-result-head');
  if(!header)return;
  const actions=document.createElement('div');actions.className='catalogue-actions';
  const select=document.createElement('label');select.className='catalogue-select';
  const box=document.createElement('input');box.type='checkbox';
  box.dataset.catalogSelect=item.sku;
  box.checked=catalogueSelection.has(item.sku.toUpperCase());
  box.setAttribute('aria-label','Select '+item.sku+' for price printout');
  box.onchange=()=>{
   const code=item.sku.toUpperCase();
   if(box.checked)catalogueSelection.add(code);else catalogueSelection.delete(code);
   updateCataloguePrintCount();
  };
  const caption=document.createElement('span');caption.textContent='Select';
  select.append(box,caption);
  const view=document.createElement('button');view.type='button';view.className='secondary-btn';
  view.textContent='View details';view.onclick=()=>viewCatalogueItem(item.sku);
  actions.append(select,view);header.append(actions);
 });
 updateCataloguePrintCount();
}
function printableFieldValue(x){
 if(x===null||x===undefined||x==='')return 'Not recorded';
 return typeof x==='object'?JSON.stringify(x):String(x);
}
function catalogueFields(record){
 return Object.entries(record||{}).map(([key,value])=>
  '<div class="catalogue-field"><span>'+esc(key.replaceAll('_',' '))+'</span><b>'+esc(printableFieldValue(value))+'</b></div>'
 ).join('');
}
async function viewCatalogueItem(code){
 try{
  const d=await api('/api/catalog/item/'+encodeURIComponent(code));
  const source=d.item,config=d.configuration;
  $('modalTitle').textContent='Equipment details · '+d.sku;
  const prices=['Silver','Gold','Platinum'].map(t=>{
   const p=d.tiers[t];
   return '<div class="catalogue-tier-card"><strong>'+t+'</strong><b>'+(p?money(p.monthly):'—')+'</b><small>per month</small><span>'+(p?money(p.annual):'Unavailable')+' per year</span></div>';
  }).join('');
  const allFields=[
   ['Complete master product record',source],
   ['Pricing configuration',config],
   ['Maintenance tariff values',d.rate],
   ['Console pricing values',d.console_rule],
   ['Master source and date',{master_source:d.source,source_date:d.source_snapshot,pricing_status:d.pricing_status}]
  ].map(([title,data])=>'<h4>'+esc(title)+'</h4><div class="catalogue-fields">'+catalogueFields(data)+'</div>').join('');
  const conflicts=d.duplicate_sku?'<h4>Conflicting SKU records</h4>'+d.duplicate_source_rows.map(x=>'<div class="catalogue-fields">'+catalogueFields(x)+'</div>').join(''):'';
  $('modalContent').innerHTML=
   '<div class="catalogue-detail-intro"><h3>'+esc(source.name||config.name||d.sku)+'</h3><p>'+esc(d.sku)+' · Model '+esc(source.model||'Not recorded')+'</p></div>'+
   '<div class="catalogue-key-fields">'+
   '<div><span>Master RRP</span><b>'+(source.rrp?money(source.rrp):'Not recorded')+'</b></div>'+
   '<div><span>Console</span><b>'+esc(config.console_display||config.console||'Not recorded')+'</b></div>'+
   '<div><span>Maintenance rate group</span><b>'+esc(config.rate_group||'Not assigned')+'</b></div>'+
   '<div><span>Coverage</span><b>'+esc(config.coverage_status||config.eligible||'Not confirmed')+'</b></div></div>'+
   '<h3>Silver / Gold / Platinum contract prices</h3><div class="catalogue-detail-tiers">'+prices+'</div>'+
   '<p class="catalogue-note">'+esc(d.annual_basis)+' · '+esc(d.pricing_status)+
   (d.duplicate_sku?' · Duplicate item code: source price needs reconciliation.':'')+'</p>'+
   '<details class="catalogue-history"><summary>Show all associated master values, source and tariff fields</summary>'+
    allFields+conflicts+'</details>'+
   '<div class="editor-actions"><button type="button" class="secondary-btn" id="catalogDetailClose">Close</button>'+
   (['admin','manager'].includes(state.user?.role)?'<button type="button" class="primary-btn" id="catalogDetailEdit">Edit record</button>':'')+'</div>';
  $('catalogDetailClose').onclick=()=>$('modal').classList.add('hidden');
  if($('catalogDetailEdit'))$('catalogDetailEdit').onclick=()=>editCatalogue(d.sku);
  $('modal').classList.remove('hidden');
 }catch(e){toast(e.message,true)}
}
function catalogPrintHtml(d){
 const headers=['Silver','Gold','Platinum'];
 const rows=d.items.map(x=>{
  const cells=headers.map(t=>{
   const p=x.tiers[t];
   return '<td>'+(p?money(p.monthly):'—')+'</td><td>'+(p?money(p.annual):'—')+'</td>';
  }).join('');
  return '<tr><td>'+esc(x.sku)+'</td><td>'+esc(x.item.name||'')+'</td>'+
   '<td>'+esc(x.item.model||'')+'</td><td>'+esc(x.configuration.console_display||x.configuration.console||'')+'</td>'+
   '<td>'+(x.duplicate_sku?'Conflict':x.item.rrp?money(x.item.rrp):'—')+'</td>'+cells+'</tr>';
 }).join('');
 return '<h1>Pulse Fitness · Equipment & Contract Prices</h1>'+
  '<p>'+d.items.length+' selected machines · '+esc(new Date().toLocaleDateString('en-GB'))+'</p>'+
  '<table class="catalogue-print-table"><thead><tr><th rowspan="2">Item code</th><th rowspan="2">Equipment</th><th rowspan="2">Model</th><th rowspan="2">Console</th><th rowspan="2">RRP</th>'+
  '<th colspan="2">Silver</th><th colspan="2">Gold</th><th colspan="2">Platinum</th></tr>'+
  '<tr><th>Monthly</th><th>Annual</th><th>Monthly</th><th>Annual</th><th>Monthly</th><th>Annual</th></tr></thead><tbody>'+
  rows+'</tbody></table><p class="catalogue-print-footnote">'+esc(d.disclaimer)+'</p>'+
  '<p class="catalogue-print-footnote">Source: '+esc(d.price_source)+' · '+esc(d.price_snapshot)+
  ' · '+esc(d.pricing_status)+'. RRPs are from the master catalogue, never customer invoice selling prices.</p>';
}
async function printCatalogueSelection(){
 const skus=[...catalogueSelection];
 if(!skus.length)return;
 const btn=$('printCatalogSelection');btn.disabled=true;btn.textContent='Preparing prices…';
 try{
  const data=await api('/api/catalog/print-selection',{method:'POST',body:JSON.stringify({skus})});
  const sheet=$('catalogPrintSheet');
  sheet.innerHTML=catalogPrintHtml(data);
  sheet.classList.remove('hidden');
  window.addEventListener('afterprint',()=>sheet.classList.add('hidden'),{once:true});
  window.print();
 }catch(e){toast(e.message,true)}
 finally{updateCataloguePrintCount()}
}

function manualAdd(){
 $('modalTitle').textContent='Add a machine — no SKU needed';
 $('modalContent').innerHTML=`<div class="editor-help">Start by typing what you know: <b>make, model, description, or product code.</b> Choose a confirmed machine from the list, or add an unidentified machine for follow-up.</div>
  <label>Find equipment in the Pulse catalogue<input id="addSearch" class="large-input" placeholder="e.g. rowing machine, Concept2, StepMill, 260G-AAS"></label>
  <div id="addResults" class="add-results"><p class="editor-hint">Search will suggest actual catalogue products; it will not invent a model or a price.</p></div>
  <div class="editor-section">Not in the catalogue or unsure of its code?</div>
  <p class="editor-hint">Record the customer description; the system will recommend matching machines.</p>
  <div class="form-grid"><label>Equipment description<input id="addName" placeholder="e.g. Indoor rowing machine"></label><label>Make / manufacturer<input id="addMake" placeholder="e.g. Concept2, Pulse Fitness"></label><label>Model (if known)<input id="addModel" placeholder="Optional"></label><label>Item code (if known)<input id="addCode" placeholder="Optional"></label><label>Quantity<input id="addQty" type="number" min="1" max="1000" value="1"></label><label>Console / display (if known)<input id="addConsole" placeholder="Optional"></label></div>
  <div class="editor-actions"><button class="secondary-btn" id="addCancel">Cancel</button><button class="primary-btn" id="addUnidentified">Add machine →</button></div>`;
 $('addCancel').onclick=()=>$('modal').classList.add('hidden');
 $('addUnidentified').onclick=()=>addEquipment({sku:$('addCode').value.trim(),name:$('addName').value.trim(),make:$('addMake').value.trim(),model:$('addModel').value.trim(),console:$('addConsole').value.trim(),qty:Number($('addQty').value)},false);
 $('addSearch').oninput=()=>{clearTimeout(window.addSearchTimer);window.addSearchTimer=setTimeout(searchAdd,220)};
 $('modal').classList.remove('hidden');$('addSearch').focus();
}
async function searchAdd(){
 try{
  const query=$('addSearch').value.trim();
  if(query.length<2){$('addResults').innerHTML='<p class="editor-hint">Enter at least two characters.</p>';return}
  const d=await api('/api/catalog/search?q='+encodeURIComponent(query)+'&limit=15');
  $('addResults').innerHTML=d.results.length?d.results.map((s,i)=>`<div class="match-choice add-match"><div><b>${esc(s.name)}</b><p>${esc(s.sku)} · ${esc(s.model)} · ${esc(s.console_display||s.console)} · RRP ${s.rrp?money(s.rrp):'unknown'}</p>${s.duplicate_sku?'<p class="error-hint">Conflicting SKU — must be corrected by data owner</p>':''}</div><button data-addresult="${i}" ${s.duplicate_sku?'disabled':''}>Add machine +</button></div>`).join(''):'<div class="editor-hint">No exact catalogue result. Add a descriptive machine line below; do not guess the code.</div>';
  document.querySelectorAll('[data-addresult]').forEach(b=>b.onclick=()=>addEquipment({sku:d.results[Number(b.dataset.addresult)].sku,qty:Number($('addQty').value)},true));
 }catch(e){toast(e.message,true)}
}
async function addEquipment(data,fromCatalogue){
 try{
  if(!Number.isInteger(data.qty)||data.qty<1||data.qty>1000)throw new Error('Quantity must be 1 to 1,000.');
  if(!data.sku&&!data.name&&!data.model)throw new Error('Enter a description, model, or valid catalogue SKU.');
  const d=await api(`/api/quotes/${state.quote.id}/manual`,{method:'POST',body:JSON.stringify(data)});
  apply(d);state.filter='all';render();
  const a=state.quote.assets[state.quote.assets.length-1];const priced=state.summary.lines.find(l=>l.id===a.id)?.price;if(!priced)review(a.id);else $('modal').classList.add('hidden');
  toast(fromCatalogue?'Machine added and priced automatically.':'Machine added. Choose a catalogue match to calculate its price.');
 }catch(e){toast(e.message,true)}
}
let invoicePending=null;
function invoiceReviewClear(){invoicePending=null;const panel=$('invoicePreview');panel.innerHTML='';panel.classList.add('hidden');}
async function previewInvoices(inputFiles,queueEntryIds=[]){
 const files=[...(inputFiles||[])];if(!files.length)return;
 try{
  invoiceReviewClear();
  if(files.length>10)throw new Error('Please select up to 10 invoices at a time. You can add more afterwards.');
  if(files.some(file=>!file.name.toLowerCase().endsWith('.pdf')))throw new Error('Select PDF invoices only.');
  if(files.some(file=>file.size>35*1024*1024)||files.reduce((sum,f)=>sum+f.size,0)>70*1024*1024)throw new Error('PDF batch too large. Please select a smaller group of invoices.');
  const encoded=[];
  for(const file of files){
    let binary='';const bytes=new Uint8Array(await file.arrayBuffer());
    for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
    encoded.push({filename:file.name,content_base64:btoa(binary)});
  }
  const payload={files:encoded};
  const parsed=await api('/api/quotes/'+state.quote.id+'/invoice-batch-preview',{method:'POST',body:JSON.stringify(payload)});
  invoicePending={payload,parsed,queueEntryIds};
  const cards=parsed.invoices.map(inv=>{
    const tag=inv.already_imported?'Already included — skipped':`${inv.added_lines} lines · ${inv.added_units} machines`;
    const examples=(inv.examples||[]).map(x=>`${esc(x.code)} (${x.qty})`).join(' · ');
    const caution=inv.warnings?.length?`<details><summary>${inv.warnings.length} check(s) for this invoice</summary><ul>${inv.warnings.slice(0,15).map(w=>`<li>${esc(w)}</li>`).join('')}</ul></details>`:'';
    return `<div class="invoice-batch-card"><strong>${esc(inv.filename)}</strong><span>${esc(inv.invoice_no||'No reference')} · ${esc(inv.site||'Unidentified site')}</span><b>${tag}</b>${inv.billed_to&&inv.billed_to.toLowerCase()!==inv.site.toLowerCase()?`<small>Billed to ${esc(inv.billed_to)} — confirm maintenance contract customer</small>`:''}<small>${inv.excluded_lines} accessory/software/commercial lines held out for separate review${inv.skipped_duplicate_units?` · ${inv.skipped_duplicate_units} previously recorded serials skipped`:''}</small>${examples?`<small>Example SKUs: ${examples}</small>`:''}${caution}</div>`;
  }).join('');
  const panel=$('invoicePreview');panel.classList.remove('hidden');
  panel.innerHTML=`<h3>Check invoices before adding equipment</h3>
  <p><b>${parsed.invoices.length} invoice(s) checked</b> · <b>${parsed.total_added_lines} machine lines</b> · <b>${parsed.total_added_units} machines</b> ready to add · ${parsed.duplicate_serials_skipped} duplicate serials omitted</p>
  <p class="invoice-caution">Original invoice SKUs and installed console descriptions are preserved. No alternative selection is required where the exact invoice code identifies the machine. Current maintenance RRP/cover is assessed separately. Historical sale prices are not maintenance RRPs.</p>
  <div class="invoice-batch-list">${cards}</div>
  <div class="invoice-actions"><button id="invoiceConfirm" type="button" class="primary-btn" ${!parsed.ready_to_import?'disabled':''}>Add equipment from these invoices</button><button id="invoiceCancel" type="button" class="secondary-btn">Cancel</button></div>`;
  $('invoiceConfirm').onclick=confirmInvoiceImport;
  $('invoiceCancel').onclick=invoiceReviewClear;
  panel.scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(e){invoiceReviewClear();toast(e.message,true)}
}
async function confirmInvoiceImport(){if(!invoicePending)return;
 const {payload,parsed,queueEntryIds}=invoicePending;const btn=$('invoiceConfirm');
 if(btn){btn.disabled=true;btn.textContent='Adding equipment to draft…';}
 try{
  const result=await api('/api/quotes/'+state.quote.id+'/invoice-batch-import',{method:'POST',body:JSON.stringify({...payload,content_sha256:parsed.content_sha256})});
  invoiceReviewClear();apply(result);state.filter='all';if(queueEntryIds?.length){stagedUploads=stagedUploads.filter(e=>!queueEntryIds.includes(e.id));renderStagedUploads();}render();
  toast(`Added ${result.import_report.equipment_units} machines from ${result.import_report.invoice_count} invoices. ${result.import_report.duplicate_serials_skipped} duplicate serials skipped.`);
  document.querySelector('.assets-panel').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){if(btn){btn.disabled=false;btn.textContent='Retry adding invoices';}toast(e.message,true)}
}
async function importAgreement(file,entryId=null){if(!file)return;
 try{if(!file.name.toLowerCase().endsWith('.pdf'))throw new Error('Please select a maintenance agreement PDF.');
 if(file.size>35*1024*1024)throw new Error('Agreement must be smaller than 35 MB.');
 if(state.quote.assets.length&&!confirm('Replace the current equipment list with this agreement? Cancel to keep your existing lines.'))return;
 const bytes=new Uint8Array(await file.arrayBuffer());let content='';for(let i=0;i<bytes.length;i+=0x8000)content+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
 $('uploadedText').textContent='Reading agreement '+file.name+'…';
 const d=await api('/api/quotes/'+state.quote.id+'/agreement-import',{method:'POST',body:JSON.stringify({filename:file.name,content_base64:btoa(content),mode:'replace'})});
 apply(d);state.filter='all';if(entryId!==null)removeStagedUpload(entryId);render();toast(`Imported ${d.import_report.lines} lines (${d.import_report.units} units) from the previous agreement. Check unmatched legacy products and renewal terms.`);
 document.querySelector('.assets-panel').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){toast(e.message,true)}finally{render()}}
async function importOldCalcs(file,entryId=null){if(!file)return;
 try{
  if(!/\.xlsx?$/i.test(file.name))throw new Error('Please select a historical .xls or .xlsx calculations workbook.');
  if(file.size>30*1024*1024)throw new Error('Old calculations file must be smaller than 30 MB.');
  const bytes=new Uint8Array(await file.arrayBuffer());let content='';for(let i=0;i<bytes.length;i+=0x8000)content+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
  $('uploadedText').textContent='Reading previous calculations '+file.name+'…';
  const d=await api('/api/quotes/'+state.quote.id+'/old-calcs-import',{method:'POST',body:JSON.stringify({filename:file.name,content_base64:btoa(content)})});
  apply(d);state.filter='all';if(entryId!==null)removeStagedUpload(entryId);render();
  toast(`Imported ${d.import_report.source_lines} historic priced lines; matched ${d.import_report.matched}, added ${d.import_report.added}. ${d.import_report.unmatched_codes.length} need reconciliation.`);
  document.querySelector('.assets-panel').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){toast(e.message,true)}finally{render()}
}
async function loadUsers(){try{
 const d=await api('/api/users');$('usersList').innerHTML=d.users.map(u=>`<div class="users-row"><div><b>${esc(u.username)}</b><span class="user-role">${esc(u.role)}</span> · ${u.active?'Active':'Inactive'}</div><div><button class="secondary-btn" data-reset="${esc(u.username)}">Reset password</button><button class="secondary-btn" data-toggle="${esc(u.username)}" data-active="${u.active}">${u.active?'Deactivate':'Activate'}</button></div></div>`).join('');
 document.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=async()=>{let active=b.dataset.active==='1';if(!confirm((active?'Deactivate ':'Activate ')+b.dataset.toggle+'?'))return;try{await api('/api/users/'+encodeURIComponent(b.dataset.toggle)+'/status',{method:'PUT',body:JSON.stringify({active:!active})});loadUsers()}catch(e){toast(e.message,true)}});
 document.querySelectorAll('[data-reset]').forEach(b=>b.onclick=async()=>{const name=b.dataset.reset,pw=prompt('New password for '+name+' (at least 12 characters):');if(pw===null)return;try{await api('/api/users/'+encodeURIComponent(name)+'/password',{method:'PUT',body:JSON.stringify({password:pw})});toast('Password changed and old sessions invalidated.')}catch(e){toast(e.message,true)}});
 }catch(e){toast(e.message,true)}}
async function addUserFromUI(){try{const data={username:$('newUsername').value,role:$('newUserRole').value,password:$('newUserPassword').value};await api('/api/users',{method:'POST',body:JSON.stringify(data)});$('newUserPassword').value='';$('newUsername').value='';toast('Staff account created.');loadUsers()}catch(e){toast(e.message,true)}}
function bind(){
 document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&!$('modal').classList.contains('hidden')){$('modal').classList.add('hidden');return;}
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){
   event.preventDefault();if(state.view==='builder'&&state.quote)saveDetails();
  }
  if(event.altKey&&event.key.toLowerCase()==='n'&&$('modal').classList.contains('hidden')&&state.view==='builder'){
   event.preventDefault();reviewNext();
  }
 });
 document.querySelector('.left-area').insertBefore(document.querySelector('.assets-panel'),$('quoteDetails'));
 $('staffHelp').onclick=quickHelp;$('quoteFind').addEventListener('input',()=>{clearTimeout(window.quoteFindTimer);window.quoteFindTimer=setTimeout(loadRegister,260)});$('quoteStatusFilter').onchange=loadRegister;
 $('newQuote').onclick=()=>newQuote();$('exportQuoteRegister').onclick=exportRegister;$('customer').addEventListener('input',()=>{clearTimeout(window.customerHintTimer);window.customerHintTimer=setTimeout(updateCustomerHints,280)});$('navBuilder').onclick=()=>showView('builder');$('navUsers').onclick=()=>showView('users');$('addStaffUser').onclick=addUserFromUI;$('refreshUsers').onclick=loadUsers;$('navRegister').onclick=()=>showView('register');$('navCatalogue').onclick=()=>showView('catalogue');$('navManager').onclick=()=>showView('manager');
 $('catalogBrowseTab').onclick=()=>showView('catalogue');
 $('catalogManageTab').onclick=()=>showView('manager');
 $('printCatalogSelection').onclick=printCatalogueSelection;
 $('clearCatalogSelection').onclick=()=>{
  catalogueSelection.clear();updateCataloguePrintCount();
  $('catalogResults').querySelectorAll('[data-catalog-select]').forEach(x=>x.checked=false);
 };
 $('saveDetails').onclick=()=>saveDetails();['customer','site','contact','contact_email','prepared_by','billing_address','delivery_address','customer_ref','account_ref','contract_ref','valid_days','term','discount','visits'].forEach(k=>{const el=$(k);if(el){el.addEventListener('change',()=>saveDetails(true));el.addEventListener('input',()=>saveMessage('Unsaved edits…'));}});$('filePicker').onchange=e=>{stageUploadFiles(e.target.files);e.target.value='';};$('browseButton').onclick=()=>$('filePicker').click();$('reviewInvoiceBatch').onclick=reviewStagedInvoices;$('clearUploadQueue').onclick=()=>{stagedUploads=[];invoiceReviewClear();renderStagedUploads();};$('loadSample').onclick=()=>importFile(sampleCsv());$('undoLastImport').onclick=undoLastImport;$('downloadPdf').onclick=downloadPdf;$('quoteVersions').onclick=versions;$('savePipeline').onclick=recordPipeline;$('manualAdd').onclick=manualAdd;$('reviewAll').onclick=()=>{state.filter='all';render()};$('reviewIssues').onclick=()=>{state.filter='issues';render()};$('nextIssue').onclick=()=>reviewNext();$('batchReview').onclick=()=>openBulkReview();$('downloadMatchReport').onclick=downloadMatchingReport;$('downloadSourceRegister').onclick=()=>downloadAssetRegister();$('closeModal').onclick=()=>$('modal').classList.add('hidden');$('modal').onclick=e=>{if(e.target===$('modal'))$('modal').classList.add('hidden')};$('catalogSearch').oninput=()=>{clearTimeout(window.searchTimer);window.searchTimer=setTimeout(searchCatalogue,270)};
 $('managerSearch').oninput=()=>{clearTimeout(window.managerTimer);window.managerTimer=setTimeout(searchManager,260)};
 $('rrp2026Query').oninput=()=>{rrp2026Offset=0;clearTimeout(rrp2026Timer);rrp2026Timer=setTimeout(searchRrp2026,250)};
 $('rrp2026Filter').onchange=()=>{rrp2026Offset=0;searchRrp2026()};
 $('rrp2026Previous').onclick=()=>{rrp2026Offset=Math.max(0,rrp2026Offset-25);searchRrp2026()};
 $('rrp2026Next').onclick=()=>{rrp2026Offset+=25;searchRrp2026()};
 $('downloadRrp2026').onclick=downloadRrp2026;
 $('hybridPropose').onclick=proposeHybridRrp;
 $('managerNew').onclick=()=>editCatalogue(null);$('managerExport').onclick=()=>window.location.href='/api/catalog/admin/export.csv';
 $('managerPreview').onclick=previewMaster;$('managerApply').onclick=applyMaster;$('downloadAllGaps').onclick=downloadAllGaps;
 const z=$('dropzone');z.addEventListener('dragover',e=>{e.preventDefault();z.classList.add('drag')});z.addEventListener('dragleave',()=>z.classList.remove('drag'));z.addEventListener('drop',e=>{e.preventDefault();z.classList.remove('drag');stageUploadFiles(e.dataTransfer.files)});
}

// V4 master catalogue controls: operator-entered audit trail. This does not
// implement identity/authentication or grant autonomous commercial approval.
let currentStage=null;
// Manager-only RRP evidence; choosing a source line never commits its price.
let rrp2026Offset=0,rrp2026RequestId=0,rrp2026Timer;
const rrp2026Labels={source_price_conflict:'Source RRP conflict',source_variant_conflict:'Different configurations',source_rrp_missing:'Missing source price',live_sku_conflict:'Live SKU conflict',not_in_live_catalogue:'Not in current catalogue',live_rrp_missing:'Current RRP missing',rrp_difference:'Different RRP',aligned:'Same RRP'};
async function loadRrp2026(){
 try{
  const info=await api('/api/catalog/admin/rrp-2026/summary');
  const c=info.status_counts;
  $('rrp2026Stats').innerHTML=`<div><b>${esc(info.distinct_source_skus.toLocaleString())}</b><small>2026 product codes</small></div><div><b>${esc((c.rrp_difference||0).toLocaleString())}</b><small>RRPs differ</small></div><div><b>${esc((c.not_in_live_catalogue||0).toLocaleString())}</b><small>Missing live SKUs</small></div><div><b>${esc((c.source_price_conflict||0).toLocaleString())}</b><small>Conflicting source RRPs</small></div>`;
  $('rrp2026Notice').textContent=`Source ${info.source_file} · ${info.source_date} · ${info.source_rows} original rows. All RRPs are awaiting commercial approval; source differences will never reprice a quote automatically.`;
  await searchRrp2026();
 }catch(e){$('rrp2026Results').textContent='Unable to load the 2026 RRP source: '+e.message}
}
async function searchRrp2026(){
 const id=++rrp2026RequestId,term=$('rrp2026Query').value.trim(),filter=$('rrp2026Filter').value;
 try{
  const result=await api('/api/catalog/admin/rrp-2026/search?q='+encodeURIComponent(term)+'&status='+encodeURIComponent(filter)+'&offset='+rrp2026Offset+'&limit=25');
  if(id!==rrp2026RequestId)return;
  $('rrp2026Page').textContent=result.total ? `${rrp2026Offset+1}–${Math.min(result.total,rrp2026Offset+result.items.length)} of ${result.total.toLocaleString()}` : 'No matches';
  $('rrp2026Previous').disabled=rrp2026Offset===0;
  $('rrp2026Next').disabled=rrp2026Offset+result.items.length>=result.total;
  $('rrp2026Results').innerHTML=result.items.length ? result.items.map(x=>{
   const price=x.source_rrp!=null?money(x.source_rrp):x.source_prices?.length?'Conflicting values':'Missing';
   const compare=x.live_rrp!=null?money(x.live_rrp):'Not found';
   const delta=x.difference_gbp!=null?` · Difference ${money(x.difference_gbp)}`:'';
   return `<div class="manager-entry"><div><b>${esc(x.sku)} · ${esc(x.name)}</b><small>2026 source RRP: <strong>${esc(price)}</strong> · Existing SmartQuote: ${esc(compare)}${esc(delta)}</small><small>Model ${esc(x.model)} · Console: ${esc(x.console||'Not confirmed')} · ${esc(rrp2026Labels[x.status]||x.status)}</small><details><summary>Original master evidence (${x.sources.length} row${x.sources.length===1?'':'s'})</summary>${x.sources.map(row=>`<small>${esc(row.sheet)} / row ${esc(row.row)} / column ${esc(row.column)} · ${money(row.rrp)} · ${esc(row.console||'Console unconfirmed')} · ${esc(row.name)}</small>`).join('')}</details></div><div class="rrp-evidence-actions"><button class="secondary-btn" data-rrpfamily="${esc(x.model)}" type="button">Compare family</button>${x.current_catalogue_present?`<button class="secondary-btn" data-rrpedit="${esc(x.sku)}" type="button">Open catalogue</button>`:''}</div></div>`
  }).join(''):'<p class="editor-hint">Nothing in this review category matches your search.</p>';
  $('rrp2026Results').querySelectorAll('[data-rrpfamily]').forEach(b=>b.onclick=()=>showRrp2026Family(b.dataset.rrpfamily));
  $('rrp2026Results').querySelectorAll('[data-rrpedit]').forEach(b=>b.onclick=()=>editCatalogue(b.dataset.rrpedit));
 }catch(e){if(id===rrp2026RequestId)$('rrp2026Results').textContent='Unable to search source RRPs: '+e.message}
}
async function showRrp2026Family(model){
 try{
  const d=await api('/api/catalog/admin/rrp-2026/family/'+encodeURIComponent(model));
  $('rrp2026Family').innerHTML=`<div class="editor-help"><b>${esc(d.model)} — ${d.total} source variants</b> · Unapproved RRP range: ${d.min_unapproved_rrp!=null?money(d.min_unapproved_rrp):'Not available'}–${d.max_unapproved_rrp!=null?money(d.max_unapproved_rrp):'Not available'}. Confirm the exact installed console and SKU before pricing. <button class="link-btn" id="rrpCloseFamily">Close family comparison</button></div>`+
   d.items.map(x=>`<div class="manager-entry"><div><b>${esc(x.sku)} · ${esc(x.name)}</b><small>${esc(x.console||'Console unconfirmed')} · ${x.source_rrp!=null?money(x.source_rrp):'Conflicting / missing source RRP'} · ${esc(rrp2026Labels[x.status]||x.status)}</small></div></div>`).join('');
  $('rrpCloseFamily').onclick=()=>$('rrp2026Family').innerHTML='';
  $('rrp2026Family').scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(e){toast(e.message,true)}
}
async function downloadRrp2026(){
 try{const response=await fetch('/api/catalog/admin/rrp-2026/reconciliation.csv',{headers:state.token?{'Authorization':'Bearer '+state.token}:{}});if(!response.ok)throw Error('Export unavailable');const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download='SmartQuote_2026_RRP_Reconciliation_Review.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),16000)}catch(e){toast(e.message,true)}
}
async function loadManager(){
 try{
  const [info,audit,readiness,gaps,memoryRules,legacyRules]=await Promise.all([api('/api/catalog/admin/info'),api('/api/catalog/admin/audit'),api('/api/catalog/admin/readiness'),api('/api/catalog/admin/matching-gaps'),api('/api/catalog/admin/matching-memory'),api('/api/catalog/admin/hybrid-rrp')]);
  const archive=readiness.historical;
  $('readinessPanel').innerHTML=`<div class="readiness-heading"><div><b>V10 archive & commercial readiness</b><p>${archive.unique_skus.toLocaleString()} historical SKUs · ${archive.alias_codes.toLocaleString()} old codes · ${archive.source_years.join(', ')||'No sources loaded'}</p></div><span class="readiness-status ${readiness.automated_preflight_passes?'ready':'hold'}">${readiness.automated_preflight_passes?'Automated checks passed':'Pilot — review required'}</span></div><ul>${readiness.warnings.map(w=>`<li>${esc(w)}</li>`).join('')||'<li>Automated data checks passed. Manual quote/PDF sign-off is still required.</li>'}</ul><small>${esc(readiness.notice)}</small>`;
  $('managerStats').innerHTML=`<div><b>${info.rows.toLocaleString()}</b><small>Catalogue records</small></div><div><b>${info.unique_skus.toLocaleString()}</b><small>Unique item codes</small></div><div><b>${info.estimate_rows}</b><small>Calculated estimates</small></div><div><b>${info.duplicate_sku_count}</b><small>Conflicting item codes</small></div>`;
  const c=gaps.counts;
  $('matchingGapStats').innerHTML=`<div><b>${(c.total_units||0).toLocaleString()}</b><small>Draft units under review</small></div><div><b>${(c.priced_units||0).toLocaleString()}</b><small>Already priced</small></div><div><b>${(c.unpriced_units||0).toLocaleString()}</b><small>Still without a price</small></div><div><b>${(c.unpriced_groups||0).toLocaleString()}</b><small>Unresolved groups</small></div>`;
  $('matchingGapList').innerHTML=gaps.items.length?gaps.items.slice(0,30).map(x=>`<div class="manager-entry"><div><b>${esc(x.units)} × ${esc(x.source_name||x.source_code||'Unidentified equipment')}</b><small>${esc(x.model||x.source_code||'Unknown model')} · ${esc(x.quote_no)} · ${esc(x.customer)} · ${esc(x.site)}</small><small>${esc(x.issue)}</small></div><button type="button" class="secondary-btn" data-gotoquote="${esc(x.quote_id)}" data-gotoasset="${esc(x.representative_asset_id)}">Review quote</button></div>`).join(''):'<p class="editor-hint">No unresolved equipment in the open draft quotes stored on this installation.</p>';
  $('matchingGapList').querySelectorAll('[data-gotoquote]').forEach(btn=>btn.onclick=async()=>{try{const d=await api('/api/quotes/'+encodeURIComponent(btn.dataset.gotoquote));apply(d);localStorage.setItem('pulse_quote_id',d.quote.id);state.filter='issues';render();showView('builder');review(btn.dataset.gotoasset)}catch(e){toast(e.message,true)}});
  $('matchingMemoryList').innerHTML=memoryRules.rules.length?memoryRules.rules.map(r=>`<div class="manager-entry"><div><b>${esc(r.source.code||r.source.model)} → ${esc(r.sku)}</b><small>${esc(r.source.name||'')} · Console ${esc(r.source.console||'Not recorded')} · ${esc(r.reviewer)} · ${esc(r.updated.slice(0,10))}</small><small>${esc(r.evidence)}${!r.catalogue_sku_available?' · SOURCE SKU CONFLICT': ''} · ${esc(r.status)}</small></div>${r.status==='active'?`<button class="secondary-btn" data-revoke="${esc(r.id)}" type="button">Revoke</button>`:''}</div>`).join(''):'<p class="editor-hint">No manager-verified equipment identities saved yet. Use the optional confirmation during a quotation review.</p>';
  $('matchingMemoryList').querySelectorAll('[data-revoke]').forEach(btn=>btn.onclick=async()=>{const reason=prompt('Why is this exact equipment mapping no longer reliable? (12+ characters)');if(reason===null)return;try{await api('/api/catalog/admin/matching-memory/'+encodeURIComponent(btn.dataset.revoke)+'/revoke',{method:'POST',body:JSON.stringify({reason})});toast('Reviewed identity retired; audit history preserved.');loadManager()}catch(e){toast(e.message,true)}});
  showHybridRrpRules(legacyRules);
  $('managerHistory').innerHTML=audit.history.length?audit.history.map(x=>`<div class="audit-row"><b>${esc(x.sku)}</b> · ${esc(x.modified)} · ${esc(x.operator)}<br><small>${esc(x.reason)}</small></div>`).join(''):'<p class="editor-hint">No catalogue edits recorded yet.</p>';
  if($('managerSearch').value.trim().length>1)await searchManager();
  await loadRrp2026();
 }catch(e){toast(e.message,true)}
}
function showHybridRrpRules(data){
 const target=$('hybridRrpRules');if(!target)return;
 target.innerHTML=`<p class="editor-hint"><b>Approved basis:</b> current equivalent unless an individually reviewed legacy exception is recorded. These records provide review evidence; they do not reprice the quotation.</p>`+
 (data.rules.length?data.rules.map(r=>`<div class="manager-entry"><div><b>${esc(r.legacy_code)} → ${esc(r.basis==='current_equivalent'?r.current_sku:'Legacy exception')}</b><small>${esc(r.status.toUpperCase())} · Console ${esc(r.console||'Not recorded')} · ${esc(r.proposed_by)} · ${esc(r.basis==='legacy_exception'?money(r.exception_rrp):'Exact catalogue RRP')}</small><small>${esc(r.evidence)}${r.approved_by?' · Approved by '+esc(r.approved_by):''}</small></div><div>${r.status==='pending'?`<button class="secondary-btn" type="button" data-hybridapprove="${esc(r.id)}">Verify & approve</button>`:''}${r.status!=='revoked'?`<button class="secondary-btn" type="button" data-hybridrevoke="${esc(r.id)}">Revoke</button>`:''}</div></div>`).join(''):'<p class="editor-hint">No legacy-equivalence decisions entered yet.</p>');
 target.querySelectorAll('[data-hybridapprove]').forEach(b=>b.onclick=async()=>{
  const note=prompt('Independent evidence checked (at least 20 characters). The proposer cannot self-approve.');if(note===null)return;
  if(!confirm('Confirm you independently verified the original machine, console, documentation and pricing basis? This will NOT automatically change quotes.'))return;
  try{await api('/api/catalog/admin/hybrid-rrp/'+encodeURIComponent(b.dataset.hybridapprove)+'/approve',{method:'POST',body:JSON.stringify({note,acknowledge:true})});toast('Review record approved; staff must still confirm individual quote pricing.');loadManager()}catch(e){toast(e.message,true)}
 });
 target.querySelectorAll('[data-hybridrevoke]').forEach(b=>b.onclick=async()=>{
  const reason=prompt('Document why this mapping / exception is no longer valid (20+ characters).');if(reason===null)return;
  try{await api('/api/catalog/admin/hybrid-rrp/'+encodeURIComponent(b.dataset.hybridrevoke)+'/revoke',{method:'POST',body:JSON.stringify({reason})});toast('Legacy pricing reference revoked.');loadManager()}catch(e){toast(e.message,true)}
 });
}
async function proposeHybridRrp(){
 const basis=$('hybridBasis').value;
 const payload={legacy_code:$('hybridLegacy').value,basis,current_sku:basis==='current_equivalent'?$('hybridSku').value:'',
  console:$('hybridConsole').value,exception_rrp:basis==='legacy_exception'?$('hybridExceptionRrp').value:null,
  expires_on:basis==='legacy_exception'?$('hybridExpiry').value:null,
  evidence:$('hybridEvidence').value,reason:$('hybridReason').value};
 try{const response=await api('/api/catalog/admin/hybrid-rrp/propose',{method:'POST',body:JSON.stringify(payload)});toast('Proposed '+response.legacy_code+'; independent manager approval required.');loadManager()}catch(e){toast(e.message,true)}
}

async function downloadAllGaps(){
 try{
  const response=await fetch('/api/catalog/admin/matching-gaps.csv',{headers:state.token?{'Authorization':'Bearer '+state.token}:{}});
  if(!response.ok)throw new Error('Unable to export the equipment matching backlog.');
  const url=URL.createObjectURL(await response.blob());const anchor=document.createElement('a');
  anchor.href=url;anchor.download='Pulse_SmartQuote_Missing_Equipment_Worklist.csv';anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),12000);
 }catch(e){toast(e.message,true)}
}
async function searchManager(){
 const v=$('managerSearch').value.trim();
 if(v.length<2){$('managerResults').innerHTML='<p class="editor-hint">Find equipment by description, model or item code.</p>';return}
 try{
  const d=await api('/api/catalog/search?q='+encodeURIComponent(v)+'&limit=35');
  $('managerResults').innerHTML=d.results.length?d.results.map((x,i)=>`<div class="manager-entry"><div><b>${esc(x.sku)} · ${esc(x.name)}</b><small>RRP ${x.rrp?money(x.rrp):'Missing'} · ${esc(x.rate_group||'Group required')} · ${x.price_origin==='calculated-estimate'?'Calculated tariff price':x.duplicate_sku?'SKU conflict':'Catalogue mapped'}</small></div><button class="secondary-btn" data-manageredit="${i}">Edit / classify</button></div>`).join(''):'<p class="editor-hint">No results. You can create a new equipment record.</p>';
  document.querySelectorAll('[data-manageredit]').forEach(b=>b.onclick=()=>editCatalogue(d.results[Number(b.dataset.manageredit)].sku));
 }catch(e){toast(e.message,true)}
}
async function editCatalogue(code){
 try{
  let data=code?await api('/api/catalog/admin/item/'+encodeURIComponent(code)):{item:{sku:'',name:'',rrp:'',model:'',console:'No Console / N/A'},conflict:false};
  let x=data.item;
  $('modalTitle').textContent=code?'Edit catalogue · '+code:'Create an equipment SKU';
  let groups=state.bootstrap.rates.filter(r=>r.group!=='Manual Review').map(r=>r.group);
  $('modalContent').innerHTML=`<div class="editor-help">Update the shared local equipment master. Its RRP is a source value; Silver, Gold and Platinum estimates are calculated from the selected service rate group. Existing quotes will recalculate with updated pricing.${data.conflict?' <b>This SKU has conflicting original prices: select the correct RRP with documented evidence.</b>':''}</div>
   <div class="form-grid"><label>Item / stock code<input id="mgSku" ${code?'readonly':''} value="${esc(x.sku||'')}"></label><label>Current RRP (£, ex VAT)<input id="mgRrp" type="number" min="0.01" step="0.01" value="${esc(x.rrp||'')}"></label><label>Equipment description<input id="mgName" value="${esc(x.name||'')}"></label><label>Model<input id="mgModel" value="${esc(x.model||'')}"></label><label>Product group<input id="mgGroup" value="${esc(x.group||'')}"></label><label>Category<input id="mgCategory" value="${esc(x.category||'')}"></label><label>Console / display<input id="mgConsole" value="${esc(x.console||'')}">${data.pricing?.console_status==='description_only'?`<small>Source mapping unconfirmed. Product description suggests: ${esc(data.pricing.console_display)}.</small><button type="button" class="secondary-btn" id="mgUseConsole">Use suggested console (after checking)</button>`:''}</label><label>Confirmed service rate group<select id="mgRate"><option value="">Auto-calculate from model/category</option>${groups.map(g=>`<option value="${esc(g)}" ${x.rate_group_override===g?'selected':''}>${esc(g)}</option>`).join('')}</select></label><label>Contract cover status<select id="mgCoverage"><option value="" ${!x.coverage_override?'selected':''}>Not independently confirmed</option><option value="Estimate - approval required" ${x.coverage_override==='Estimate - approval required'?'selected':''}>Estimate — approval required</option><option value="Approved for maintenance" ${x.coverage_override==='Approved for maintenance'?'selected':''}>Data-owner reviewed (pilot only)</option><option value="Not eligible" ${x.coverage_override==='Not eligible'?'selected':''}>Not eligible</option></select></label><label>Console service multiplier<input id="mgFactor" type="number" min="0.7" max="2" step="0.01" value="${esc(x.console_multiplier_override||1)}"><small>Keep 1.00 unless an authorised tariff specifies otherwise.</small></label><label>Edited by<input id="mgOperator" value="${esc($('managerOperator').value)}"></label><label>Change evidence / reason<input id="mgReason" value="${esc($('managerReason').value)}" placeholder="Approved revised product/RRP source and date"></label></div>
   <div class="editor-actions"><button class="secondary-btn" id="mgCancel">Cancel</button><button class="primary-btn" id="mgSave">Save master record</button></div>`;
  if($('mgUseConsole'))$('mgUseConsole').onclick=()=>{$('mgConsole').value=data.pricing.console_display;toast('Suggested console entered. Please verify against product documentation before saving.');};
  $('mgCancel').onclick=()=>$('modal').classList.add('hidden');
  $('mgSave').onclick=async()=>{
   try{
    const item={sku:$('mgSku').value,name:$('mgName').value,rrp:$('mgRrp').value,model:$('mgModel').value,group:$('mgGroup').value,category:$('mgCategory').value,console:$('mgConsole').value,rate_group_override:$('mgRate').value,coverage_override:$('mgCoverage').value,console_multiplier_override:$('mgFactor').value};
    let endpoint=code?'/api/catalog/admin/item/'+encodeURIComponent(code):'/api/catalog/admin/item';
    await api(endpoint,{method:code?'PUT':'POST',body:JSON.stringify({item,operator:$('mgOperator').value,reason:$('mgReason').value})});
    $('modal').classList.add('hidden');toast('Catalogue record saved. Quotes will use updated prices.');
    apply(await api('/api/quotes/'+state.quote.id));render();await loadManager();
   }catch(e){toast(e.message,true)}
  };
  $('modal').classList.remove('hidden');
 }catch(e){toast(e.message,true)}
}
async function previewMaster(){
 try{
  const f=$('masterUpload').files?.[0];if(!f)throw new Error('Choose a .xlsx or .csv master price list.');
  if(f.size>25*1024*1024)throw new Error('The selected file is over 25 MB.');
  $('masterPreview').innerHTML='<p class="editor-hint">Reading price list and checking conflicts…</p>';
  const bytes=new Uint8Array(await f.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.slice(i,i+32768));
  const d=await api('/api/catalog/admin/import/preview',{method:'POST',body:JSON.stringify({filename:f.name,content_base64:btoa(binary)})});
  currentStage=d.stage_id;
  $('masterPreview').innerHTML=`<div class="import-stats">${Object.entries(d.counts).map(([k,v])=>`<span><b>${esc(k)}:</b> ${v}</span>`).join('')}</div><p class="editor-hint">${esc(d.total)} source rows · ${esc(d.source_sheets.join(', '))} · ${esc(d.message)}</p><div class="table-scroller"><table class="asset-table"><thead><tr><th>Action</th><th>Item code</th><th>Description</th><th>New RRP</th></tr></thead><tbody>${d.preview.map(r=>`<tr><td>${esc(r.action)}</td><td>${esc(r.sku)}</td><td>${esc(r.name)}</td><td>${r.rrp?money(r.rrp):esc(r.error||'Invalid')}</td></tr>`).join('')}</tbody></table></div><p class="editor-hint">Conflicts/invalid rows are skipped, never guessed. Only New and Changed items will be applied. Snapshot stays in JSON; edits are stored in a separate local register.</p>`;
  $('managerApply').disabled=false;
 }catch(e){currentStage=null;$('managerApply').disabled=true;toast(e.message,true);$('masterPreview').innerHTML='<p class="issue-banner">Price list could not be staged. Nothing was changed.</p>'}
}
async function applyMaster(){
 try{
  if(!currentStage)throw new Error('Preview a price list first.');
  const operator=$('managerOperator').value,reason=$('managerReason').value;
  const d=await api('/api/catalog/admin/import/apply',{method:'POST',body:JSON.stringify({stage_id:currentStage,operator,reason,acknowledge:$('masterAcknowledged').checked})});
  currentStage=null;$('managerApply').disabled=true;
  $('masterPreview').innerHTML=`<div class="editor-help">Imported ${d.updated} items, skipped ${d.skipped} lines including ${d.conflicts} conflicts. Open drafts will refresh; previous PDFs are preserved.</div>`;
  apply(await api('/api/quotes/'+state.quote.id));render();await loadManager();toast('Master catalogue changes applied.');
 }catch(e){toast(e.message,true)}
}

init();
