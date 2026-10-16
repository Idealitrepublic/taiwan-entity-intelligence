/** Optional real-browser regression: NODE_PATH=<playwright modules> node tests/company_path_browser.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const A = {id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',entity_type:'Company',display_name:'公司甲'};
const B = {id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',entity_type:'Company',display_name:'公司乙'};
const C = {id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',entity_type:'GovernmentAgency',display_name:'共同機關'};
const E1 = '11111111-1111-4111-8111-111111111111';
const E2 = '22222222-2222-4222-8222-222222222222';
function segment(from, to, id, evidenceId, reverse=false) {
  return {from_entity:from,to_entity:to,traversal_direction:reverse?'reverse':'forward',
    relationship:{id,source_entity_id:reverse?to.id:from.id,
      target_entity_id:reverse?from.id:to.id,relationship_type:'CONTRACT_WITH',
      primary_evidence_id:evidenceId,amount:null,start_date:'2025-01-01'},
    evidence:{id:evidenceId,source_name:'Official public record',source_record_id:id,
      source_url:'https://example.gov.tw/record',retrieved_at:'2026-10-14T00:00:00Z'}};
}

(async () => {
  const browser = await chromium.launch({headless:true,
    executablePath:process.env.TEI_BROWSER_PATH ||
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:900}});
    const consoleErrors = [];
    page.on('pageerror',error=>consoleErrors.push(error.message));
    await page.route('https://tei.local/**',async route=>{
      const url = new URL(route.request().url()),path=url.pathname;
      if(path==='/')return route.fulfill({status:200,contentType:'text/html',body:html});
      if(path==='/api/v1/search'){
        const query=url.searchParams.get('q');
        const item=query==='公司甲'?A:query==='公司乙'?B:null;
        return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
          data:{items:item?[{entity_id:item.id,entity_type:item.entity_type,
            display_name:item.display_name,public_identifier:query==='公司甲'?'11111111':'22222222'}]:[]}})});
      }
      if(path==='/api/v1/paths'){
        assert.equal(url.searchParams.get('company_only'),'1');
        assert.equal(url.searchParams.get('source'),A.id);
        assert.equal(url.searchParams.get('target'),B.id);
        const depth=Number(url.searchParams.get('max_depth'));
        const data=depth===1?{found:false,depth:null,segments:[],max_depth:1}:
          {found:true,depth:2,source_entity:A,target_entity:B,max_depth:depth,
           shared_node_complete:true,segments:[
             segment(A,C,'33333333-3333-4333-8333-333333333333',E1),
             segment(C,B,'44444444-4444-4444-8444-444444444444',E2,true)]};
        return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({data})});
      }
      return route.fulfill({status:200,contentType:'application/json',body:'{}'});
    });
    await page.goto('https://tei.local/');
    await page.locator('#pathSourceQuery').fill('公司甲');
    await page.locator('#pathSourceMatches .path-match').first().click();
    await page.locator('#pathTargetQuery').fill('公司乙');
    await page.locator('#pathTargetMatches .path-match').first().click();
    await page.locator('#pathDepth').selectOption('1');
    await page.locator('#pathFind').click();
    await assert.doesNotReject(page.locator('#pathResult').getByText('未找到共用節點',{
      exact:false}).waitFor());
    assert.equal(await page.locator('#svg .node').count(),0);
    await page.locator('#pathDepth').selectOption('2');
    await page.locator('#pathFind').click();
    await page.locator('#svg .edge-group').nth(1).waitFor();
    assert.equal(await page.locator('#svg .node').count(),3);
    assert.equal(await page.locator('#svg .edge-group').count(),2);
    assert.equal(await page.locator('#graphTitle').textContent(),'公司甲 ↔ 公司乙');
    assert.equal(await page.locator('#svg').getAttribute('data-path-graph'),'true');
    await page.locator('#svg .edge-group').first().dispatchEvent('click');
    assert.match(await page.locator('#nodeInfoBody').textContent(),/Official public record/);
    for(const width of [1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      const graph=await page.locator('#svg').boundingBox();
      assert(graph && graph.width>200 && graph.height>200,
        `Graph vanished at ${width}px`);
      assert.equal(await page.locator('#svg .node').count(),3);
      assert.equal(await page.locator('#svg .edge-group').count(),2);
    }
    assert.deepEqual(consoleErrors,[]);
    console.log('Real browser: direct/no-path and shared-node/path graph, evidence, 1440/1280/1024/768px passed.');
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
