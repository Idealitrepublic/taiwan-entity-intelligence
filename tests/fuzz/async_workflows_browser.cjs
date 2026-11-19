/** Round two: controlled response reordering, cross-view cancellation, retry and real downloads. */
const fs=require('node:fs'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
const seed=Number(process.env.TEI_FUZZ_SEED||91021);let state=seed>>>0;
const rnd=()=>((state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296);
const pick=xs=>xs[Math.floor(rnd()*xs.length)];
const html=fs.readFileSync('web/index.html','utf8');
const A={id:'003e0ccc-1f16-55cc-89d3-570d74a48ea8',entity_type:'Company',display_name:'隔離公司甲',public_identifier:'22659295'};
const B={id:'446eca14-e58c-5984-b308-d7e9057523b2',entity_type:'Company',display_name:'隔離公司乙',public_identifier:'54690903'};
const C={id:'11111111-1111-4111-8111-000000000003',entity_type:'GovernmentAgency',display_name:'隔離機關丙'};
const D={id:'11111111-1111-4111-8111-000000000004',entity_type:'Person',display_name:'隔離人物丁'};
const nodes=[A,B,C,D];
const proof=i=>({id:'proof-'+i,title:'隔離測試來源 '+i,source_name:'測試來源',source_url:'https://example.gov.tw/source/'+i,retrieved_at:'2026-11-19T00:00:00Z'});
const edge=(a,b,i)=>({id:'edge-'+i,source:a.id,target:b.id,source_entity_id:a.id,target_entity_id:b.id,relationship_type:'CONTRACT_WITH',primary_evidence_id:'proof-'+i,primary_evidence:proof(i)});
const routePath=depth=>{const route=depth===1?[A,B]:depth===2?[A,C,B]:[A,C,D,B];return{found:true,depth,source_entity:A,target_entity:B,max_depth:depth,segments:route.slice(1).map((n,i)=>({from_entity:route[i],to_entity:n,relationship:edge(route[i],n,i),evidence:proof(i),traversal_direction:'forward'}))}};
const company=n=>({status:'ok',public_graph_scope:true,uniform_number:n.public_identifier,company_name:n.display_name,company:{Business_Accounting_NO:n.public_identifier,Company_Name:n.display_name},people:[],graph:{nodes:[{id:'company:'+n.public_identifier,type:'company',label:n.display_name}],edges:[]},evidence:[],evidence_status:{}});
const awards=n=>({status:'ok',source:'隔離決標來源',matched:3,records:[0,1,2].map(i=>({id:n.public_identifier+'-'+i,title:n.display_name+'標案'+i,job_number:'000'+i,unit_id:'3.1',notice_filename:'BDM-'+n.public_identifier+'-'+i,date:'202'+(5-i)+'-01-01',agency:'測試機關',source_url:'https://example.gov.tw/award/'+i}))});
const pdfs=Object.fromEntries([A,B].map(n=>[n.public_identifier,execFileSync(process.env.TEI_PYTHON||'python3',['-c',"from src.report_pdf import render_report_pdf;import sys;sys.stdout.buffer.write(render_report_pdf({'title':'隔離報告 '+sys.argv[1],'methodology':'合成測試資料','report_type':'ENTITY','generated_at':'2026-11-19','sources':[],'relationship_graph':{'nodes':[],'edges':[]}}))",n.public_identifier])]));
const pdf=pdfs[A.public_identifier];
const defer=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve}};
const results=[];const output=process.env.TEI_FUZZ_OUTPUT||'/tmp/tei-async-fuzz-'+seed+'.json';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEI_BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 async function run(name,body){
  if(process.env.TEI_FUZZ_CASE&&process.env.TEI_FUZZ_CASE!==name)return;
  const context=await browser.newContext({viewport:{width:pick([1280,1440]),height:900},acceptDownloads:true});
  const page=await context.newPage(),gates=[],requests=[],errors=[],downloads=[],blocked=[];page.setDefaultTimeout(6000);
  page.on('pageerror',e=>errors.push(e.message));page.on('download',d=>downloads.push(d));
  const gate=(matches,override)=>{const hit=defer(),release=defer(),done=defer();const g={matches,override,hit:hit.promise,used:false,open:()=>release.resolve(),done:done.promise};gates.push({g,hit,release,done});return g};
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url()),p=u.pathname;
   if(u.hostname!=='tei.local'){blocked.push(u.hostname);return route.abort()}
   if(p==='/'||/^\/(graph|entity|politician)\//.test(p))return route.fulfill({contentType:'text/html',body:html});
   if(p==='/tei-enhancements.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync('web/tei-enhancements.js','utf8')});
   requests.push({path:p,query:u.search});
   const holder=gates.find(x=>!x.g.used&&x.g.matches(u));
   if(holder){holder.g.used=true;holder.hit.resolve();await holder.release.promise}
   let data={};const n=nodes.find(n=>p.endsWith(n.id));
   if(p==='/api/v1/search'){
    const q=u.searchParams.get('q'),found=q===A.public_identifier||q===B.public_identifier?[]:q?.includes('機關')?[C]:q?.includes('乙')?[B]:[A];
    data={data:{items:found.map(n=>({entity_id:n.id,...n,match_type:'name_exact'}))}};
   }else if(p.startsWith('/api/company/'))data=company(p.endsWith(A.public_identifier)?A:B);
   else if(p.startsWith('/api/procurement/'))data=awards(p.endsWith(A.public_identifier)?A:B);
   else if(p.startsWith('/api/company-related/'))data={status:'ok',items:[]};
   else if(p.startsWith('/api/v1/entities/'))data={data:{...n,identity_status:'EXACT',evidence:[{evidence:proof(n?.id)}]}};
   else if(p.startsWith('/api/v1/graph/')){const other=n?.id===C.id?D:C;data={data:{nodes:[n,other],edges:[edge(n,other,9)],has_more:false}}}
   else if(p==='/api/v1/paths')data={data:routePath(Number(u.searchParams.get('max_depth')))};
   else if(p==='/api/procurement-detail')data={status:'ok',summary:[{label:'預算金額 / Budget',value:'零金額原因保留',source_field:'已公告資料:預算金額'}],bidders:[],items:[],source_url:'https://example.gov.tw/detail',retrieved_at:'2026-11-19T00:00:00Z'};
   else if(p==='/api/status')data={supabase:{connected:true,canonical:{companies:472},source_files:0,source_records:0}};
   let reply={status:200,contentType:'application/json',body:JSON.stringify(data)};
   if(p.startsWith('/api/v1/reports/'))reply={status:200,contentType:'application/pdf',body:pdfs[p.split('/').at(-1)]||pdf};
   if(holder?.g.override)reply={...reply,...holder.g.override};
   try{if(reply.abort)await route.abort('failed');else await route.fulfill(reply)}catch(e){if(!page.isClosed()&&!/closed|handled|cancel|intercept/i.test(e.message))throw e}finally{holder?.done.resolve()}
  });
  const settle=async()=>{await page.waitForTimeout(70+Math.floor(rnd()*40));await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))};
  const enter=async term=>{await page.locator('#q').fill(term);await page.locator('#q').press('Enter')};
  const text=async(selector,value)=>page.waitForFunction(({selector,value})=>document.querySelector(selector)?.textContent.includes(value),{selector,value});
  let budget;
  try{
   await Promise.race([body({page,gate,requests,downloads,enter,text,settle}),new Promise((_,reject)=>{budget=setTimeout(()=>reject(Error('Workflow exceeded 18 second isolation budget')),18000)})]);
   assert.deepEqual(errors,[],'No uncaught page errors');assert.deepEqual(blocked,[],'No application outbound requests');
   results.push({name,result:'PASS',requests:requests.length,downloads:downloads.length});
  }catch(e){
   const screenshot=output.replace('.json','-'+name+'.png');await page.screenshot({path:screenshot,fullPage:true}).catch(()=>{});
   results.push({name,result:'FAIL',error:e.message,requests,errors,screenshot});
  }finally{clearTimeout(budget);gates.forEach(x=>x.release.resolve());await context.close()}
 }
 try{
 await run('reversed-name-search',async({page,gate,enter,text,settle})=>{
  const old=gate(u=>u.pathname==='/api/v1/search'&&u.searchParams.get('q').includes('甲'));
  await page.goto('https://tei.local/');await enter('隔離甲');await old.hit;await enter('隔離乙');await text('#searchResults','隔離公司乙');old.open();await old.done;await settle();
  assert.match(await page.locator('#searchResults').textContent(),/隔離公司乙/,'Older name response replaced the latest search');
 });
 await run('escape-pending-search',async({page,gate,enter,settle})=>{
  const old=gate(u=>u.pathname==='/api/v1/search'&&u.searchParams.get('q').includes('甲'));
  await page.goto('https://tei.local/');await enter('隔離甲');await old.hit;await page.locator('#q').press('Escape');old.open();await old.done;await settle();
  assert.equal(await page.locator('#searchResults').isVisible(),false,'Dismissed search results reopened after a late reply');
 });
 await run('invalid-input-after-pending-search',async({page,gate,enter,settle})=>{
  const old=gate(u=>u.pathname==='/api/v1/search'&&u.searchParams.get('q').includes('甲'));
  await page.goto('https://tei.local/');await enter('隔離甲');await old.hit;await enter('字');old.open();await old.done;await settle();
  assert.equal(await page.locator('#searchResults').isVisible(),false);assert.match(await page.locator('#uniform').textContent(),/at least 2/);assert.equal(await page.locator('#search').isEnabled(),true);
 });
 await run('outside-click-after-pending-search',async({page,gate,enter,settle})=>{
  const old=gate(u=>u.pathname==='/api/v1/search'&&u.searchParams.get('q').includes('甲'));
  await page.goto('https://tei.local/');await enter('隔離甲');await old.hit;await page.locator('#graphTitle').click();old.open();await old.done;await settle();
  assert.equal(await page.locator('#searchResults').isVisible(),false);
 });
 await run('company-tail-after-entity',async({page,gate,enter,text,settle})=>{
  const old=gate(u=>u.pathname==='/api/procurement/'+A.public_identifier);
  await page.goto('https://tei.local/');await enter(A.public_identifier);await old.hit;await text('#company',A.display_name);
  await enter('隔離機關');await page.locator('#searchResults .search-result').click();await text('#company',C.display_name);
  old.open();await old.done;await settle();assert.equal(await page.locator('#company').textContent(),C.display_name,'Old company awards replaced a newly selected entity');
 });
 await run('dismissed-lookup-keeps-current-company-sources',async({page,gate,enter,text,settle})=>{
  const old=gate(u=>u.pathname==='/api/procurement/'+A.public_identifier);await page.goto('https://tei.local/');await enter(A.public_identifier);await old.hit;await text('#company',A.display_name);
  await enter('隔離乙');await text('#searchResults',B.display_name);await page.locator('#q').press('Escape');old.open();await old.done;await settle();
  assert.match(await page.locator('#tabProcurementCount').textContent(),/3 筆/,'Cancelling a lookup discarded the still-selected company source updates');assert.equal(await page.locator('#company').textContent(),A.display_name);assert.equal(await page.locator('#searchResults').isVisible(),false);
 });
 await run('current-profile-does-not-close-new-search-results',async({page,gate,enter,text,settle})=>{
  const held=gate(u=>u.pathname==='/api/v1/entities/'+C.id);await page.goto('https://tei.local/graph/'+C.id);await held.hit;await enter('隔離乙');await text('#searchResults',B.display_name);
  held.open();await held.done;await settle();assert.equal(await page.locator('#company').textContent(),C.display_name);assert.equal(await page.locator('#searchResults').isVisible(),true);assert.match(await page.locator('#searchResults').textContent(),/隔離公司乙/);
 });
 await run('profile-after-company',async({page,gate,enter,text,settle})=>{
  const old=gate(u=>u.pathname==='/api/v1/entities/'+C.id);
  await page.goto('https://tei.local/graph/'+C.id);await old.hit;await enter(B.public_identifier);await text('#company',B.display_name);
  old.open();await old.done;await settle();assert.equal(await page.locator('#company').textContent(),B.display_name,'Old entity profile replaced a newer company investigation');
 });
 await run('company-tail-after-example',async({page,gate,enter,text,settle})=>{
  const old=gate(u=>u.pathname==='/api/procurement/'+A.public_identifier);
  await page.goto('https://tei.local/');await enter(A.public_identifier);await old.hit;await text('#company',A.display_name);await page.locator('#sample').click();
  await page.locator('#svg[data-path-graph=true]').waitFor();old.open();await old.done;await settle();
  assert.equal(await page.locator('#svg').getAttribute('data-path-graph'),'true','Old company source rerender removed the example path');
 });
 await run('path-after-new-search',async({page,gate,enter,text,settle})=>{
  const old=gate(u=>u.pathname==='/api/v1/paths');await page.goto('https://tei.local/');await page.locator('#sample').click();await old.hit;
  await enter(B.public_identifier);await text('#company',B.display_name);old.open();await old.done;await settle();
  assert.match(await page.locator('#graphTitle').textContent(),/隔離公司乙/);assert.equal(await page.locator('#svg').getAttribute('data-path-graph'),null,'Late path response replaced a newer search');
 });
 await run('path-range-then-clear',async({page,gate,settle})=>{
  const old=gate(u=>u.pathname==='/api/v1/paths'&&u.searchParams.get('max_depth')==='2');await page.goto('https://tei.local/');await page.locator('#sample').click();await old.hit;
  await page.locator('#pathDepth').selectOption('3');await page.locator('#pathFind').click();await page.locator('#svg .node').nth(3).waitFor();old.open();await old.done;await settle();
  assert.equal(await page.locator('#svg .node').count(),4,'Old range response replaced a newer two-intermediary result');
  await page.locator('#pathClear').click();assert.match(await page.locator('#pathSource').textContent(),/Not selected/);
 });
 await run('path-clear-pending',async({page,gate,settle})=>{
  const old=gate(u=>u.pathname==='/api/v1/paths');await page.goto('https://tei.local/');await page.locator('#sample').click();await old.hit;
  await page.locator('#pathClear').click();old.open();await old.done;await settle();assert.match(await page.locator('#pathSource').textContent(),/Not selected/);assert.equal(await page.locator('#svg').getAttribute('data-path-graph'),null);assert.equal(await page.locator('#pathFind').isEnabled(),false);
 });
 await run('award-filter-detach-retry',async({page,gate,enter,text,settle,requests})=>{
  await page.goto('https://tei.local/');await enter(A.public_identifier);await text('#tabProcurementCount','3 筆');await page.locator('.tab[data-tab=procurement]').click();
  const fail=gate(u=>u.pathname==='/api/procurement-detail',{status:503,contentType:'application/json',body:'{"status":"unavailable"}'});
  const pane=page.locator('#procurementPane');await pane.getByText(A.display_name+'標案0',{exact:true}).click();await fail.hit;
  await pane.getByRole('searchbox').fill('標案１');await pane.locator('.award-keyword-search button').click();fail.open();await fail.done;await settle();
  assert.equal(await pane.locator('details.record').count(),1);assert.match(await pane.textContent(),/標案1/);assert(!await pane.textContent().then(t=>t.includes('Source unavailable')),'Detached error changed the current filtered notice');
  await pane.getByRole('searchbox').fill('');await pane.locator('.award-keyword-search button').click();await pane.getByText(A.display_name+'標案0',{exact:true}).click();
  await text('#procurementPane','零金額原因保留');assert(requests.filter(r=>r.path==='/api/procurement-detail').length>=2);
 });
 for(const fault of ['http503','html200','corrupt-pdf','abort'])await run('download-retry-'+fault,async({page,gate,enter,text,settle,requests,downloads})=>{
  await page.goto('https://tei.local/');await enter(A.public_identifier);await text('#tabProcurementCount','3 筆');await page.locator('#search:enabled').waitFor();
  const override=fault==='http503'?{status:503,contentType:'application/json',body:'{"error":"測試來源失敗"}'}:fault==='html200'?{contentType:'text/html',body:'<p>upstream error</p>'}:fault==='corrupt-pdf'?{contentType:'application/pdf',body:'not a PDF'}:{abort:true};
  const fail=gate(u=>u.pathname.includes('/api/v1/reports/'),override);const button=page.getByRole('button',{name:'下載完整調查 PDF / Download PDF',exact:true});
  await button.click();await fail.hit;await button.click();assert.equal(requests.filter(r=>r.path.includes('/api/v1/reports/')).length,1,'Duplicate pending PDF request');
  fail.open();await fail.done;await text('.report-feedback',fault==='http503'?'測試來源失敗':fault==='html200'?'Expected a PDF':fault==='corrupt-pdf'?'Invalid PDF':'Failed to fetch');assert.equal(downloads.length,0,'A failed response became a downloaded file');
  const done=page.waitForEvent('download');await button.click();const file=await done;assert.equal(file.suggestedFilename(),'tei-company-'+A.public_identifier+'.pdf');const target=output.replace('.json','-'+fault+'.pdf');await file.saveAs(target);assert(fs.readFileSync(target).equals(pdf),'Downloaded PDF differs from the successful response');assert.equal(await page.locator('.report-feedback.source-warning').count(),0,'Successful retry kept the old report failure visible');
 });
 await run('download-while-switching-company',async({page,gate,enter,text,downloads})=>{
  await page.goto('https://tei.local/');await enter(A.public_identifier);await text('#tabProcurementCount','3 筆');await page.locator('#search:enabled').waitFor();
  const held=gate(u=>u.pathname.includes('/api/v1/reports/'));await page.getByRole('button',{name:'下載完整調查 PDF / Download PDF',exact:true}).click();await held.hit;
  await enter(B.public_identifier);await text('#company',B.display_name);const ready=page.waitForEvent('download');held.open();const file=await ready;
  const target=output.replace('.json','-switched-company.pdf');await file.saveAs(target);assert.equal(file.suggestedFilename(),'tei-company-'+A.public_identifier+'.pdf');assert(fs.readFileSync(target).equals(pdfs[A.public_identifier]));assert.equal(await page.locator('#company').textContent(),B.display_name);
 });
 await run('closed-report-preview',async({page,gate,enter,text,settle,downloads})=>{
  await page.goto('https://tei.local/');await enter(A.public_identifier);await text('#tabProcurementCount','3 筆');await page.locator('#search:enabled').waitFor();
  const held=gate(u=>u.pathname.includes('/api/v1/reports/'));const opened=page.waitForEvent('popup');await page.getByRole('button',{name:'預覽雙語 PDF / Preview PDF',exact:true}).click();const popup=await opened;await held.hit;await popup.close();held.open();await held.done;await text('.report-feedback','Report window was closed');assert.equal(downloads.length,0);
 });
 }finally{await browser.close()}
 const report={seed,round:'async-workflows',cases:results.length,failures:results.filter(r=>r.result==='FAIL').length,results,network:'all application external requests blocked'};
 fs.writeFileSync(output,JSON.stringify(report,null,2));console.log(JSON.stringify({seed,cases:report.cases,failures:report.failures,failed:results.filter(r=>r.result==='FAIL').map(r=>({name:r.name,error:r.error.slice(0,200)}))}));
 if(report.failures)process.exitCode=1;
})().catch(e=>{console.error(e.message);process.exitCode=1});
