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
const linkedCompany = uniform => {const result={status:'ok',uniform_number:uniform,
  company_name:`法人公司 ${uniform}`,company:{},people:[],evidence_status:{},
  graph:{nodes:[{id:`company:${uniform}`,type:'company',label:`法人公司 ${uniform}`},
    {id:'person:director:1',type:'person',label:'測試董事',properties:{position:'董事',source:'經濟部董監事資料'}},
    {id:'penalty:case-1',type:'penalty',label:'勞動基準法第24條',properties:{date:'2026-08-01',source_url:'https://example.gov.tw/penalty',source_record_id:'case-1'}},
    {id:'judicial:case-2',type:'judicial',label:'測試裁判',properties:{date:'2026-07-01',source_url:'https://example.gov.tw/judgment',jid:'case-2'}}],edges:[]},
  evidence:[{id:'penalty:case-1',source_name:'勞動裁罰公開資料',source_url:'https://example.gov.tw/penalty',source_record_id:'case-1'},
    {id:'judicial:case-2',source_name:'司法院',source_url:'https://example.gov.tw/judgment',source_record_id:'case-2',match_rule:'company_name_candidate_requires_verification'}]};
  if(uniform==='12345678')for(let index=2;index<=10;index++)result.graph.nodes.push({id:`person:director:${index}`,type:'person',label:`測試董事 ${index}`,properties:{position:'董事',source:'經濟部董監事資料'}});
  return result;
};

