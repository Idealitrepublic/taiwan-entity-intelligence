/** Browser regression for the company graph shape shown by Chunghwa Telecom. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const companyId = 'company:96979933';
const graphNodes = [
  {id:companyId,type:'company',label:'中華電信股份有限公司'},
  ...Array.from({length:13},(_,index)=>({id:`person:${index}`,type:'person',label:`關係人 ${index+1}`,properties:{position:'董事'}})),
  ...Array.from({length:50},(_,index)=>({id:`penalty:${index}`,type:'penalty',label:'勞動基準法第24條',properties:{date:'2025-01-01'}})),
  ...Array.from({length:50},(_,index)=>({id:`judicial:${index}`,type:'judicial',label:`司法院判決 ${index+1}`,properties:{date:'2026-01-01'}})),
  {id:'website:cht',type:'website',label:'cht.com.tw'}
];
const companyResponse = {status:'ok',uniform_number:'96979933',company_name:'中華電信股份有限公司',company:{},people:[],
  graph:{nodes:graphNodes,edges:[{source:companyId,target:'website:cht',relationship:'website'}]},
  evidence:[],labor_penalties:[],judicial_result:{records:[],matched:0},evidence_status:{}};
const procurementResponse = {status:'ok',matched:74,records:Array.from({length:74},(_,index)=>({
  id:`award:${index}`,title:`公開標案 ${index+1}`,agency:'臺北市政府',date:'2025-01-01'
}))};

function inspectGraph() {
  const svg=document.querySelector('#svg'),viewport=svg.getBoundingClientRect();
  const nodes=[...svg.querySelectorAll('.node')],hubNodes=nodes.filter(node=>node.classList.contains('hub'));
  const point=node=>{const circle=node.querySelector('circle:not(.hit)');return{x:Number(circle.getAttribute('cx')),y:Number(circle.getAttribute('cy'))}};
  const root=point(svg.querySelector('.node[data-type="company"]'));
  const hubs=Object.fromEntries(hubNodes.map(node=>[node.dataset.hub,point(node)]));
  const website=point(svg.querySelector('.node[data-type="website"]'));
  const branches=[...svg.querySelectorAll('.root-branch')].map(line=>({
    x1:Number(line.getAttribute('x1')),y1:Number(line.getAttribute('y1')),
    x2:Number(line.getAttribute('x2')),y2:Number(line.getAttribute('y2'))
  }));
  const boxes=nodes.map(node=>({id:node.dataset.nodeId,box:node.getBoundingClientRect()}));
  const overlap=[];
  for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){
    const a=boxes[i].box,b=boxes[j].box;
    if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)
      overlap.push([boxes[i].id,boxes[j].id]);
  }
  return{root,hubs,website,branches,spine:svg.querySelector('.root-spine')?.getAttribute('d'),
    clipped:boxes.filter(({box})=>box.left<viewport.left-2||box.right>viewport.right+2||box.top<viewport.top-2||box.bottom>viewport.bottom+2).map(({id})=>id),
    overlap,judicialChildren:svg.querySelectorAll('.node[data-type="judicial_year"]').length};
}

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.TEI_BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('https://tei.local/**',route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/')return route.fulfill({status:200,contentType:'text/html',body:html});
      const response=path==='/api/company/96979933'?companyResponse:path==='/api/procurement/96979933'?procurementResponse:path==='/api/company-related/96979933'?{status:'ok',items:[]}:{status:'ok'};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(response)});
    });
    await page.goto('https://tei.local/');
    await page.locator('#q').fill('96979933');
    await page.locator('#search').click();
    await page.locator('#svg .node[data-hub="judicial"]').waitFor();
    const baseline=await page.evaluate(inspectGraph);
    assert.deepEqual(Object.keys(baseline.hubs),['person','penalty','judicial','procurement']);
    assert.equal(baseline.root.y,baseline.hubs.judicial.y,'Company root aligns with the judicial reference row');
    const step=baseline.hubs.judicial.y-baseline.hubs.penalty.y;
    assert(step>0);
    assert.equal(baseline.hubs.penalty.y-baseline.hubs.person.y,step,'People use the judicial spacing');
    assert.equal(baseline.hubs.procurement.y-baseline.hubs.judicial.y,step,'Awards use the judicial spacing');
    assert.equal(baseline.website.y-baseline.hubs.procurement.y,step,'Company website uses the same spacing');
    assert.equal(baseline.branches.length,5,'Every direct company connection uses the shared rail');
    assert(baseline.branches.every(branch=>branch.x1===baseline.branches[0].x1&&branch.y1===branch.y2&&branch.x2>branch.x1));
    assert(baseline.spine?.includes(`V ${baseline.website.y}`),'The root rail reaches the last direct node');
    assert.deepEqual(baseline.overlap,[]);
    assert.deepEqual(baseline.clipped,[]);
    await page.locator('#svg .node[data-hub="judicial"]').click();
    for(const width of [1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      const layout=await page.evaluate(inspectGraph);
      assert.equal(layout.root.y,layout.hubs.judicial.y,`${width}px: judicial anchor remains aligned`);
      assert.equal(layout.judicialChildren,1,`${width}px: judgment year stays expandable`);
      assert.deepEqual(layout.overlap,[],`${width}px: no node or label overlap`);
      assert.deepEqual(layout.clipped,[],`${width}px: all nodes remain visible`);
      if(width===1440&&process.env.TEI_CHUNGHWA_GRAPH_SCREENSHOT)
        await page.locator('.graph').screenshot({path:process.env.TEI_CHUNGHWA_GRAPH_SCREENSHOT});
    }
    assert.deepEqual(errors,[]);
    console.log('Chunghwa-shaped graph: judicial spacing, shared company rail, expansion and 1440/1280/1024/768px passed.');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
