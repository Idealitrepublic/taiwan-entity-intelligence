/** Browser geometry regression: NODE_PATH=<playwright modules> node tests/knowledge_graph_layout_browser.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const root = {id:'11111111-1111-4111-8111-111111111111',entity_type:'Company',display_name:'臺灣先進製造與國際研發股份有限公司／Taiwan Advanced Manufacturing Company'};
const first = [
  ['Person','董事與公司代表王明明／Director of International Operations'],
  ['Politician','立法委員陳○○／Legislator with a long English title'],
  ['GovernmentAgency','臺北市政府產業發展局／Economic Development Agency'],
  ['Contract','大型採購與系統整合標案／Public Procurement Contract 2026'],
  ['Judgment','臺灣臺北地方法院民事裁判／Judgment with detailed title'],
  ['Penalty','勞動基準法裁罰案件／Administrative Labor Penalty'],
  ['Company','共同公開紀錄企業甲股份有限公司／Connected Company A'],
  ['Company','共同公開紀錄企業乙股份有限公司／Connected Company B'],
  ['GovernmentOfficial','政府官員與採購承辦人／Government Official'],
  ['PoliticalContribution','政治獻金申報紀錄／Political Contribution'],
].map(([entity_type,display_name],index)=>({id:`22222222-2222-4222-8222-${String(index).padStart(12,'0')}`,entity_type,display_name}));
const second = [
  ['Company','多層延伸公司與關係企業股份有限公司／Second-layer Corporation'],
  ['Person','王○○／Second-layer Director with unusually long name'],
  ['GovernmentAgency','中央政府採購與公共工程委員會／Second-layer Agency'],
  ['Judgment','第二層司法裁判紀錄及完整案由／Second-layer Judgment'],
  ['Penalty','第二層地方政府勞動裁罰紀錄／Second-layer Penalty'],
  ['Contract','第二層公共採購與服務契約／Second-layer Procurement'],
].map(([entity_type,display_name],index)=>({id:`33333333-3333-4333-8333-${String(index).padStart(12,'0')}`,entity_type,display_name}));
const denseNodes=Array.from({length:35},(_,index)=>({id:`44444444-4444-4444-8444-${String(index).padStart(12,'0')}`,
  entity_type:index%3===0?'Judgment':index%3===1?'Contract':'Company',
  display_name:`大量公開紀錄節點第 ${index+1} 筆／Long source-backed record with complete label ${index+1}`}));
const evidence = index => ({id:`evidence-${index}`,source_name:'官方公開來源',source_record_id:`official-${index}`,
  source_url:`https://example.gov.tw/record/${index}`,retrieved_at:'2026-10-16T00:00:00Z'});
const edge = (from,to,index) => ({id:`edge-${index}`,source:from,target:to,relationship_type:index%2?'CONTRACT_WITH':'RELATED_TO_JUDGMENT',primary_evidence:evidence(index)});

async function geometry(page, label) {
  const result = await page.evaluate(() => {
    const svg=document.querySelector('#svg'),viewport=svg.getBoundingClientRect();
    const nodes=[...svg.querySelectorAll('.node')].map(element=>({id:element.dataset.nodeId,
      box:element.getBoundingClientRect(),texts:[...element.querySelectorAll('text')]}));
    const overlap=[];
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const a=nodes[i].box,b=nodes[j].box;
      if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1 && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)
        overlap.push([nodes[i].id,nodes[j].id]);
    }
    const clipped=nodes.filter(node=>node.box.left<viewport.left-2||node.box.right>viewport.right+2||
      node.box.top<viewport.top-2||node.box.bottom>viewport.bottom+2).map(node=>node.id);
    const truncated=nodes.filter(node=>node.texts.some(text=>text.textContent.includes('…'))).map(node=>node.id);
    const texts=nodes.flatMap(node=>node.texts.map(text=>({id:node.id,box:text.getBBox()})));
    const crossed=[];
    for(const item of svg.querySelectorAll('.edge-group path.edge')){
      const group=item.closest('.edge-group'),from=group.dataset.source,to=group.dataset.target,length=item.getTotalLength();
      for(let offset=4;offset<length-4;offset+=4){const point=item.getPointAtLength(offset),hit=texts.find(text=>text.id!==from&&text.id!==to&&
        point.x>text.box.x+1&&point.x<text.box.x+text.box.width-1&&point.y>text.box.y+1&&point.y<text.box.y+text.box.height-1);
        if(hit){crossed.push([group.dataset.edgeId,hit.id]);break}}
    }
    const filledEdges=[...svg.querySelectorAll('.edge-group path.edge')].filter(path=>getComputedStyle(path).fill!=='none').length;
    return{nodes:nodes.length,overlap,clipped,truncated,crossed,filledEdges};
  });
  assert.deepEqual(result.overlap,[],`${label}: nodes and full labels do not overlap`);
  assert.deepEqual(result.clipped,[],`${label}: node labels remain inside the graph viewport`);
  assert.deepEqual(result.truncated,[],`${label}: node labels are not truncated`);
  assert.deepEqual(result.crossed,[],`${label}: connectors avoid unrelated labels`);
  assert.equal(result.filledEdges,0,`${label}: routed connectors must not paint filled polygons`);
  return result;
}

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.TEI_BROWSER_PATH||
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];let dense=false;
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('https://tei.local/**',route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/'||path.startsWith('/graph/'))return route.fulfill({status:200,contentType:'text/html',body:html});
      let data={};
      if(path===`/api/v1/entities/${root.id}`)data={data:{...root,identity_status:'EXACT',evidence:[]}};
      if(path===`/api/v1/graph/${root.id}`){const children=dense?[...first,...denseNodes]:first;data={data:{nodes:[root,...children],edges:children.map((node,index)=>edge(root.id,node.id,index)),has_more:false}}}
      if(path===`/api/v1/graph/${first[2].id}`)data={data:{nodes:[first[2],...second],edges:second.map((node,index)=>edge(first[2].id,node.id,index+100)),has_more:false}};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
    });
    await page.goto(`https://tei.local/graph/${root.id}`);
    await page.locator(`#svg .node[data-node-id="${first[9].id}"]`).waitFor();
    assert((await geometry(page,'10 first-layer nodes')).nodes>=11);
    await page.locator(`#svg .node[data-node-id="${first[2].id}"] circle:not(.hit)`).click();
    await page.locator(`#svg .node[data-node-id="${second[5].id}"]`).waitFor();
    assert.equal((await geometry(page,'mixed second layer')).nodes,17);
    await page.locator('#svg .edge-group[data-edge-id="edge-100"]').dispatchEvent('click');
    assert.match(await page.locator('#nodeInfoBody').innerText(),/official-100/);
    await page.locator('#closeNode').click();
    if(process.env.TEI_KNOWLEDGE_SCREENSHOT)await page.locator('.graph').screenshot({path:process.env.TEI_KNOWLEDGE_SCREENSHOT});
    for(const width of[1440,1280,1024,768]){
      await page.setViewportSize({width,height:900});
      await geometry(page,`${width}px viewport`);
      await page.locator('#fit').click();
      await geometry(page,`${width}px fit`);
    }
    const before=await page.locator('#zoomValue').innerText();
    await page.locator('#plus').click();
    assert.notEqual(await page.locator('#zoomValue').innerText(),before,'Zoom still works');
    await page.locator('#fit').click();
    const draggable=page.locator(`#svg .node[data-node-id="${second[2].id}"] circle:not(.hit)`),prior=Number(await draggable.getAttribute('cx')),box=await draggable.boundingBox();
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
    await page.mouse.down();await page.mouse.move(box.x+box.width/2+18,box.y+box.height/2,{steps:5});await page.mouse.up();
    assert.notEqual(Number(await draggable.getAttribute('cx')),prior,'Dragging still moves a knowledge node');
    await page.locator('#fit').click();
    await page.locator('#collapse').click();
    assert.equal(await page.locator('#svg .node').count(),1,'Collapse keeps the company root');
    dense=true;
    await page.goto(`https://tei.local/graph/${root.id}`);
    await page.locator(`#svg .node[data-node-id="${denseNodes.at(-1).id}"]`).waitFor();
    assert((await geometry(page,'45-node dense graph')).nodes>=46);
    for(const width of[1440,1280,1024,768]){await page.setViewportSize({width,height:900});await geometry(page,`dense ${width}px`)}
    await page.setViewportSize({width:1280,height:900});
    const compactWidth=(await page.locator('#svg').boundingBox()).width;
    await page.locator('#graphFocus').click();
    assert.equal(await page.locator('#graphFocus').getAttribute('aria-pressed'),'true');
    assert((await page.locator('#svg').boundingBox()).width>compactWidth+300,'Graph focus gives the diagram more room');
    assert((await page.locator('#svg').boundingBox()).height>700,'Graph focus makes labels physically larger');
    await geometry(page,'1280px focused graph');
    await page.locator('#graphFocus').click();
    assert.equal(await page.locator('#graphFocus').getAttribute('aria-pressed'),'false');
    await page.setViewportSize({width:390,height:844});
    const mobileList=page.locator('#mobileGraphList');
    assert(await mobileList.isVisible(),'Mobile graph has an accessible node and edge list');
    assert((await mobileList.locator('button').count())>=46,'All loaded nodes remain selectable on mobile');
    assert((await mobileList.locator('button').first().evaluate(element=>parseFloat(getComputedStyle(element).fontSize)))>=14);
    await mobileList.locator('button').filter({hasText:first[0].display_name}).first().click();
    assert.match(await page.locator('#nodeInfoTitle').innerText(),/董事與公司代表/);
    await page.locator('#closeNode').click();
    await mobileList.locator('button').filter({hasText:root.display_name+' → '+first[0].display_name}).first().click();
    assert.match(await page.locator('#nodeInfoBody').innerText(),/official-0/);
    assert.deepEqual(errors,[]);
    console.log('Entity graph: 10, 17 and 46+ mixed nodes; two layers; labels, edges, Evidence, desktop focus, 1440/1280/1024/768px geometry and mobile list passed.');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
