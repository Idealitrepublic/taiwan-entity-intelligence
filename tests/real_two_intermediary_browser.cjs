/** Replay a verified local PostgreSQL/RLS response; never invent path records. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const value=JSON.parse(fs.readFileSync(process.env.TEI_REAL_PATH_FIXTURE,'utf8')).local_exercise;
assert.equal(value.result,'PASS');
const path=value.path,html=fs.readFileSync('web/index.html','utf8');
assert.equal(path.depth,3);assert.equal(path.segments.length,3);
const a=path.source_entity,b=path.target_entity;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://tei.local/**',route=>{
   const u=new URL(route.request().url()),p=u.pathname;
   if(p==='/')return route.fulfill({contentType:'text/html',body:html});
   let data={};
   if(p==='/api/v1/search')data={data:{items:[a,b].filter(x=>x.display_name.includes(u.searchParams.get('q'))).map(x=>({...x,entity_id:x.id,public_identifier:x.id===a.id?'22659295':'23060248'}))}};
   if(p==='/api/v1/paths'){
    assert.equal(u.searchParams.get('exact_depth'),'3');
    assert.equal(u.searchParams.get('source'),a.id);assert.equal(u.searchParams.get('target'),b.id);
    data={data:path};
   }
   if(p.startsWith('/api/v1/graph/'))data={data:value.neighborhoods[p.split('/').at(-1)]||{nodes:[],edges:[],has_more:false}};
   if(p.startsWith('/api/v1/entities/'))data={data:Object.values(value.neighborhoods).flatMap(x=>x.nodes).find(n=>n.id===p.split('/').at(-1))||{}};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto('https://tei.local/');
  await page.locator('#pathSourceQuery').fill(a.display_name);await page.locator('#pathSourceMatches .path-match').first().click();
  await page.locator('#pathTargetQuery').fill(b.display_name);await page.locator('#pathTargetMatches .path-match').first().click();
  await page.locator('#pathDepth').selectOption('3');await page.locator('#pathFind').click();
  await page.locator('#svg .edge-group').nth(2).waitFor();
  assert.equal(await page.locator('#svg .node').count(),4);assert.equal(await page.locator('#svg .edge-group').count(),3);
  assert.match(await page.locator('#pathResult').innerText(),/2 個中介/);
  for(const segment of path.segments){
   await page.locator(`#svg .edge-group[data-edge-id="${segment.relationship.id}"]`).press('Enter');
   assert((await page.locator('#nodeInfoBody').innerText()).includes(segment.evidence.source_name));
   await page.locator('#closeNode').click();
  }
  await page.locator(`#svg .node[data-node-id="${b.id}"]`).press('Enter');
  await page.waitForFunction(()=>document.querySelector('#svg').getAttribute('aria-busy')==='false');
  assert(await page.locator('#svg .node').count()>4,'Verified company can expand beyond the two-intermediary path');
  assert.deepEqual(errors,[]);
  console.log('PASS real-data replay: 4 distinct nodes, 3 evidenced links, selected 2 intermediaries, all Evidence, company expansion; no shared DB writes.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
