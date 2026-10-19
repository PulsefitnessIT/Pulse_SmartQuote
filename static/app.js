/* Pulse SmartQuote: offline-friendly frontend, no third-party scripts. */
let state={quote:null,summary:null,bootstrap:null,view:'builder',filter:'all',groups:[],token:sessionStorage.getItem('smartquote_token'),user:null};
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>'£'+Number(n||0).toLocaleString('en-GB',{minimumFractionDigits:2,maximumFractionDigits:2});
const toast=(message,error=false)=>{const t=$('toast');t.innerText=message;t.className='toast'+(error?' error':'');setTimeout(()=>{t.className='toast hidden'},5000)};
async function api(path,options={}){const r=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(state.token?{'Authorization':'Bearer '+state.token}:{}),...(options.headers||{})}});let data;try{data=await r.json()}catch(e){data={detail:`Server error (${r.status})`}}if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data}
async function init(){
 $('loginForm').onsubmit=async e=>{e.preventDefault();try{
  const result=await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:$('loginName').value,password:$('loginPassword').value})});
  state.token=result.token;sessionStorage.setItem('smartquote_token',result.token);$('loginPassword').value='';$('loginGate').classList.add('hidden');await launchWorkspace();
 }catch(ex){$('loginError').textContent=ex.message}};
 try{const health=await api('/api/health');if(health.auth_setup_required){$('loginError').textContent='No administrator account yet. In the application folder run: python manage_users.py bootstrap';$('loginGate').classList.remove('hidden');return}
 await launchWorkspace();}
 catch(e){$('loginGate').classList.remove('hidden');$('loginError').textContent=state.token?'Session expired. Please sign in again.':'Please sign in to continue.';sessionStorage.removeItem('smartquote_token');state.token=null}
}
async function launchWorkspace(){
 const profile=await api('/api/auth/me');state.user=profile.user;
 $('navManager').style.display=['admin','manager'].includes(profile.user.role)?'':'none';
 $('navUsers').style.display=profile.user.role==='admin'?'':'none';
 $('managerOperator').value=profile.user.username;$('managerOperator').readOnly=true;
 state.bootstrap=await api('/api/bootstrap');const old=localStorage.getItem('pulse_quote_id');if(old){try{apply(await api('/api/quotes/'+old))}catch(e){await newQuote()}}else{await newQuote()}
 render();if(!state.bound){bind();state.bound=true}
 $('loginGate').classList.add('hidden');
}
async function newQuote(){const d=await api('/api/quotes',{method:'POST'});apply(d);localStorage.setItem('pulse_quote_id',d.quote.id);render();showView('builder')}
function apply(data){state.quote=data.quote;state.summary=data.summary;state.groups=data.display_groups||[]}
function viewData(){return {q:state.quote,s:state.summary}}
function render(){if(!state.quote)return;const{q,s}=viewData();$('quoteNumber').textContent=q.quote_no;$('summaryCode').textContent=q.quote_no;$('pipelineStatus').value=q.pipeline_status||'Draft';$('pipelineNote').value=q.pipeline_note||'';
 ['customer','site','contact','contact_email','prepared_by','billing_address','delivery_address','customer_ref','account_ref','contract_ref','valid_days','term','discount','visits'].forEach(k=>{if($(k))$(k).value=(k==='valid_days'?q[k]??30:q[k]??'')});
 $('tierOptions').innerHTML=Object.entries(state.bootstrap.packages).map(([tier,p])=>`<button class="tier-card ${q.tier===tier?'active':''}" data-tier="${tier}"><span>${tier==='Silver'?'ESSENTIAL':tier==='Gold'?'RECOMMENDED':'COMPREHENSIVE'}</span><strong>${esc(tier)}</strong><small>${esc(p.subtitle)}</small></button>`).join('');
 document.querySelectorAll('[data-tier]').forEach(btn=>btn.onclick=async()=>{state.quote.tier=btn.dataset.tier;$('visits').value=btn.dataset.tier==='Silver'?'0':(Number($('visits').value)===0?'1':$('visits').value);await saveDetails(true)});
 $('metrics').innerHTML=[['Equipment rows',s.rows,'▣'],['Units on register',s.units,'◫'],['Identified assets',q.assets.filter(a=>!!a.selected).length,'✓'],['Needs a price',s.rows-s.excluded_rows-s.priced_rows,'!']].map(([l,v,i])=>`<div class="metric"><div><span>${esc(l)}</span><strong>${esc(v)}</strong></div><div class="m-icon">${esc(i)}</div></div>`).join('');
 $('sumAnnualLabel').textContent=s.priced_rows<s.rows-s.excluded_rows?'PARTIAL subtotal (unpriced machines excluded)':'Proposed annual maintenance';
 $('annual').textContent=money(s.annual);$('monthly').textContent=money(s.monthly);$('termTotal').textContent=money(s.term_total);$('sumTier').textContent=q.tier;$('sumUnits').textContent=s.units;$('sumLines').textContent=`${s.priced_rows} / ${s.rows}`;$('sumTerm').textContent=s.term+' year'+(s.term>1?'s':'');$('assetCount').textContent=s.rows;
 $('uploadedText').textContent=q.files.length?`${q.files.length} file(s) imported`:'No files uploaded yet';
 const oldCalc=q.historic_calcs||null;const comp=$('oldCalcBanner');if(comp){comp.classList.toggle('hidden',!oldCalc);if(oldCalc){comp.innerHTML=`<b>Previous calculations:</b> ${esc(oldCalc.filename)} · ${oldCalc.line_count} lines / ${oldCalc.machine_count} machines · historic equipment total ${money(oldCalc.source_line_sum)} · historic annual contract ${money(oldCalc.previous_quote_annual)}.<br><small>New catalogue-priced quotation: ${money(s.annual)} / year ex VAT${s.issues.length?' · DRAFT, outstanding current-RRP/contract checks':''}. Historical prices are for audit and comparison, never automatic approved 2026 RRPs.</small>`;}}
 const renewal=q.renewal||null;const rb=$('renewalBanner');rb.classList.toggle('hidden',!renewal);
 if(renewal){rb.innerHTML=`<b>Renewal imported:</b> ${esc(renewal.agreement_ref||'Previous agreement')} · ${esc(renewal.previous_package||'')} cover · Previous annual charge ${esc(renewal.previous_annual||'unknown')} · Ends ${esc(renewal.previous_end||'unknown')}.<br><small>Equipment is priced afresh using today's SmartQuote catalogue; the old total is a comparison only.</small>${renewal.fixed_price_extension?'<div class="contract-issue">Important: the previous agreement offers an extension at the SAME annual price. Check whether the customer is entitled to exercise this option before proposing different pricing.</div><label><input type="checkbox" id="renewalOptionChecked" '+(q.renewal_option_checked?'checked':'')+'> I have checked the existing fixed-price extension option and confirmed how to proceed.</label>':''}`;const checkbox=$('renewalOptionChecked');if(checkbox)checkbox.onchange=()=>saveDetails(true)}
 const pmap=Object.fromEntries(s.lines.map(l=>[l.id,l.price]));
 const needs=a=>(!a.excluded&&(!pmap[a.id]||pmap[a.id]?.basis==='historic-reference'||a.qty_issue)) || (a.excluded&&!(a.exclusion_reason||'').trim());
 const todo=q.assets.filter(needs);
 $('reviewIssuesCount').textContent=todo.length;
 $('reviewAll').classList.toggle('active',state.filter==='all');$('reviewIssues').classList.toggle('active',state.filter==='issues');
 const displayed=state.groups.length?state.groups:q.assets.map(a=>({representative:a,qty:a.qty,ids:[a.id],serials:a.serial?[a.serial]:[],source_rows:[a.source_row],price:pmap[a.id]}));
 const shown=state.filter==='issues'?displayed.filter(g=>g.ids.some(id=>todo.some(a=>a.id===id))):displayed;
 $('assetBody').innerHTML=shown.length?shown.map(g=>{
  const a={...g.representative,qty:g.qty};
  const selected=a.selected,pr=g.price;
  const label=a.excluded?'Excluded':a.qty_issue?'Check quantity':!pr?'Needs a price':pr.basis==='historic-reference'?'Historic RRP':a.manual_annual_unit!=null?'Manual rate':selected?.price_origin==='historic-family-estimate'?'Family estimate':selected?.price_origin==='calculated-estimate'?'Calculated':'Priced';
  const cls=a.excluded?'':a.qty_issue?'bad':!pr?'bad':['calculated-estimate','historic-family-estimate'].includes(selected?.price_origin)?'warning':'ok';
  return `<tr class="${a.excluded?'is-excluded':''}"><td><b>${esc(a.display_name||a.name||a.code||a.model||'Unlabelled asset')}</b><small>${esc(a.code||a.model||'No product code')} · ${esc(a.site||'Site unspecified')} · ${esc(a.source_sheet)} / row ${esc(a.source_row)}</small>${g.serials?.length?`<small>${g.qty===1?'SN':'Serials'}: ${esc(g.serials.slice(0,3).join(', '))}${g.serials.length>3?' +'+(g.serials.length-3)+' more in asset register':''}</small>`:''}<small>${g.ids.length>1?g.ids.length+' source rows grouped · ':''}Original rows ${esc(g.source_rows.length>3?g.source_rows[0]+'–'+g.source_rows[g.source_rows.length-1]:g.source_rows.join(', '))}</small>${g.assets?.length>1?`<details class="asset-register"><summary>View ${g.assets.length} individual records and serials</summary><div class="asset-register-list">${g.assets.map(x=>`<div>Row ${esc(x.source_row)} · ${esc(x.asset_tag||'No asset ID')} · Serial: ${esc(x.serial||'not supplied')} · ${esc(x.source_description||'')}</div>`).join('')}</div></details>`:''}${a.qty_issue?`<small class="qty-alert">${esc(a.qty_issue)}</small>`:''}</td><td><b>${esc(selected?.name||a.name||'Choose equipment')}</b><small>${esc(selected?.sku||selected?.model||'Unmatched')} ${(a.console||selected?.console_display||selected?.console)?' · Console: '+esc(a.console||selected.console_display||selected.console):''}</small><small>${esc(a.match_type)}${selected?.price_origin==='historic-family-estimate'?' · <b>INDICATIVE from modern family RRP (not exact historic SKU)</b>':''}${selected?.price_origin==='calculated-estimate'?' · priced from RRP and tariff':''}${selected?.reference_sku?' · Reference: '+esc(selected.reference_sku)+'; RRP '+esc(selected.reference_range||''):''}</small>${a.historic_evidence?'<small>Historical '+esc(a.historic_evidence.basis)+': '+esc(a.historic_evidence.variant_count)+' variant(s) · '+esc((a.historic_evidence.variants||[]).slice(0,2).map(v=>v.sku+' ('+v.year+', '+(v.console||'console unknown')+')').join('; '))+' · Identity only, check before quoting.</small>':''}${a.historic_master?'<small>2025 legacy master: '+a.historic_master.variant_rows+' variants; consoles '+esc((a.historic_master.consoles||[]).slice(0,3).join(', ')||'unspecified')+' (identity reference only)</small>':''}${a.historic_rrp?'<small>Original calcs RRP: '+money(a.historic_rrp)+' · old annual/unit '+money(a.historic_annual_unit)+(pr?.basis==='historic-reference'?' · CURRENT RRP REQUIRED':'')+'</small>':''}</td><td>${esc(a.qty)}</td><td><span class="price-col">${a.excluded?'—':pr?money(pr.unit/12):'TBC'}</span><small>per machine · ex VAT</small></td><td><span class="price-col">${a.excluded?'EXCLUDED':pr?money(pr.annual):'TBC'}</span><small>${pr?money(pr.unit/12*a.qty)+'/month for line':'needs a price'}</small></td><td><span class="status ${cls}">${label}</span><br><button class="review-btn" data-review="${esc(a.id)}">✎ Edit line</button><button class="tiny-del" title="Permanently remove line" data-delete="${esc(a.id)}">✕</button></td></tr>`;
 }).join(''):'<tr><td colspan="6" class="empty-table">'+(state.filter==='issues'?'All included equipment has a price. Choose All equipment or generate your PDF.':'Drop in an asset list or try the sample import to begin.')+'</td></tr>';
 document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>review(b.dataset.review));document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>removeAsset(b.dataset.delete));
 let matched=q.assets.filter(a=>a.selected&&!a.excluded).length,excluded=q.assets.filter(a=>a.excluded).length;
 $('matchBreakdown').textContent=`${matched} matched · ${todo.length} need attention · ${excluded} excluded`;
 const health=s.issues.slice(0,9);$('healthList').innerHTML=health.length?health.map(v=>`<div class="health-item">${esc(v)}</div>`).join('')+(s.issues.length>9?`<div class="health-item">+${s.issues.length-9} more issues — see equipment list</div>`:''):'<div class="health-item healthy">Everything needed is in place. Click Generate Quote PDF.</div>';
 $('healthBadge').className='health-badge '+(s.ready?'ok':'warning');$('healthBadge').textContent=s.ready?'Ready to generate':`${s.issues.length} detail${s.issues.length===1?'':'s'} needed`;
 if(!q.assets.length){$('healthList').innerHTML='<div class="health-item">Upload equipment and complete the customer details to begin.</div>'}
 $('advisoryNote').textContent=s.estimated_rows?`${s.estimated_rows} equipment line(s) use catalogue-derived estimates (including possible historic-model comparisons). Check the reference details before customer issue; this is not an exact old-SKU price.`:'Matching and pricing do not require a separate review step.';
}
function collect(){let v={};['customer','site','contact','contact_email','prepared_by','billing_address','delivery_address','customer_ref','account_ref','contract_ref','valid_days','term','discount','visits'].forEach(k=>v[k]=$(k).value);v.tier=state.quote.tier;if(state.quote.renewal?.fixed_price_extension)v.renewal_option_checked=!!$('renewalOptionChecked')?.checked;return v}
async function saveDetails(quiet=false){try{const d=await api('/api/quotes/'+state.quote.id,{method:'PUT',body:JSON.stringify(collect())});apply(d);render();if(!quiet)toast('Quote updated. Prices recalculated automatically.')}catch(e){toast(e.message,true)}}
async function importFile(file){if(!file)return;const z=$('dropzone');z.classList.add('busy');$('uploadedText').textContent='Reading '+file.name+'…';try{
  if(file.size>25*1024*1024)throw new Error('Please split this file: 25 MB limit for a single import.');
  const bytes=new Uint8Array(await file.arrayBuffer());let s='';for(let i=0;i<bytes.length;i+=0x8000)s+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
  const d=await api('/api/quotes/'+state.quote.id+'/import',{method:'POST',body:JSON.stringify({filename:file.name,content_base64:btoa(s)})});apply(d);state.filter='all';render();toast(`${d.import_report.added} assets imported into ${d.import_report.grouped_lines} equipment groups. Review any unpriced groups.`);document.querySelector('.assets-panel').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){toast(e.message,true)}finally{z.classList.remove('busy');$('filePicker').value=''}}
