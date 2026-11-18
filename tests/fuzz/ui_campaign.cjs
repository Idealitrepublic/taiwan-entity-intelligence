/** Seeded stateful UI fuzzing. Synthetic network only; no public endpoints. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const seed=Number(process.env.TEI_FUZZ_SEED||20261118),steps=Number(process.env.TEI_FUZZ_STEPS||150);
let randomState=seed>>>0;
function random(){randomState=(Math.imul(randomState,1664525)+1013904223)>>>0;return randomState/4294967296}
const pick=items=>items[Math.floor(random()*items.length)];
const html=fs.readFileSync('web/index.html','utf8');
const types=['GovernmentAgency','Company','Politician','CivilOrganization','GovernmentOfficial','Person','Contract','PoliticalParty'];
const nodes=Array.from({length:28},(_,i)=>({id:`11111111-1111-4111-8111-${String(i).padStart(12,'0')}`,
 entity_type:types[i%types.length],display_name:`測試${i}／`+pick(['中文資料','LongEnglishName'.repeat(4),'多層關聯組織','<img src=x onerror="window.fuzzInjected=1">']),
 ...(i%8===1?{public_identifier:String(10000000+i)}:{})}));
const proof=i=>({id:`proof-${i}`,title:`來源 ${i}／<script>window.fuzzInjected=1</script>`,source_name:'隔離測試來源',source_record_id:`case-${i}`,source_url:i%5?'https://example.gov.tw/record/'+i:'javascript:alert(1)',retrieved_at:'2026-11-18T14:00:00Z'});
const links=[];
for(let i=1;i<nodes.length;i++)links.push({id:`edge-${i}`,source:nodes[Math.floor((i-1)/3)].id,target:nodes[i].id,relationship_type:i%2?'MEMBER_OF':'CONTRACT_WITH',primary_evidence:proof(i)});
for(let i=0;i<8;i++){const a=pick(nodes),b=pick(nodes);if(a.id!==b.id)links.push({id:`cross-${i}`,source:a.id,target:b.id,relationship_type:'MEMBER_OF',primary_evidence:proof(100+i)})}
const actions=[],errors=[],requests=[],blocked=[];
const output=process.env.TEI_FUZZ_OUTPUT||'/tmp/tei-ui-fuzz-'+seed+'.json';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEI_BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
 const page=await context.newPage();page.setDefaultTimeout(8000);
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url()),p=u.pathname;
  if(u.hostname!=='tei.local'){blocked.push(u.hostname);return route.abort()}
  if(p.startsWith('/graph/')||p==='/')return route.fulfill({contentType:'text/html',body:html});
  if(p==='/tei-enhancements.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync('web/tei-enhancements.js','utf8')});
  let data={};
  const index=nodes.findIndex(n=>p.endsWith(n.id)),n=nodes[index];
  if(p.startsWith('/api/'))requests.push(p);
  if(p.startsWith('/api/v1/entities/'))data={data:{...n,identity_status:'EXACT',evidence:[{evidence:proof(index)}]}};
  if(p.startsWith('/api/v1/politicians/'))data={data:{terms:[],committees:[],affiliations:[]}};
  if(p.startsWith('/api/v1/graph/')){
   const all=links.filter(e=>e.source===n.id||e.target===n.id),offset=Number(u.searchParams.get('after')||0),edges=all.slice(offset,offset+4);
   const include=new Set([n.id,...edges.flatMap(e=>[e.source,e.target])]);
   data={data:{nodes:nodes.filter(n=>include.has(n.id)),edges,has_more:all.length>offset+4,next_cursor:String(offset+4)}};
  }
  if(p==='/api/v1/search')data={data:{items:nodes.filter(n=>n.entity_type==='Company').map(n=>({entity_id:n.id,...n}))}};
  if(p.startsWith('/api/company/')){const uniform=p.split('/').at(-1),company=nodes.find(n=>n.public_identifier===uniform);data={status:'ok',uniform_number:uniform,company_name:company?.display_name||'測試公司',company:{Business_Accounting_NO:uniform,Company_Name:company?.display_name||'測試公司'},people:[],graph:{nodes:[],edges:[]},evidence:[],evidence_status:{},public_graph_scope:true}}
  if(p.startsWith('/api/procurement/'))data={status:'ok',records:[]};
  if(p.startsWith('/api/company-related/'))data={status:'ok',items:[]};
  if(p==='/api/status')data={supabase:{connected:true,canonical:{companies:472,people:152,entity_evidence:66904,evidence_records:67134},source_files:0,source_records:0}};
  const delay=(Number(p.replace(/\D/g,'').slice(-3))||0)%4*7;
  if(delay)await new Promise(r=>setTimeout(r,delay));
  await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 async function inspect(label){
  await page.waitForFunction(()=>!document.querySelector('#graphLoading')||document.querySelector('#graphLoading').hidden,{timeout:8000});
  assert.deepEqual(errors,[],label+': page error');
  const state=await page.locator('#svg').evaluate(svg=>{
   const ns=[...svg.querySelectorAll('.node')],ids=ns.map(n=>n.dataset.nodeId);
   const invalid=[...svg.querySelectorAll('path,circle,text,g')].filter(e=>['d','transform','cx','cy','x','y'].some(k=>/NaN|Infinity/.test(e.getAttribute(k)||'')));
   return {ids,invalid:invalid.length,bounds:svg.getBoundingClientRect().toJSON(),injected:document.querySelectorAll('#overviewPane script,#overviewPane img,#nodeInfo script,#nodeInfo img').length};
  });
  assert(state.ids.includes(nodes[0].id),label+': root was lost');
  assert.equal(new Set(state.ids).size,state.ids.length,label+': duplicate node IDs');
  assert.equal(state.invalid,0,label+': non-finite geometry');assert.equal(state.injected,0,label+': HTML injection');
  assert(state.bounds.height>=200&&state.bounds.width>150,label+': graph disappeared');
 }
 try{
  await page.goto('https://tei.local/graph/'+nodes[0].id);
  await page.locator('#svg .node').nth(1).waitFor();
  for(let i=0;i<steps;i++){
   const action=pick(['expand','expand','resize','zoom','fit','collapse','range','select','switch-fast','focus','drag','evidence']);
   const record={step:i,action,executed:true};actions.push(record);
   if(action==='expand'){
    const choices=await page.locator('#svg .node[data-node-id]').all();const node=pick(choices);record.id=await node.getAttribute('data-node-id');
    await node.press('Enter');
   }else if(action==='resize'){
    record.width=pick([390,768,1024,1280,1440]);await page.setViewportSize({width:record.width,height:900});
   }else if(action==='zoom')await page.locator(pick(['#plus','#minus'])).click();
   else if(action==='fit')await page.locator('#fit').click();
   else if(action==='collapse')await page.locator('#collapse').click();
   else if(action==='range')await page.locator('#hopLimit').selectOption(pick(['','1','2','3']));
   else if(action==='select'||action==='switch-fast'){
    const select=page.locator('#pathEntitySelect');
    if(!await select.isVisible()&&await page.locator('#graphFocus').isVisible())await page.locator('#graphFocus').click();
    const options=await select.locator('option').evaluateAll(xs=>xs.map(x=>x.value).filter(Boolean));
    if(options.length){record.id=pick(options);await select.selectOption(record.id);if(action==='switch-fast'){record.id=pick(options);await select.selectOption(record.id)}
     await page.waitForFunction(()=>!document.querySelector('#pathEntityStatus').textContent.includes('Loading'));
     assert.equal(await select.inputValue(),record.id);
    }
   }else if(action==='focus'){
    if(await page.locator('#graphFocus').isVisible())await page.locator('#graphFocus').click();else record.executed=false;
   }else if(action==='drag'){
    const svg=await page.locator('#svg').boundingBox();const circle=page.locator('#svg .node circle:not(.hit)').first();const box=await circle.boundingBox();
    if(box&&box.x>=svg.x&&box.y>=svg.y&&box.x+box.width<svg.x+svg.width&&box.y+box.height<svg.y+svg.height){await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+pick([-18,18]),box.y+box.height/2+pick([-12,12]),{steps:3});await page.mouse.up()}else record.executed=false;
   }else if(action==='evidence'){
    if(await page.locator('#mobileGraphList').isVisible()){
     const choices=page.locator('#mobileGraphList button');if(await choices.count())await choices.first().click();else record.executed=false;
    }else{const edge=page.locator('#svg .edge-group[role=button]').first();if(await edge.count())await edge.press('Enter');else record.executed=false;}
   }
   if(await page.locator('#nodeInfo').isVisible())await page.locator('#closeNode').click();
   await inspect('step '+i+' '+action);
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(output,JSON.stringify({result:'PASS',seed,steps,executed_steps:actions.filter(a=>a.executed).length,actions,requests:requests.length,blocked_outbound:blocked,errors},null,2));
  console.log(JSON.stringify({result:'PASS',seed,steps,executed_steps:actions.filter(a=>a.executed).length,requests:requests.length,errors}));
 }catch(e){
  await page.screenshot({path:output.replace('.json','.png'),fullPage:true}).catch(()=>{});
  fs.writeFileSync(output,JSON.stringify({result:'FAIL',seed,steps,actions,error:e.message,errors,blocked_outbound:blocked},null,2));
  throw e;
 }finally{await context.close();await browser.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
