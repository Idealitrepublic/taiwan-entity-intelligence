/** Browser regression for the company graph shape shown by Chunghwa Telecom. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const companyId = 'company:96979933';
const laborArticles = ['第13條第2項','第24條','第24條第1項','第32條第1項','第32條第2項','第36條第1項','第36條第2項','第38條第4項','第39條','第49條第1項'];
const graphNodes = [
  {id:companyId,type:'company',label:'中華電信股份有限公司'},
  ...Array.from({length:13},(_,index)=>({id:`person:${index}`,type:'person',label:`關係人 ${index+1}`,properties:{position:index===0?'董事長':index===1?'監察人':'董事'}})),
  ...Array.from({length:50},(_,index)=>({id:`penalty:${index}`,type:'penalty',label:`勞動基準法${laborArticles[index%laborArticles.length]}`,properties:{date:'2025-01-01'}})),
  ...Array.from({length:50},(_,index)=>({id:`judicial:${index}`,type:'judicial',label:`司法院判決 ${index+1}`,properties:{date:'2026-01-01'}})),
  {id:'website:cht',type:'website',label:'cht.com.tw'}
];
const companyResponse = {status:'ok',uniform_number:'96979933',company_name:'中華電信股份有限公司',company:{},people:[],
  graph:{nodes:graphNodes,edges:[{source:companyId,target:'website:cht',relationship:'website'}]},
  evidence:[],labor_penalties:[],judicial_result:{records:[],matched:0},evidence_status:{}};
const procurementResponse = {status:'ok',matched:74,records:Array.from({length:74},(_,index)=>({
  id:`award:${index}`,title:`公開標案 ${index+1}`,
  agency:['臺北市政府','新北市政府','臺中市政府','高雄市政府'][index%4],
  date:`${2026-index%4}-01-01`
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
    await page.locator('#svg .node[data-hub="penalty"]').click();
    assert.equal(await page.locator('#svg .node[data-type="penalty_law"]').count(),1);
    await page.locator('#svg .node[data-type="penalty_law"]').click();
    assert.equal(await page.locator('#svg .node[data-type="penalty_article"]').count(),10);
    for(const width of [1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      const layout=await page.evaluate(inspectGraph);
      assert.equal(layout.hubs.penalty.y-layout.hubs.person.y,layout.hubs.judicial.y-layout.hubs.penalty.y,
        `${width}px: ten expanded labor groups do not add empty space between category hubs`);
      const visible=await page.evaluate(()=>{
        const viewport=document.querySelector('#svg').getBoundingClientRect();
        return [...document.querySelectorAll('#svg .node[data-type="penalty_article"]')].map(node=>({
          text:node.querySelector('text.child-label').getBoundingClientRect(),
          circle:node.querySelector('circle:not(.hit)').getBoundingClientRect()
        })).filter(node=>node.text.left>=viewport.left&&node.text.right<=viewport.right&&
          node.text.top>=viewport.top&&node.text.bottom<=viewport.bottom);
      });
      assert.deepEqual(layout.overlap,[],`${width}px: no overlap with ten expanded labor articles`);
      assert(visible.length>=2,`${width}px: readable labor articles remain visible without fitting all ten`);
      assert(visible.every(node=>node.text.height>=12&&node.circle.width>=24),
        `${width}px: visible labor text and circles meet readable on-screen size`);
      assert(Number((await page.locator('#zoomValue').textContent()).replace('%',''))>=115,
        `${width}px: expansion does not auto-shrink the graph`);
      if(width===1440&&process.env.TEI_CHUNGHWA_LABOR_SCREENSHOT)
        await page.locator('.graph').screenshot({path:process.env.TEI_CHUNGHWA_LABOR_SCREENSHOT});
    }
    await page.setViewportSize({width:1440,height:900});
    await page.locator('#svg .node[data-type="penalty_article"]').nth(4).click();
    assert.equal(await page.locator('#svg .node[data-type="penalty_year"]').count(),1);
    await page.locator('#svg .node[data-type="penalty_year"]').click();
    assert.equal(await page.locator('#svg .node[data-type="penalty_county"]').count(),1);
    await page.locator('#svg .node[data-type="penalty_county"]').click();
    assert.equal(await page.locator('#svg .node[data-type="penalty"]').count(),5);
    await page.locator('#fit').click();
    assert(Number((await page.locator('#zoomValue').textContent()).replace('%',''))>=115,
      'Fit keeps the expanded branch readable instead of shrinking all labels');
    await page.locator('#collapse').click();
    assert.deepEqual((await page.evaluate(inspectGraph)).clipped,[], 'Collapse restores the full graph overview');
    await page.setViewportSize({width:1440,height:900});
    await page.locator('#svg .node[data-hub="person"]').click();
    assert.equal(await page.locator('#svg .node[data-type="person"]').count(),13);
    assert.match(await page.locator('#svg .node[data-type="person"]').first().getAttribute('aria-label'),/關係人 1 · 董事長/);
    for(const width of [1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      await page.locator('#fit').click();
      await page.locator('#minus').click();
      const layout=await page.evaluate(inspectGraph);
      assert.equal(layout.hubs.penalty.y-layout.hubs.person.y,layout.hubs.judicial.y-layout.hubs.penalty.y,
        `${width}px: thirteen people do not create a tall empty gap before labor violations`);
      assert(layout.hubs.judicial.y-layout.hubs.penalty.y<=step,
        `${width}px: expanded hubs do not exceed the judicial reference spacing`);
      assert.deepEqual(layout.overlap,[],`${width}px: compact categories do not overlap expanded people`);
      const visible=await page.evaluate(()=>{
        const viewport=document.querySelector('#svg').getBoundingClientRect();
        return [...document.querySelectorAll('#svg .node[data-type="person"]')].map(node=>({
          text:node.querySelector('text.child-label').getBoundingClientRect(),
          circle:node.querySelector('circle:not(.hit)').getBoundingClientRect()
        })).filter(node=>node.text.left>=viewport.left&&node.text.right<=viewport.right&&
          node.text.top>=viewport.top&&node.text.bottom<=viewport.bottom);
      });
      assert(visible.length>=2,`${width}px: refocused people remain visible`);
      assert(visible.every(node=>node.text.height>=12&&node.circle.width>=24),
        `${width}px: refocused people text and circles remain readable`);
      assert(Number((await page.locator('#zoomValue').textContent()).replace('%',''))>=115,
        `${width}px: Fit and zoom-out cannot shrink expanded people into a tiny overview`);
      if(width===1440&&process.env.TEI_CHUNGHWA_PEOPLE_SCREENSHOT)
        await page.locator('.graph').screenshot({path:process.env.TEI_CHUNGHWA_PEOPLE_SCREENSHOT});
    }
    await page.locator('#collapse').click();
    await page.setViewportSize({width:1440,height:900});
    await page.locator('#svg .node[data-hub="judicial"]').click();
    for(const width of [1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      const layout=await page.evaluate(inspectGraph);
      assert.equal(layout.root.y,layout.hubs.judicial.y,`${width}px: judicial anchor remains aligned`);
      assert.equal(layout.hubs.judicial.y-layout.hubs.penalty.y,layout.hubs.penalty.y-layout.hubs.person.y,
        `${width}px: judicial expansion keeps uniform category spacing`);
      assert.equal(layout.judicialChildren,1,`${width}px: judgment year stays expandable`);
      assert.deepEqual(layout.overlap,[],`${width}px: no node or label overlap`);
      assert(await page.locator('#svg .node[data-type="judicial_year"]').count()>0,
        `${width}px: judgment year remains available after refocusing`);
      if(width===1440&&process.env.TEI_CHUNGHWA_GRAPH_SCREENSHOT)
        await page.locator('.graph').screenshot({path:process.env.TEI_CHUNGHWA_GRAPH_SCREENSHOT});
    }
    await page.setViewportSize({width:1440,height:900});
    await page.locator('#svg .node[data-type="judicial_year"]').click();
    assert.equal(await page.locator('#svg .node[data-type="judicial_month"]').count(),1);
    assert.match(await page.locator('#svg .node[data-type="judicial_month"]').getAttribute('aria-label'),/01 月/);
    await page.locator('#svg .node[data-type="judicial_month"]').click();
    assert.equal(await page.locator('#svg .node[data-type="judicial"]').count(),8);
    await page.locator('#collapse').click();
    await page.setViewportSize({width:1440,height:900});
    await page.locator('#svg .node[data-hub="procurement"]').click();
    assert.equal(await page.locator('#svg .node[data-type="procurement_city"]').count(),4);
    await page.locator('#svg .node[data-type="procurement_city"]').first().click();
    assert(await page.locator('#svg .node[data-type="procurement_year"]').count()>0);
    for(const width of [1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      await page.locator('#fit').click();
      const layout=await page.evaluate(inspectGraph);
      assert.equal(layout.hubs.procurement.y-layout.hubs.judicial.y,
        layout.hubs.judicial.y-layout.hubs.penalty.y,
        `${width}px: awards and their year branch do not create extra hub-lane whitespace`);
      assert.deepEqual(layout.overlap,[],`${width}px: award county/year labels do not overlap other nodes`);
      assert(Number((await page.locator('#zoomValue').textContent()).replace('%',''))>=115,
        `${width}px: expanded award records remain readable`);
      if(width===1440&&process.env.TEI_CHUNGHWA_AWARDS_SCREENSHOT)
        await page.locator('.graph').screenshot({path:process.env.TEI_CHUNGHWA_AWARDS_SCREENSHOT});
    }
    assert.deepEqual(errors,[]);
    console.log('Chunghwa-shaped graph: judicial spacing, shared company rail, expansion and 1440/1280/1024/768px passed.');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