function issueAssets(){const cost=Object.fromEntries(state.summary.lines.map(x=>[x.id,x.price]));return state.quote.assets.filter(a=>!a.excluded&&(!cost[a.id]||a.qty_issue))}
function reviewNext(afterId=null){const list=issueAssets();let next=list[0];if(afterId){const all=state.quote.assets,ix=all.findIndex(a=>a.id===afterId);next=all.slice(ix+1).concat(all.slice(0,ix+1)).find(a=>list.some(t=>t.id===a.id));}if(next)review(next.id);else{$('modal').classList.add('hidden');toast('All included equipment is priced. Finish the customer details and generate the quote.');}}
function review(id){
 const a=state.quote.assets.find(x=>x.id===id);if(!a)return;
 $('modalTitle').textContent=`Edit equipment line · ${a.source_sheet||'Manual'}`;
 const idx=state.quote.assets.findIndex(x=>x.id===id);
 const problems=a.issues||[];
 const price=state.summary.lines.find(l=>l.id===a.id)?.price;
 const priced=!!price&&!a.qty_issue;const issueHtml=a.qty_issue?`<div class="issue-banner"><b>Check imported quantity</b><p>${esc(a.qty_issue)}</p></div>`:priced?`<div class="editor-help"><b>${a.selected?.price_origin==='historic-family-estimate'?'Indicative historic-family estimate — verify old SKU / console.':'Price ready.'}</b> This machine has a calculated amount in the draft. You can still change its details below.${a.selected?.reference_warning?'<br>'+esc(a.selected.reference_warning):''}</div>`:problems.length?`<div class="issue-banner"><b>Machine or price missing</b><ul>${problems.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:'<div class="editor-help">Search for the machine to calculate its cost.</div>';
 const options=[...(a.selected?[a.selected]:[]),...(a.candidates||[])];
 const choices=options.map((v,i)=>`<div class="match-choice"><div><b>${esc(v.name||'Unknown equipment')}</b><p>${esc(v.sku||v.service_key||'No SKU')} · ${esc(v.console_display||v.console||'Console unknown')} · RRP ${v.rrp?money(v.rrp):'not supplied'}</p></div>${v.price_origin==='historic-family-estimate'?'<span class="editor-hint">Family-price reference only. Search for a verified machine to replace it.</span>':`<button data-choose="${i}" ${v.duplicate_sku?'disabled title="Conflicting duplicate SKU"':''}>${a.selected&&i===0?'Reconfirm':'Confirm this machine'}</button>`}</div>`).join('');
 $('modalContent').innerHTML=`<div class="edit-toolbar"><span>LINE ${idx+1} OF ${state.quote.assets.length} · ORIGINAL SPREADSHEET ROW ${esc(a.source_row)}</span><button id="editorNext" class="secondary-btn" type="button">Next unpriced line →</button></div>${issueHtml}
  <div class="editor-help"><b>Current proposed price:</b> ${price?money(price.unit/12)+' per unit per month · '+money(price.unit)+' per unit per year':'Select a machine to calculate the price'} (ex VAT, ${esc(state.quote.tier)}, after discount)</div><div class="editor-section">1 · Correct the imported equipment details</div>
  <div class="form-grid"><label>Imported machine description<input id="modalName" value="${esc(a.name||'')}" placeholder="e.g. Pulse Club Line Treadmill"></label><label>Product / item code (SKU)<input id="modalCode" value="${esc(a.code||'')}" placeholder="e.g. 260G-AAS"><span class="field-aside">Changing the SKU triggers new catalogue matching when saved.</span></label><label>Model<input id="modalModel" value="${esc(a.model||'')}" placeholder="e.g. 260G"></label><label>Console / display (optional)<input id="modalConsole" list="consoleList" value="${esc(a.console||'')}" placeholder="Select a console or type your own"><datalist id="consoleList"><option value="Console 3.5 (Series 1)"><option value="Console 5 (Series 2)"><option value="Console 6 (Series 3)"><option value="Console 8 (Series 3 Mini)"><option value="7-inch Tactile Key Console"><option value="10.1-inch Tactile Key Console"><option value="10.1-inch Cirrus V4 Touchscreen"><option value="18.5-inch Cirrus V4 Touchscreen"><option value="19-inch monitor"><option value="PM5 Console"><option value="Other / Third Party"><option value="Strength Console"></datalist><span class="field-aside">Select the actual console where known. A different console may require a different SKU/RRP; check the catalogue variant.</span></label><label>Manufacturer<input id="modalMake" value="${esc(a.make||'')}" placeholder="Pulse Fitness / Third-party"></label><label>Quantity<input id="modalQty" type="number" min="1" step="1" value="${esc(a.qty)}"></label><label>Serial number(s)<input id="modalSerial" value="${esc(a.serial||'')}"></label><label>Equipment location / site<input id="modalSite" value="${esc(a.site||'')}"></label></div>
  <label>Customer-facing quotation description<input id="modalDisplay" value="${esc(a.display_name||'')}" placeholder="Leave blank to use the catalogue's official description"><span class="field-aside">Only affects the PDF description. It does not change the SKU or underlying price.</span></label>
  <button class="secondary-btn" type="button" id="saveAndMatch" style="margin:12px 0">Save these details & re-check catalogue</button>
  <div class="editor-section">2 · Suggested machines and catalogue search</div><p class="editor-hint">Suggestions use the imported name or model, not a verified match. Check the full product description and correct console before selecting. Search by description, make, model or item code.</p>
  <div class="match-choices-scroll">${choices||'<p class="editor-hint">No automatic match was found. Search the catalogue, or add an evidenced manual annual unit rate below.</p>'}</div>
  <div class="searchline"><input id="modalSearch" placeholder="e.g. rower, Concept2, storage rack, 260G"><button id="modalFind" class="secondary-btn">Find machine</button></div><div id="modalResults"></div>
  <div class="editor-section">3 · Exceptional handling (only when needed)</div><div class="manual-box"><label class="edit-check"><input type="checkbox" id="enableManual" ${a.manual_annual_unit!=null?'checked':''}> Use an externally verified manual annual maintenance rate</label><div id="manualFields" class="${a.manual_annual_unit==null?'hidden':''}"><div class="form-grid"><label>Annual unit price (ex VAT)<input id="modalManualRate" type="number" step="0.01" min="0.01" value="${esc(a.manual_annual_unit??'')}" placeholder="£ per unit per year"></label><label>Manual price source/reference<input id="modalManualSource" value="${esc(a.manual_price_source||'')}" placeholder="Approved price list / manager email, date"></label></div><p class="editor-hint"><b>Commercial control:</b> manual rates are not invented or auto-approved. Enter a genuine authorised source and include a source for the manual price. This replaces automated pricing for this line. The quotation discount is applied to this manual base rate. Review the final discounted amount.</p></div></div>
  <div class="exclude-box"><label class="edit-check"><input type="checkbox" id="modalExclude" ${a.excluded?'checked':''}> Exclude this machine from the maintenance quotation</label><div id="excludeFields" class="${a.excluded?'':'hidden'}"><label>Reason for exclusion <span class="required-label">(required)</span><input id="modalExcludeReason" value="${esc(a.exclusion_reason||'')}" placeholder="e.g. Customer declined cover for this machine"></label><p class="editor-hint">Excluded equipment remains traceable and will be shown separately on the PDF. It contributes £0 to the quote.</p></div></div>
  <div class="editor-actions"><button class="secondary-btn" id="modalCancel">Close without saving</button><button class="secondary-btn" id="modalSaveNext">Save & next unpriced line →</button><button class="primary-btn" id="modalSave">Save changes ✓</button></div>`;
 const same=state.quote.assets.filter(b=>!b.excluded&&b.id!==a.id&&b.name===a.name&&b.model===a.model&&b.code===a.code&&b.console===a.console&&b.site===a.site);
 if(same.length){$('modalContent').insertAdjacentHTML('beforeend',`<label class="checkline"><input id="bulkSameEquipment" type="checkbox" checked> Apply this catalogue choice to ${same.length} other identical machine(s) at this site (each serial number stays separate)</label>`)}
 document.querySelectorAll('[data-choose]').forEach(b=>b.onclick=()=>choose(a,options[Number(b.dataset.choose)]));
 $('modalFind').onclick=()=>searchModal(a);$('modalSearch').onkeydown=e=>{if(e.key==='Enter')searchModal(a)};
 $('modalSave').onclick=()=>updateAsset(a,false);$('modalSaveNext').onclick=()=>updateAsset(a,true);
 $('saveAndMatch').onclick=()=>updateAsset(a,false,true);$('modalCancel').onclick=()=>$('modal').classList.add('hidden');$('editorNext').onclick=()=>reviewNext(a.id);
 $('enableManual').onchange=e=>$('manualFields').classList.toggle('hidden',!e.target.checked);
 $('modalExclude').onchange=e=>$('excludeFields').classList.toggle('hidden',!e.target.checked);
 $('modal').classList.remove('hidden');
}
async function choose(a,option){
 try{const d=await api(`/api/quotes/${state.quote.id}/resolve`,{method:'POST',body:JSON.stringify({asset_id:a.id,option,apply_to_similar:!!$('bulkSameEquipment')?.checked})});apply(d);render();$('modal').classList.add('hidden');toast('Machine selected and priced. Other identical assets were updated when requested.');}
 catch(e){toast(e.message,true)}
}
async function updateAsset(a,next=false,rematch=false){
 try{
  const manual=$('enableManual').checked;
  const data={name:$('modalName').value,code:$('modalCode').value,model:$('modalModel').value,console:$('modalConsole').value,make:$('modalMake').value,qty:Number($('modalQty').value),serial:$('modalSerial').value,site:$('modalSite').value,display_name:$('modalDisplay').value,excluded:$('modalExclude').checked,exclusion_reason:$('modalExcludeReason').value,manual_annual_unit:manual?$('modalManualRate').value:null,manual_price_source:manual?$('modalManualSource').value:''};
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
function showView(v){state.view=v;['builder','register','catalogue','manager','users'].forEach(id=>$(id+'View').classList.toggle('hidden',v!==id));['navBuilder','navRegister','navCatalogue','navManager','navUsers'].forEach((id,i)=>$(id).classList.toggle('selected',['builder','register','catalogue','manager','users'][i]===v));$('crumbTitle').textContent={builder:'Smart Quote Builder',register:'Quote Register',catalogue:'Equipment Catalogue',manager:'Master Price List',users:'Staff Users'}[v];if(v==='register')loadRegister();if(v==='manager')loadManager();if(v==='users')loadUsers()}
async function loadRegister(){try{
 const [d,metrics]=await Promise.all([api('/api/quotes'),api('/api/reporting/summary')]);
 $('pipelineStats').innerHTML=`<div><strong>${metrics.total_quotes}</strong><small>Saved quotes</small></div><div><strong>${metrics.pilot_snapshots}</strong><small>Pilot PDFs archived</small></div><div><strong>${metrics.pipeline['Accepted']||0}</strong><small>Recorded acceptances</small></div><div><strong>${money(metrics.recorded_accepted_annual)}</strong><small>Recorded accepted annual</small></div>`;
 $('quotesList').innerHTML=d.quotes.length?d.quotes.map(q=>`<div class="quote-list-row" data-open="${esc(q.id)}"><div><strong>${esc(q.quote_no)}</strong><p>${esc(q.customer||'Unnamed customer')} · ${esc(q.site||'No site')} · ${esc(q.tier)} · ${esc(q.pipeline_status||'Draft')}</p></div><div class="qval">${money(q.annual)} / yr</div></div>`).join(''):'<p>No quotations yet.</p>';
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
 const d=await api('/api/catalog/search?q='+encodeURIComponent(query)+'&limit=30');
 const pkg=(s,t)=>s.monthly_packages?.[t]!=null?money(s.monthly_packages[t]):'RRP / SKU needs review';
 $('catalogResults').innerHTML=`<div class="catalogue-basis">${esc(d.basis)}. Actual quote discount is applied in the quotation builder, not here.</div>`+
 (d.results.map(s=>`<div class="catalogue-result"><div class="catalogue-result-head"><b>${esc(s.sku)} · ${esc(s.name)}</b><span><strong>RRP</strong> ${s.rrp?money(s.rrp):'Unverified'}</span></div><small>Model ${esc(s.model||'not supplied')} · Console: ${esc(s.console_display||s.console)} ${s.console_status==='description_only'?'(description-derived; mapping not verified)':''}</small><div class="catalogue-tiers"><span>Silver <b>${pkg(s,'Silver')}</b></span><span>Gold <b>${pkg(s,'Gold')}</b></span><span>Platinum <b>${pkg(s,'Platinum')}</b></span></div><div class="catalogue-note">${esc(s.duplicate_sku?'Conflicting source SKU – automatic quote blocked':s.pricing_warning)}${s.pricing_rule?' · '+esc(s.rate_group)+' · '+esc(s.pricing_rule):''}</div></div>`).join('')||'<p>No current priced catalogue results. Check historical evidence below.</p>')+
 (d.historical?.results?.length?`<div class="history-heading"><b>Historical equipment library (${d.historical.total} matches)</b><small>Identity evidence only — a historical item is not an approved replacement or current RRP.</small></div>${d.historical.results.map(h=>`<div class="history-result"><b>${esc(h.sku)} · ${esc(h.name||'Unnamed historical item')}</b><small>Model ${esc(h.model||'unknown')} · Console ${esc(h.console||'unverified')} · Seen ${esc(h.first_seen||'?')}–${esc(h.year||'?')} · ${esc(h.source||'Original master')}</small></div>`).join('')}`:'');
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
async function importAgreement(file){if(!file)return;
 try{if(!file.name.toLowerCase().endsWith('.pdf'))throw new Error('Please select a maintenance agreement PDF.');
 if(file.size>35*1024*1024)throw new Error('Agreement must be smaller than 35 MB.');
 if(state.quote.assets.length&&!confirm('Replace the current equipment list with this agreement? Cancel to keep your existing lines.'))return;
 const bytes=new Uint8Array(await file.arrayBuffer());let content='';for(let i=0;i<bytes.length;i+=0x8000)content+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
 $('uploadedText').textContent='Reading agreement '+file.name+'…';
 const d=await api('/api/quotes/'+state.quote.id+'/agreement-import',{method:'POST',body:JSON.stringify({filename:file.name,content_base64:btoa(content),mode:'replace'})});
 apply(d);state.filter='all';render();toast(`Imported ${d.import_report.lines} lines (${d.import_report.units} units) from the previous agreement. Check unmatched legacy products and renewal terms.`);
 document.querySelector('.assets-panel').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){toast(e.message,true)}finally{$('agreementPicker').value='';render()}}
async function importOldCalcs(file){if(!file)return;
 try{
  if(!/\.xlsx?$/i.test(file.name))throw new Error('Please select a historical .xls or .xlsx calculations workbook.');
  if(file.size>30*1024*1024)throw new Error('Old calculations file must be smaller than 30 MB.');
  const bytes=new Uint8Array(await file.arrayBuffer());let content='';for(let i=0;i<bytes.length;i+=0x8000)content+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
  $('uploadedText').textContent='Reading previous calculations '+file.name+'…';
  const d=await api('/api/quotes/'+state.quote.id+'/old-calcs-import',{method:'POST',body:JSON.stringify({filename:file.name,content_base64:btoa(content)})});
  apply(d);state.filter='all';render();
  toast(`Imported ${d.import_report.source_lines} historic priced lines; matched ${d.import_report.matched}, added ${d.import_report.added}. ${d.import_report.unmatched_codes.length} need reconciliation.`);
  document.querySelector('.assets-panel').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){toast(e.message,true)}finally{$('oldCalcsPicker').value='';render()}
}
async function loadUsers(){try{
 const d=await api('/api/users');$('usersList').innerHTML=d.users.map(u=>`<div class="users-row"><div><b>${esc(u.username)}</b><span class="user-role">${esc(u.role)}</span> · ${u.active?'Active':'Inactive'}</div><div><button class="secondary-btn" data-reset="${esc(u.username)}">Reset password</button><button class="secondary-btn" data-toggle="${esc(u.username)}" data-active="${u.active}">${u.active?'Deactivate':'Activate'}</button></div></div>`).join('');
 document.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=async()=>{let active=b.dataset.active==='1';if(!confirm((active?'Deactivate ':'Activate ')+b.dataset.toggle+'?'))return;try{await api('/api/users/'+encodeURIComponent(b.dataset.toggle)+'/status',{method:'PUT',body:JSON.stringify({active:!active})});loadUsers()}catch(e){toast(e.message,true)}});
 document.querySelectorAll('[data-reset]').forEach(b=>b.onclick=async()=>{const name=b.dataset.reset,pw=prompt('New password for '+name+' (at least 12 characters):');if(pw===null)return;try{await api('/api/users/'+encodeURIComponent(name)+'/password',{method:'PUT',body:JSON.stringify({password:pw})});toast('Password changed and old sessions invalidated.')}catch(e){toast(e.message,true)}});
 }catch(e){toast(e.message,true)}}
async function addUserFromUI(){try{const data={username:$('newUsername').value,role:$('newUserRole').value,password:$('newUserPassword').value};await api('/api/users',{method:'POST',body:JSON.stringify(data)});$('newUserPassword').value='';$('newUsername').value='';toast('Staff account created.');loadUsers()}catch(e){toast(e.message,true)}}
function bind(){
 document.querySelector('.left-area').insertBefore(document.querySelector('.assets-panel'),$('quoteDetails'));
 $('newQuote').onclick=()=>newQuote();$('exportQuoteRegister').onclick=exportRegister;$('customer').addEventListener('input',()=>{clearTimeout(window.customerHintTimer);window.customerHintTimer=setTimeout(updateCustomerHints,280)});$('navBuilder').onclick=()=>showView('builder');$('navUsers').onclick=()=>showView('users');$('addStaffUser').onclick=addUserFromUI;$('refreshUsers').onclick=loadUsers;$('navRegister').onclick=()=>showView('register');$('navCatalogue').onclick=()=>showView('catalogue');$('navManager').onclick=()=>showView('manager');
 $('saveDetails').onclick=()=>saveDetails();['customer','site','contact','contact_email','prepared_by','billing_address','delivery_address','customer_ref','account_ref','contract_ref','valid_days','term','discount','visits'].forEach(k=>{const el=$(k);if(el)el.addEventListener('change',()=>saveDetails(true))});$('filePicker').onchange=e=>importFile(e.target.files[0]);$('browseAgreement').onclick=()=>$('agreementPicker').click();$('agreementPicker').onchange=e=>importAgreement(e.target.files[0]);$('browseOldCalcs').onclick=()=>$('oldCalcsPicker').click();$('oldCalcsPicker').onchange=e=>importOldCalcs(e.target.files[0]);$('browseButton').onclick=()=>$('filePicker').click();$('loadSample').onclick=()=>importFile(sampleCsv());$('downloadPdf').onclick=downloadPdf;$('quoteVersions').onclick=versions;$('savePipeline').onclick=recordPipeline;$('manualAdd').onclick=manualAdd;$('reviewAll').onclick=()=>{state.filter='all';render()};$('reviewIssues').onclick=()=>{state.filter='issues';render()};$('nextIssue').onclick=()=>reviewNext();$('closeModal').onclick=()=>$('modal').classList.add('hidden');$('modal').onclick=e=>{if(e.target===$('modal'))$('modal').classList.add('hidden')};$('catalogSearch').oninput=()=>{clearTimeout(window.searchTimer);window.searchTimer=setTimeout(searchCatalogue,270)};
 $('managerSearch').oninput=()=>{clearTimeout(window.managerTimer);window.managerTimer=setTimeout(searchManager,260)};
 $('managerNew').onclick=()=>editCatalogue(null);$('managerExport').onclick=()=>window.location.href='/api/catalog/admin/export.csv';
 $('managerPreview').onclick=previewMaster;$('managerApply').onclick=applyMaster;
 const z=$('dropzone');z.addEventListener('dragover',e=>{e.preventDefault();z.classList.add('drag')});z.addEventListener('dragleave',()=>z.classList.remove('drag'));z.addEventListener('drop',e=>{e.preventDefault();z.classList.remove('drag');importFile(e.dataTransfer.files[0])});
}

// V4 master catalogue controls: operator-entered audit trail. This does not
// implement identity/authentication or grant autonomous commercial approval.
let currentStage=null;
async function loadManager(){
 try{
  const [info,audit,readiness]=await Promise.all([api('/api/catalog/admin/info'),api('/api/catalog/admin/audit'),api('/api/catalog/admin/readiness')]);
  const archive=readiness.historical;
  $('readinessPanel').innerHTML=`<div class="readiness-heading"><div><b>V10 archive & commercial readiness</b><p>${archive.unique_skus.toLocaleString()} historical SKUs · ${archive.alias_codes.toLocaleString()} old codes · ${archive.source_years.join(', ')||'No sources loaded'}</p></div><span class="readiness-status ${readiness.automated_preflight_passes?'ready':'hold'}">${readiness.automated_preflight_passes?'Automated checks passed':'Pilot — review required'}</span></div><ul>${readiness.warnings.map(w=>`<li>${esc(w)}</li>`).join('')||'<li>Automated data checks passed. Manual quote/PDF sign-off is still required.</li>'}</ul><small>${esc(readiness.notice)}</small>`;
  $('managerStats').innerHTML=`<div><b>${info.rows.toLocaleString()}</b><small>Catalogue records</small></div><div><b>${info.unique_skus.toLocaleString()}</b><small>Unique item codes</small></div><div><b>${info.estimate_rows}</b><small>Calculated estimates</small></div><div><b>${info.duplicate_sku_count}</b><small>Conflicting item codes</small></div>`;
  $('managerHistory').innerHTML=audit.history.length?audit.history.map(x=>`<div class="audit-row"><b>${esc(x.sku)}</b> · ${esc(x.modified)} · ${esc(x.operator)}<br><small>${esc(x.reason)}</small></div>`).join(''):'<p class="editor-hint">No catalogue edits recorded yet.</p>';
  if($('managerSearch').value.trim().length>1)await searchManager();
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
