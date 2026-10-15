/** Browser regression: NODE_PATH=<playwright modules> node tests/auto_related_company_browser.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const root = '11111111-1111-4111-8111-111111111111';
const bridge = '22222222-2222-4222-8222-222222222222';
const other = '33333333-3333-4333-8333-333333333333';
const evidence = {id:'44444444-4444-4444-8444-444444444444',
  source_name:'官方資料',source_url:'https://example.gov.tw/record',
  source_record_id:'official-1',retrieved_at:'2026-10-16T00:00:00Z'};
const companyResponse = {status:'ok',uniform_number:'22099131',
  company_name:'台灣積體電路製造股份有限公司',company:{},people:[],
  graph:{nodes:[{id:'company:22099131',type:'company',label:'台灣積體電路製造股份有限公司'}],edges:[]},
  evidence:[],labor_penalties:[],judicial_result:{records:[],matched:0},
  evidence_status:{},website_crosscheck:null};

(async () => {
  const browser = await chromium.launch({headless:true,
    executablePath:process.env.TEI_BROWSER_PATH ||
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:900}});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('https://tei.local/**',async route=>{
      const url=new URL(route.request().url()),path=url.pathname;
      if(path==='/' || path.startsWith('/graph/'))return route.fulfill({status:200,
        contentType:'text/html',body:html});
      let body={};
      if(path==='/api/company/22099131')body=companyResponse;
      if(path==='/api/procurement/22099131')body={status:'ok',matched:0,records:[]};
      if(path==='/api/company-related/22099131')body={status:'ok',uniform_number:'22099131',
        items:[{uniform_number:'12345678',company_name:'法人甲股份有限公司',
          connection_type:'corporate_director',connection_label:'法人董監事所代表公司',
          evidence:{source_name:'經濟部公司登記董監事資料',source_record_id:'director-1',
            source_url:'https://data.gcis.nat.gov.tw/od/data/api/example',
            retrieved_at:'2026-10-16T00:00:00Z',match_method:'exact_uniform'}},
          {uniform_number:'22345678',company_name:'法人乙股份有限公司',
           connection_type:'corporate_director',connection_label:'法人董監事所代表公司',
           evidence:{source_name:'經濟部公司登記董監事資料',source_record_id:'director-2',
             source_url:'https://data.gcis.nat.gov.tw/od/data/api/example',
             retrieved_at:'2026-10-16T00:00:00Z',match_method:'exact_uniform'}},
          {uniform_number:'32345678',company_name:'法人丙股份有限公司',
           connection_type:'corporate_director',connection_label:'法人董監事所代表公司',
           evidence:{source_name:'經濟部公司登記董監事資料',source_record_id:'director-3',
             source_url:'https://data.gcis.nat.gov.tw/od/data/api/example',
             retrieved_at:'2026-10-16T00:00:00Z',match_method:'exact_uniform'}},
          {uniform_number:'99999999',company_name:'無來源候選',
           connection_type:'corporate_director',evidence:{}}]};
      if(path===`/api/v1/entities/${root}`)body={data:{id:root,entity_type:'Company',
        display_name:'公司甲',identity_status:'EXACT',evidence:[]}};
      if(path===`/api/v1/graph/${root}`)body={data:{nodes:[
        {id:root,entity_type:'Company',display_name:'公司甲'},
        {id:bridge,entity_type:'GovernmentAgency',display_name:'共同機關'}],
        edges:[{id:'55555555-5555-4555-8555-555555555555',source:root,target:bridge,
          relationship_type:'CONTRACT_WITH',primary_evidence:evidence}],has_more:false}};
      if(path===`/api/v1/graph/${bridge}`)body={data:{nodes:[
        {id:bridge,entity_type:'GovernmentAgency',display_name:'共同機關'},
        {id:other,entity_type:'Company',display_name:'公司乙'}],
        edges:[{id:'66666666-6666-4666-8666-666666666666',source:other,target:bridge,
          relationship_type:'CONTRACT_WITH',primary_evidence:evidence}],has_more:false}};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.goto('https://tei.local/');
    await page.locator('#q').fill('22099131');
    await page.locator('#search').click();
    await page.locator('#svg .node[data-type="related_company"]').first().waitFor();
    assert.equal(await page.locator('#svg .node[data-type="related_company"]').count(),3);
    assert.equal(await page.locator('#svg .node[data-hub="related"]').count(),1);
    const layout=await page.evaluate(()=>{
      const hub=Number(document.querySelector('#svg .node[data-hub="related"] circle:not(.hit)').getAttribute('cy'));
      const children=[...document.querySelectorAll('#svg .node[data-type="related_company"] circle:not(.hit):not(.related-halo)')];
      const branches=[...document.querySelectorAll('#svg .related-branch')];
      const person=Number(document.querySelector('#svg .node[data-hub="person"] circle:not(.hit)').getAttribute('cy'));
      return {hub,children:children.map(circle=>({x:Number(circle.getAttribute('cx')),y:Number(circle.getAttribute('cy'))})),
        branches:branches.map(line=>({y1:line.getAttribute('y1'),y2:line.getAttribute('y2')})),person};
    });
    assert.equal(layout.children[1].y,layout.hub,'Expanded children center on their parent hub');
    assert(layout.children.every(child=>child.x===layout.children[0].x),'Children share one aligned column');
    assert(layout.children[2].y+60<layout.person,'Expanded company lane does not overlap the next hub');
    assert.equal(layout.branches.length,3);
    assert(layout.branches.every(branch=>branch.y1===branch.y2),'Branches stay horizontal');
    await page.locator('#svg .node[data-type="related_company"]').first().click();
    assert.match(await page.locator('#nodeInfoBody').textContent(),/director-1/);
    assert.equal(await page.locator('#nodeInfoBody a[href^="https://data.gcis.nat.gov.tw"]').count(),1);
    for(const width of [1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      const graph=await page.locator('#svg').boundingBox();
      assert(graph && graph.width>200 && graph.height>200,`Company graph vanished at ${width}px`);
      assert.equal(await page.locator('#svg .node[data-type="related_company"]').count(),3);
      const boxes=await Promise.all((await page.locator('#svg .node[data-type="related_company"]').all())
        .map(node=>node.boundingBox()));
      assert(boxes.every(box=>box&&box.x>=graph.x&&box.x+box.width<=graph.x+graph.width),
        `Related-company labels overflow the graph at ${width}px`);
    }
    await page.goto(`https://tei.local/graph/${root}`);
    await page.locator(`#svg .node[data-node-id="${other}"]`).waitFor();
    assert.equal(await page.locator('#svg .node').count(),3);
    assert.equal(await page.locator('#svg .edge-group').count(),2);
    await page.locator('#svg .edge-group').last().click();
    assert.match(await page.locator('#nodeInfoBody').textContent(),/official-1/);
    assert.deepEqual(errors,[]);
    console.log('Automatic company graph: live exact-ID source and published two-hop evidence passed.');
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
