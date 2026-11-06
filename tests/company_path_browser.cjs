/** Optional real-browser regression: NODE_PATH=<playwright modules> node tests/company_path_browser.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const A = {id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',entity_type:'Company',display_name:'公司甲'};
const B = {id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',entity_type:'Company',display_name:'公司乙'};
const C = {id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',entity_type:'GovernmentAgency',display_name:'共同機關'};
const D = {id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd',entity_type:'Company',display_name:'另一家有來源的公司'};
const E = {id:'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',entity_type:'Company',display_name:'同組第二家公司'};
const F = {id:'ffffffff-ffff-4fff-8fff-ffffffffffff',entity_type:'Person',display_name:'已核對董事'};
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
    const visiblePaths=selector=>page.locator(selector).evaluateAll(paths=>paths.filter(path=>
      getComputedStyle(path).visibility==='visible'&&getComputedStyle(path.parentElement).display!=='none').length);
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
      if(path==='/api/v1/graph/'+C.id){
        return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
          data:{nodes:[C,D,E],edges:[D,E].map((company,index)=>({id:'branch'+index,source:company.id,target:C.id,
            relationship_type:'CONTRACT_WITH',primary_evidence:{id:'branch-proof'+index,
              source_name:'Company award notice',source_url:'https://example.gov.tw/award'}}))}})});
      }
      if(path==='/api/v1/graph/'+A.id){
        return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
          data:{nodes:[A,F],edges:[{id:'officer',source:F.id,target:A.id,relationship_type:'DIRECTOR_OF',
            primary_evidence:{id:'registry-proof',source_name:'Company registry',source_url:'https://example.gov.tw/registry'}}]}})});
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
    await assert.doesNotReject(page.locator('#pathResult').getByText('未找到符合條件的關係路徑',{
      exact:false}).waitFor());
    assert.equal(await page.locator('#svg .node').count(),2);
    await page.locator('#pathDepth').selectOption('2');
    await page.locator('#pathFind').click();
    await page.locator('#svg .edge-group').nth(1).waitFor();
    assert.equal(await page.locator('#svg .node').count(),3);
    assert.equal(await page.locator('#svg .edge-group').count(),2);
    assert.equal(await page.locator('#graphTitle').textContent(),'公司甲 ↔ 公司乙');
    assert.equal(await page.locator('#svg').getAttribute('data-path-graph'),'true');
    await page.locator('#svg .edge-group').first().dispatchEvent('click');
    assert.match(await page.locator('#nodeInfoBody').textContent(),/Official public record/);
    const mainNotes=page.locator('#svg .graph-connection-note');
    assert.equal(await mainNotes.count(),2);
    await page.locator('#closeNode').click();
    await page.locator(`#svg .node[data-node-id="${C.id}"]`).dispatchEvent('click');
    const branchNote=page.locator(`#svg .graph-node-frame:has([data-node-id="${D.id}"])`).getByRole('button',{name:/政府標案.*關聯：共同機關.*查看證據/});
    await branchNote.waitFor();
    assert.equal(await mainNotes.count(),4);
    const firstBus=page.locator(`.graph-branch-bus[data-parent="${C.id}"]`);
    assert.equal(await firstBus.count(),1,'two company links share one line to their frame');
    assert.equal(await visiblePaths('.aggregated-branch .edge'),0);
    assert.match(await branchNote.textContent(),/政府標案.*關聯：共同機關/);
    await branchNote.press('Enter');
    assert.match(await page.locator('#nodeInfoBody').textContent(),/Company award notice/);
    await page.locator('#closeNode').click();
    await page.locator(`#svg .node[data-node-id="${A.id}"]`).dispatchEvent('click');
    const branchLines=page.locator('#graphBranchLines');
    await branchLines.waitFor();
    assert.equal(await firstBus.isVisible(),false);
    assert.equal(await visiblePaths('.path-main-edge .edge'),2);
    await branchLines.click();
    assert.equal(await firstBus.isVisible(),true);
    assert.equal(await branchLines.getAttribute('aria-pressed'),'true');
    await branchLines.click();
    assert.equal(await firstBus.isVisible(),false);
    await branchNote.press('Enter');
    assert.match(await page.locator('#nodeInfoBody').textContent(),/Company award notice/);
    assert.equal(await visiblePaths('.aggregated-branch.selected .edge'),1);
    const labelsStayInside=await page.locator('#svg').evaluate(svg=>{
      const boxes=[...svg.querySelectorAll('.graph-type-zone rect')].map(rect=>rect.getBBox());
      return [...svg.querySelectorAll('.graph-connection-note rect')].every(rect=>{
        const b=rect.getBBox();
        return boxes.some(box=>b.x>=box.x&&b.y>=box.y&&b.x+b.width<=box.x+box.width&&b.y+b.height<=box.y+box.height);
      });
    });
    assert(labelsStayInside,'reasons stay inside their colored group frame');
    for(const width of [1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      const graph=await page.locator('#svg').boundingBox();
      assert(graph && graph.width>200 && graph.height>200,
        `Graph vanished at ${width}px`);
      assert.equal(await page.locator('#svg .node').count(),6);
      assert.equal(await page.locator('#svg .edge-group').count(),5);
      assert.equal(await mainNotes.count(),5);
    }
    assert.deepEqual(consoleErrors,[]);
    console.log('Real browser: direct/no-path and shared-node path, group lines, focus toggle, evidence, 1440/1280/1024/768px passed.');
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
