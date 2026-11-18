/** Isolated browser regression: every public entity shares graph/panel controls. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require('playwright');
const html=fs.readFileSync('web/index.html','utf8');
const types=['Company','Person','Politician','GovernmentOfficial','GovernmentAgency','CivilOrganization','PoliticalParty','Contract'];
const nodes=types.map((entity_type,i)=>({id:`11111111-1111-4111-8111-${String(i).padStart(12,'0')}`,entity_type,display_name:`測試${entity_type}／Long bilingual public entity`,...(i===0?{public_identifier:'22659295'}:{})}));
const evidence={id:'proof',title:'公開來源身分依據',source_name:'官方來源',source_url:'https://example.gov.tw/evidence',retrieved_at:'2026-11-18T14:00:00Z'};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.TEI_BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://tei.local/**',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/'||path.startsWith('/graph/')||path.startsWith('/politician/'))return route.fulfill({contentType:'text/html',body:html});
   let body={};
   if(path==='/api/status')body={supabase:{connected:false,snapshot_available:true,counts_state:'cached',counts_checked_at:'2026-11-18T14:00:00Z',canonical:{companies:472,people:152,entity_evidence:66904,evidence_records:67134},source_files:0,source_records:0}};
   if(path.startsWith('/api/v1/entities/')){const node=nodes.find(n=>path.endsWith(n.id));body={data:{...node,identity_status:'EXACT',evidence:[{evidence}]}}}
   if(path.startsWith('/api/v1/graph/')){const node=nodes.find(n=>path.endsWith(n.id)),child=nodes.find(n=>n.id!==node.id);body={data:{nodes:[node,child],edges:[{id:`edge-${node.id}`,source:node.id,target:child.id,relationship_type:'MEMBER_OF',primary_evidence:evidence}],has_more:false}}}
   if(path.startsWith('/api/v1/politicians/'))body={data:{}};
   if(path.startsWith('/api/company/'))body={status:'ok',public_graph_scope:true,uniform_number:'22659295',company_name:nodes[0].display_name,company:{Business_Accounting_NO:'22659295'},people:[],graph:{nodes:[],edges:[]},evidence:[],evidence_status:{}};
   if(path.startsWith('/api/procurement/'))body={status:'ok',records:[]};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  for(const node of nodes){
   await page.goto(`https://tei.local/graph/${node.id}`);
   await page.locator('#svg .node').nth(1).waitFor();
   assert.equal(await page.locator('#pathEntityPicker').isVisible(),true,`${node.entity_type} has shared entity picker`);
   assert.equal(await page.locator('#fit').isVisible(),true);
   assert.equal(await page.locator('#collapse').isVisible(),true);
   assert.match(await page.locator('#dbStatus').textContent(),/67,134/);
   assert.match(await page.locator('#dbStatus').textContent(),/not live/);
   assert.equal(await page.locator('#domain').isVisible(),false);
   await page.locator('#pathEntitySelect').selectOption(node.id);
   await page.waitForFunction(()=>!document.querySelector('#overviewPane').textContent.includes('Loading company data'));
   assert.match(await page.locator('#overviewPane').textContent(),/測試/);
   await page.locator(`#svg .node[data-node-id="${node.id}"]`).press('Enter');
   assert.equal(await page.locator('#svg .node').count()>=2,true);
   if(await page.locator('#nodeInfo').isVisible())await page.locator('#closeNode').click();
   await page.locator('#fit').click();
  }
  assert.deepEqual(errors,[]);
  console.log('Public remediation: eight entity types, expansion, shared picker, source panels, exact cached counts, no 165 input PASS.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
