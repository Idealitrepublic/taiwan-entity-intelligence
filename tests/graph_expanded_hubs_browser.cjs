/** Browser regression: NODE_PATH=<playwright modules> node tests/graph_expanded_hubs_browser.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const company = 'company:22099131';
const nodes = [
  { id: company, type: 'company', label: '測試公司／Test Company with longer name' },
  ...['甲', '乙', '丙', '丁'].map((name, index) => ({ id: `person:${index}`, type: 'person', label: `關係人${name}／Related person with long English name ${index}`, properties: { position: ['監察人','董事長','董事','副董事長'][index] } })),
  ...['第24條', '第32條', '第36條'].map((law, index) => ({ id: `penalty:${index}`, type: 'penalty', label: `勞動基準法${law}`, properties: { law_text: `勞動基準法${law}`, date: `2025-0${index + 1}-01`, agency:'臺北市政府', fine: '10000', source_url:'https://data.gov.tw/dataset/109896' } })),
  {id:'penalty:gender',type:'penalty',label:'性別平等工作法第13條',properties:{law_text:'性別平等工作法第13條',date:'2024-04-05',agency:'高雄市政府'}},
  {id:'penalty:employment',type:'penalty',label:'就業服務法第5條',properties:{law_text:'就業服務法第5條',date:'2023-03-01',agency:'臺中市政府'}},
  {id:'penalty:safety',type:'penalty',label:'職業安全衛生法第6條',properties:{law_text:'職業安全衛生法第6條',date:'2022-03-01',agency:'新北市政府'}},
  ...Array.from({ length: 50 }, (_, index) => ({ id: `judicial:${index}`, type: 'judicial', label: `裁判 ${index + 1}／Court decision concerning extended public source record`, properties: { date: index<49?`2026-01-${String(index%28+1).padStart(2,'0')}`:'2025-01-01', jid: `J-${index}`, source_url: 'https://judicial.gov.tw/record' } })),
  {id:'judicial:feb',type:'judicial',label:'二月裁判',properties:{date:'2026-02-01',jid:'J-FEB',source_url:'https://judicial.gov.tw/feb'}},
  {id:'judicial:mar',type:'judicial',label:'三月裁判',properties:{date:'2026-03-01',jid:'J-MAR',source_url:'https://judicial.gov.tw/mar'}},
  {id:'website:example',type:'website',label:'company-website-with-very-long-public-domain.example.tw'},
  {id:'anti_fraud:example',type:'anti_fraud',label:'公開反詐來源中需要完整閱讀的長名稱／Fraud source record'}
];
const awards = [
  { id: 'a', title: '臺北市採購案一', agency: '臺北市政府', date: '2025-01-01' },
  { id: 'b', title: '臺北市採購案二', agency: '臺北市政府', date: '2024-01-01' },
  { id: 'c', title: '臺中市採購案', agency: '臺中市政府', date: '2025-01-01' }
];
const body = { status: 'ok', uniform_number: '22099131', company_name: '測試公司', company: {}, people: [],
  graph: { nodes, edges: [{source:company,target:'website:example',relationship:'website'},
    {source:'website:example',target:'anti_fraud:example',relationship:'listed_in_anti_fraud'}] }, evidence: [], labor_penalties: [], judicial_result: { records: [], matched: 0 }, evidence_status: {} };
async function assertLayout(page, label, { focused = false } = {}) {
  const result = await page.evaluate(() => {
    const svg = document.querySelector('#svg'), viewport = svg.getBoundingClientRect();
    const nodes = [...svg.querySelectorAll('.node')].map(node => ({ id: node.dataset.nodeId,
      box: node.getBoundingClientRect(), text: [...node.querySelectorAll('text')].map(item => item.textContent) }));
    const overlaps = [];
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i].box, b = nodes[j].box;
      if (Math.min(a.right,b.right)-Math.max(a.left,b.left)>1 && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)
        overlaps.push([nodes[i].id,nodes[j].id]);
    }
    const clipped = nodes.filter(node => node.box.left < viewport.left-2 || node.box.right > viewport.right+2 ||
      node.box.top < viewport.top-2 || node.box.bottom > viewport.bottom+2).map(node => node.id);
    const ellipses = nodes.filter(node => node.text.some(value => value.includes('…'))).map(node => node.id);
    const info = document.querySelector('#nodeInfo'), infoBox = info.hidden ? null : info.getBoundingClientRect();
    const covered = infoBox ? nodes.filter(node => Math.min(node.box.right,infoBox.right)-Math.max(node.box.left,infoBox.left)>1 &&
      Math.min(node.box.bottom,infoBox.bottom)-Math.max(node.box.top,infoBox.top)>1).map(node => node.id) : [];
    return { count:nodes.length, overlaps, clipped, ellipses, covered };
  });
  assert.deepEqual(result.overlaps,[],`${label}: no node/label overlap`);
  if (!focused) assert.deepEqual(result.clipped,[],`${label}: Fit keeps all labels inside graph viewport`);
  assert.deepEqual(result.ellipses,[],`${label}: no label truncation`);
  assert.deepEqual(result.covered,[],`${label}: detail panel does not cover nodes or labels`);
  return result;
}
async function assertReadableBranch(page, childType, label) {
  const result = await page.evaluate(type => {
    const svg = document.querySelector('#svg'), viewport = svg.getBoundingClientRect();
    const visible = [...svg.querySelectorAll(`.node[data-type="${type}"]`)].map(node => {
      const circle = node.querySelector('circle:not(.hit):not(.related-halo)');
      const text = node.querySelector('text.child-label');
      return { id: node.dataset.nodeId, circle: circle?.getBoundingClientRect(), text: text?.getBoundingClientRect() };
    }).filter(node => node.circle && node.text && node.circle.left >= viewport.left &&
      node.text.right <= viewport.right && node.text.top >= viewport.top && node.text.bottom <= viewport.bottom);
    return { visible, zoom: Number(document.querySelector('#zoomValue').textContent.replace('%','')) };
  }, childType);
  assert(result.visible.length > 0, `${label}: at least one expanded record is visible`);
  assert(result.visible.some(node => node.circle.width >= 24 && node.text.height >= 12),
    `${label}: expanded circles and labels are legible at actual screen size`);
  assert(result.zoom >= 115, `${label}: expanding must not shrink the entire graph`);
}

(async () => {
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.TEI_BROWSER_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://tei.local/**', route => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/') return route.fulfill({ status: 200, contentType: 'text/html', body: html });
      const result = path === '/api/company/22099131' ? body
        : path === '/api/procurement/22099131' ? { status: 'ok', matched: awards.length, records: awards }
        : path === '/api/company-related/22099131' ? { status: 'ok', uniform_number: '22099131', items: [
          '測試投資股份有限公司／Long affiliated company name one', '另一間有公開紀錄連結的公司／Connected Company'
        ].map((company_name,index)=>({uniform_number:`2209914${index}`,company_name,connection_type:'same_award_notice',connection_label:'共同標案',shared_record:{id:`award-${index}`,title:`共同決標公告 ${index}`},evidence:{source_url:'https://example.gov.tw/award',source_name:'測試來源',source_record_id:`award-${index}`,retrieved_at:'2026-10-16T00:00:00Z'}})) } : {};
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(result) });
    });
    await page.goto('https://tei.local/');
    await page.locator('#q').fill('22099131');
    await page.locator('#search').click();
    await page.locator('#svg .node[data-hub="procurement"]').waitFor();
    await page.locator('#svg .node[data-hub="related"]').click();
    const panel = await page.evaluate(() => {
      const info=document.querySelector('#nodeInfo'),box=info.getBoundingClientRect(),graph=document.querySelector('.graph').getBoundingClientRect();
      return {left:box.left,graphRight:graph.right,visible:info.contains(document.elementFromPoint(box.left+20,box.top+20))};
    });
    assert(panel.left>=panel.graphRight-2 && panel.visible,'Desktop details remain visible beside, not over, the graph');
    const anchors = await page.evaluate(() => {
      const center = document.querySelector('#svg .node[data-type="company"]');
      const hubs = [...document.querySelectorAll('#svg .node.hub')];
      const point = element => { const circle = element.querySelector('circle:not(.hit)');
        return {x:Number(circle.getAttribute('cx')),y:Number(circle.getAttribute('cy'))}; };
      return {center:point(center),label: center.querySelector('text').getBoundingClientRect().toJSON(),
        circle:center.querySelector('circle:not(.hit)').getBoundingClientRect().toJSON(),
        hubs:hubs.map(hub=>({kind:hub.dataset.hub,...point(hub)}))};
    });
    const hubYs = anchors.hubs.map(hub=>hub.y), steps = hubYs.slice(1).map((y,index)=>y-hubYs[index]);
    assert(anchors.label.bottom < anchors.circle.top, 'Company root label aligns above the circle like category labels');
    assert(anchors.hubs.every(hub=>hub.x===anchors.hubs[0].x), 'All categories share one column');
    assert.equal(anchors.center.y,anchors.hubs.find(hub=>hub.kind==='judicial').y,
      'Company root and judicial hub share the reference row');
    assert(steps.every(step=>Math.abs(step-steps[0])<.01), 'Connected companies and awards match all category spacing');
    assert.equal(await page.locator('#svg .root-branch').count(),anchors.hubs.length+1,
      'Every company category and its website connect through the same root rail');
    assert.match(await page.locator('#svg .ancillary-spine').getAttribute('d'),/^M .* H .* V .* H /,
      'The website-to-anti-fraud connection also follows an orthogonal branch');
    await assertLayout(page, 'collapsed category layout');
    await page.locator('#svg .node[data-hub="related"]').click();
    const cases = [
      ['related', 'related_connection', 2], ['person', 'person', 4], ['penalty', 'penalty_law', 4], ['judicial', 'judicial_year', 2], ['procurement', 'procurement_city', 2]
    ];
    for (const [hubType, childType, count] of cases) {
      if (hubType !== 'related') {
        await page.locator('#collapse').click();
        await page.locator(`#svg .node[data-hub="${hubType}"]`).click();
      }
      const layout = await page.evaluate(({ hubType, childType }) => {
        const position = element => {
          const circle = element.querySelector('circle:not(.hit):not(.related-halo)');
          return { x: Number(circle.getAttribute('cx')), y: Number(circle.getAttribute('cy')) };
        };
        const hub = position(document.querySelector(`#svg .node[data-hub="${hubType}"]`));
        const children = [...document.querySelectorAll(`#svg .node[data-type="${childType}"]`)].map(position);
        const branches = [...document.querySelectorAll('#svg .graph-branch:not(.root-branch)')].map(line => ({
          x1: Number(line.getAttribute('x1')), y1: Number(line.getAttribute('y1')),
          x2: Number(line.getAttribute('x2')), y2: Number(line.getAttribute('y2'))
        }));
        const spine = document.querySelector('#svg .graph-spine:not(.root-spine)')?.getAttribute('d');
        return { hub, children, branches, spine };
      }, { hubType, childType });
      assert.equal(layout.children.length, count, `${hubType} keeps every source-backed node`);
      assert.equal((layout.children[0].y + layout.children.at(-1).y) / 2, layout.hub.y,
        `${hubType} children align with their parent`);
      assert(layout.children.every(point => point.x === layout.children[0].x), `${hubType} shares an aligned lane`);
      assert.equal(layout.branches.length, hubType==='related'?count*2:count,
        `${hubType} has one branch to each source and another to its company`);
      assert(layout.branches.every(branch => branch.y1 === branch.y2 && branch.x2 > branch.x1),
        `${hubType} branches are horizontal`);
      assert(layout.spine && layout.spine.includes(`${layout.hub.y}`), `${hubType} has a parent rail`);
      if(hubType==='related'){
        assert.equal(await page.locator('#svg .node[data-type="related_company"]').count(),2,
          'The two verified companies remain visible beyond their source-record nodes');
        assert.match(await page.locator('#svg .node[data-type="related_connection"]').first().getAttribute('aria-label'),
          /共同決標公告 0/, 'The connecting node names the actual shared award notice');
      }
      const column = await page.evaluate(() => {
        const position = element => {const circle=element.querySelector('circle:not(.hit)');return{x:Number(circle.getAttribute('cx')),y:Number(circle.getAttribute('cy'))}};
        return {root:position(document.querySelector('#svg .node[data-type="company"]')),
          hubs:[...document.querySelectorAll('#svg .node.hub')].map(hub=>({kind:hub.dataset.hub,...position(hub)}))};
      });
      assert(column.hubs.every(point=>point.x===column.hubs[0].x),`${hubType}: category hubs stay in one column`);
      assert.equal(column.root.y,column.hubs.find(hub=>hub.kind==='judicial').y,
        `${hubType}: root stays anchored to the judicial row`);
      const pitches=column.hubs.slice(1).map((hub,index)=>hub.y-column.hubs[index].y);
      assert(pitches.every(pitch=>pitch===pitches[0]),
        `${hubType}: expanded records never create extra vertical gaps between category hubs`);
      await assertLayout(page, `${hubType} expanded`, { focused: true });
      await assertReadableBranch(page, childType, `${hubType} expanded`);
      if(hubType==='person'){
        const labels=await page.locator('#svg .node[data-type="person"]').evaluateAll(items=>items.map(item=>item.getAttribute('aria-label')));
        assert(labels[0].includes('董事長')&&labels[1].includes('副董事長')&&labels[2].includes('董事')&&labels[3].includes('監察人'),
          'People labels include roles and sort by position before name');
      }
      if (hubType === 'related' && process.env.TEI_GRAPH_RELATED_SCREENSHOT)
        await page.locator('.graph').screenshot({ path: process.env.TEI_GRAPH_RELATED_SCREENSHOT });
      if (hubType === 'penalty') {
        const labels=await page.locator('#svg .node[data-type="penalty_law"]').evaluateAll(items=>items.map(item=>item.getAttribute('aria-label')));
        assert(labels.some(label=>label.includes('勞動基準法'))&&labels.some(label=>label.includes('性別平等工作法'))&&labels.some(label=>label.includes('就業服務法'))&&labels.some(label=>label.includes('職業安全衛生法')));
        await page.locator('#svg .node[data-type="penalty_law"]').filter({hasText:'勞動基準法'}).click();
        assert.equal(await page.locator('#svg .node[data-type="penalty_article"]').count(),3);
        await page.locator('#svg .node[data-type="penalty_article"]').first().click();
        assert.equal(await page.locator('#svg .node[data-type="penalty_year"]').count(),1);
        await page.locator('#svg .node[data-type="penalty_year"]').click();
        assert.equal(await page.locator('#svg .node[data-type="penalty_county"]').count(),1);
        await page.locator('#svg .node[data-type="penalty_county"]').click();
        assert.equal(await page.locator('#svg .node[data-type="penalty"]').count(),1);
        await page.locator('#svg .node[data-type="penalty"]').click();
        assert.equal(await page.locator('#nodeInfoBody a[href^="https://data.gov.tw/"]').count(),1);
        await assertLayout(page,'penalty law → article → year → county → record',{focused:true});
      }
      if (hubType === 'procurement' || hubType === 'judicial') {
        await page.locator(`#svg .node[data-type="${childType}"]`).first().click();
        const descendants = await page.evaluate(type => {
          const position = element => {
            const circle = element.querySelector('circle:not(.hit):not(.related-halo)');
            return { x: Number(circle.getAttribute('cx')), y: Number(circle.getAttribute('cy')) };
          };
          const parent = position(document.querySelector(`#svg .node[data-type="${type}"]`));
          const childType = type === 'judicial_year' ? 'judicial_month' : 'procurement_year';
          const points = [...document.querySelectorAll(`#svg .node[data-type="${childType}"]`)].map(position);
          const lines = [...document.querySelectorAll('#svg .graph-branch:not(.root-branch)')];
          return { parent, points, lines: lines.map(line => [line.getAttribute('y1'), line.getAttribute('y2')]) };
        }, childType);
        assert.equal(descendants.points.length, hubType === 'judicial' ? 3 : 2);
        assert.equal((descendants.points[0].y + descendants.points.at(-1).y) / 2, descendants.parent.y);
        assert(descendants.lines.every(([y1, y2]) => y1 === y2), 'Nested branches are horizontal');
        const nestedPitches=await page.locator('#svg .node.hub circle:not(.hit)').evaluateAll(circles=>
          circles.slice(1).map((circle,index)=>Number(circle.getAttribute('cy'))-Number(circles[index].getAttribute('cy'))));
        assert(nestedPitches.every(pitch=>pitch===nestedPitches[0]),
          `${hubType}: opening a year does not push other categories apart`);
        await assertLayout(page, `${hubType} nested`, { focused: true });
        await assertReadableBranch(page, hubType === 'judicial' ? 'judicial_month' : 'procurement_year', `${hubType} nested`);
        if (hubType === 'judicial') {
          const monthOrder=await page.locator('#svg .node[data-type="judicial_month"]').evaluateAll(items=>items.map(item=>item.dataset.groupKey));
          assert.deepEqual(monthOrder,['03','02','01'],'Judgment months are newest first inside their year');
          await page.locator('#svg .node[data-type="judicial_month"][data-group-key="01"]').click();
          await assertLayout(page,'judgment month expanded',{focused:true});
          await assertReadableBranch(page,'judicial','judgment month expanded');
          if (process.env.TEI_GRAPH_JUDICIAL_SCREENSHOT)
            await page.locator('.graph').screenshot({ path: process.env.TEI_GRAPH_JUDICIAL_SCREENSHOT });
          await page.locator('#svg .node[data-type="judicial"] circle:not(.hit)').first().click();
          assert.equal(await page.locator('#nodeInfoBody a[href^="https://judicial.gov.tw/"]').count(), 1);
          assert.match(await page.locator('#nodeInfoBody').textContent(),/2026-01-28/,
            'Judgments within a month appear newest first');
          const seen = new Set();
          for (let pageNumber = 0; pageNumber < 7; pageNumber++) {
            const ids = await page.locator('#svg .node[data-type="judicial"]').evaluateAll(elements => elements.map(element => element.dataset.nodeId));
            assert.equal(ids.length, pageNumber === 6 ? 1 : 8);
            ids.forEach(id => seen.add(id));
            if (pageNumber < 6) await page.locator('#graphNext').click();
          }
          assert.equal(seen.size, 49, 'Every judgment remains reachable without showing all 49 at once');
        }
        if (hubType === 'procurement' && process.env.TEI_GRAPH_SCREENSHOT)
          await page.locator('.graph').screenshot({ path: process.env.TEI_GRAPH_SCREENSHOT });
        if (hubType === 'procurement') {
          const labels=await page.locator('#svg .node[data-type="procurement_year"]').evaluateAll(items=>items.map(item=>item.getAttribute('aria-label')));
          assert(labels.every(label=>!/(\d{4}).*\1/.test(label)),
            'Award year appears only once in each graph label');
        }
      }
      if (await page.locator('#closeNode').isVisible()) await page.locator('#closeNode').click();
    }
    for (const width of [1440, 1280, 1024, 768]) {
      await page.setViewportSize({ width, height: 900 });
      const graph = await page.locator('#svg').boundingBox();
      assert(graph && graph.width > 200 && graph.height > 200, `Graph visible at ${width}px`);
      assert.equal(await page.locator('#svg .node[data-type="procurement_year"]').count(), 2);
      await assertLayout(page, `${width}px`, { focused: true });
      await assertReadableBranch(page, 'procurement_year', `${width}px`);
      if (width===768 && process.env.TEI_GRAPH_NARROW_SCREENSHOT)
        await page.locator('.graph').screenshot({path:process.env.TEI_GRAPH_NARROW_SCREENSHOT});
    }
    await page.locator('#svg .node[data-type="procurement_city"]').first().click();
    await assertLayout(page,'768px with award details open', { focused: true });
    const narrowPanel = await page.evaluate(() => {
      const svg=document.querySelector('#svg').getBoundingClientRect(),info=document.querySelector('#nodeInfo').getBoundingClientRect();
      return {svgBottom:svg.bottom,infoTop:info.top};
    });
    assert(narrowPanel.svgBottom<narrowPanel.infoTop,'Narrow-screen details sit below the graph, not over its nodes');
    if (process.env.TEI_GRAPH_NARROW_DETAILS_SCREENSHOT)
      await page.locator('.graph').screenshot({path:process.env.TEI_GRAPH_NARROW_DETAILS_SCREENSHOT});
    assert.deepEqual(errors, []);
    console.log('All expanded graph categories, judgment years and award years align with horizontal branches.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