(async () => {
  const browser = await chromium.launch({headless:true,
    executablePath:process.env.TEI_BROWSER_PATH ||
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:900}});
    const errors=[],linkedFetches=new Map();
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('https://tei.local/**',async route=>{
      const url=new URL(route.request().url()),path=url.pathname;
      if(path==='/' || path.startsWith('/graph/'))return route.fulfill({status:200,
        contentType:'text/html',body:html});
      let body={};
      if(path==='/api/company/22099131')body=companyResponse;
      if(path==='/api/procurement/22099131')body={status:'ok',matched:0,records:[]};
      if(/^\/api\/company\/(12345678|22345678)$/.test(path)){
        const uniform=path.split('/').at(-1);linkedFetches.set(uniform,(linkedFetches.get(uniform)||0)+1);body=linkedCompany(uniform);
      }
      if(/^\/api\/procurement\/(12345678|22345678)$/.test(path))body={status:'ok',matched:1,source:'政府電子採購網',records:[{id:'award-1',title:'公開決標公告',date:'2026-06-01',agency:'測試機關',source_url:'https://example.gov.tw/award'}]};
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
    assert.equal(await page.locator('#svg .node[data-type="related_connection"]').count(),3);
    assert.equal(await page.locator('#svg .node[data-hub="related"]').count(),1);
    const layout=await page.evaluate(()=>{
      const hub=Number(document.querySelector('#svg .node[data-hub="related"] circle:not(.hit)').getAttribute('cy'));
      const children=[...document.querySelectorAll('#svg .node[data-type="related_company"] circle:not(.hit):not(.related-halo)')];
      const connectors=[...document.querySelectorAll('#svg .node[data-type="related_connection"] circle:not(.hit):not(.connection-halo)')];
      const branches=[...document.querySelectorAll('#svg .related-branch')];
      const person=Number(document.querySelector('#svg .node[data-hub="person"] circle:not(.hit)').getAttribute('cy'));
      return {hub,children:children.map(circle=>({x:Number(circle.getAttribute('cx')),y:Number(circle.getAttribute('cy'))})),
        connectors:connectors.map(circle=>({x:Number(circle.getAttribute('cx')),y:Number(circle.getAttribute('cy'))})),
        branches:branches.map(line=>({y1:line.getAttribute('y1'),y2:line.getAttribute('y2')})),person};
    });
    assert.equal(layout.connectors[1].y,layout.hub,'Connection sources center on their parent hub');
    assert(layout.connectors.every(child=>child.x===layout.connectors[0].x),'Connection sources share one aligned column');
    assert(layout.children.every((company,index)=>company.x>layout.connectors[index].x&&company.y===layout.connectors[index].y),
      'Each company appears beside the specific source record that connects it to A');
    assert.equal(layout.branches.length,3);
    assert(layout.branches.every(branch=>branch.y1===branch.y2),'Branches stay horizontal');
    await page.locator('#svg .node[data-type="related_connection"]').first().click();
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
    await page.setViewportSize({width:1280,height:900});
    await page.locator('#svg .node[data-type="related_company"]').first().click();
    assert.match(await page.locator('#nodeInfoBody').textContent(),/director-1/);
    assert.equal(await page.locator('#nodeInfoBody a[href^="https://data.gcis.nat.gov.tw"]').count(),1);
    await page.locator('#svg .node[data-type="related_category"]').first().waitFor();
    assert.equal(await page.locator('#svg .node[data-type="related_category"]').count(),4);
    assert.equal(await page.locator('#svg .node[data-type="related_connection"] .connection-halo').count(),3);
    assert.equal(await page.locator('#svg .node[data-type="related_company"] .related-halo').count(),3);
    const sourceOutline=await page.locator('#svg .node[data-type="related_connection"] .connection-halo').first().evaluate(element=>getComputedStyle(element).stroke);
    const companyOutline=await page.locator('#svg .node[data-type="related_company"] .related-halo').first().evaluate(element=>getComputedStyle(element).stroke);
    assert.equal(sourceOutline,'rgb(246, 211, 124)');
    assert.equal(companyOutline,'rgb(246, 211, 124)');
    for(const width of [1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      const graph=await page.locator('#svg').boundingBox();
      const categories=await Promise.all((await page.locator('#svg .node[data-type="related_category"]').all()).map(item=>item.boundingBox()));
      assert(categories.every(box=>box&&box.x>=graph.x&&box.x+box.width<=graph.x+graph.width),
        `Expanded linked-company categories overflow at ${width}px`);
    }
    await page.setViewportSize({width:1280,height:900});
    await page.locator('#svg .node[data-node-id="related-category:12345678:person"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#svg .node[data-type="related_detail"]').count(),8,'Large source lists stay bounded');
    assert.match(await page.locator('#svg .node[data-node-id="related-category:12345678:person"]').textContent(),/顯示前 8 筆/);
    await page.locator('#svg .node[data-node-id="related-category:12345678:penalty"]').focus();
    await page.keyboard.press('Enter');
    await page.locator('#svg .node[data-node-id="related-detail:12345678:penalty%3Acase-1"]').waitFor();
    await page.locator('#svg .node[data-node-id="related-detail:12345678:penalty%3Acase-1"]').click();
    assert.equal(await page.locator('#nodeInfoBody a[href="https://example.gov.tw/penalty"]').count(),1);
    await page.locator('#svg .node[data-node-id="related-category:12345678:judicial"]').focus();
    await page.keyboard.press('Enter');
    await page.locator('#svg .node[data-node-id="related-detail:12345678:judicial%3Acase-2"]').click();
    assert.match(await page.locator('#nodeInfoBody').textContent(),/名稱候選，須核對原文/);
    const firstCategoryPositions=await page.locator('#svg .node[data-type="related_category"] circle:not(.hit)').evaluateAll(circles=>circles.map(circle=>Number(circle.getAttribute('cy'))));
    assert(firstCategoryPositions.every((y,index)=>!index||y-firstCategoryPositions[index-1]>40),'Linked company categories retain readable vertical spacing');
    await page.locator('#svg .node[data-node-id="related-company:22345678"]').focus();
    await page.keyboard.press('Enter');
    await page.locator('#svg .node[data-node-id="related-category:22345678:person"]').waitFor();
    assert.equal(await page.locator('#svg .node[data-type="related_category"]').count(),8,'A second linked company expands independently');
    const categoryLanes=await page.evaluate(()=>Object.fromEntries(['12345678','22345678'].map(uniform=>[uniform,[...document.querySelectorAll(`#svg .node[data-node-id^="related-category:${uniform}:"] circle:not(.hit)`)].map(circle=>Number(circle.getAttribute('cy')))])));
    assert(Math.max(...categoryLanes['12345678'])+40<Math.min(...categoryLanes['22345678']),
      'Two expanded companies receive non-overlapping vertical category lanes');
    await page.locator('#svg .node[data-node-id="related-company:12345678"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#svg .node[data-type="related_category"]').count(),4,'Collapsing one linked company retains the other');
    await page.locator('#svg .node[data-node-id="related-company:12345678"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(linkedFetches.get('12345678'),1,'Reopening uses the cached read-only company response');
    await page.locator('#svg .node[data-node-id="related-company:32345678"]').focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelector('#nodeInfoBody')?.textContent?.includes('公司統編與查詢結果不一致'));
    assert.match(await page.locator('#nodeInfoBody').textContent(),/公司統編與查詢結果不一致/);
    assert.equal(await page.locator('#svg .node[data-node-id="related-category:32345678:person"]').count(),0,
      'A failed company lookup must not create unsupported graph nodes');
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
