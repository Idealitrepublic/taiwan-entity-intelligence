/** Browser regression: NODE_PATH=<playwright modules> node tests/graph_expanded_hubs_browser.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const company = 'company:22099131';
const nodes = [
  { id: company, type: 'company', label: '測試公司／Test Company with longer name' },
  ...['甲', '乙', '丙'].map((name, index) => ({ id: `person:${index}`, type: 'person', label: `董事${name}／Director with long English name ${index}`, properties: { position: '董事' } })),
  ...['第24條', '第32條', '第36條'].map((law, index) => ({ id: `penalty:${index}`, type: 'penalty', label: `勞動基準法${law}：出勤與工資紀錄`, properties: { date: `2025-0${index + 1}-01`, fine: '10000' } })),
  ...Array.from({ length: 50 }, (_, index) => ({ id: `judicial:${index}`, type: 'judicial', label: `裁判 ${index + 1}／Court decision concerning extended public source record`, properties: { date: `${index < 49 ? 2026 : 2025}-01-01`, jid: `J-${index}`, source_url: 'https://judicial.gov.tw/record' } })),
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
async function assertLayout(page, label) {
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
  assert.deepEqual(result.clipped,[],`${label}: all labels stay inside graph viewport`);
  assert.deepEqual(result.ellipses,[],`${label}: no label truncation`);
  assert.deepEqual(result.covered,[],`${label}: detail panel does not cover nodes or labels`);
  return result;
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
        ].map((company_name,index)=>({uniform_number:`2209914${index}`,company_name,connection_type:'same_award_notice',connection_label:'共同標案',evidence:{source_url:'https://example.gov.tw/award',source_name:'測試來源'}})) } : {};
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
    assert(Math.abs(anchors.center.y-(hubYs[0]+hubYs.at(-1))/2)<.01, 'Company root is centered on category column');
    assert(steps.every(step=>Math.abs(step-steps[0])<.01), 'Connected companies and awards match all category spacing');
    await assertLayout(page, 'collapsed category layout');
    await page.locator('#svg .node[data-hub="related"]').click();
    const cases = [
      ['related', 'related_company', 2], ['person', 'person', 3], ['penalty', 'law_group', 3], ['judicial', 'judicial_year', 2], ['procurement', 'procurement_city', 2]
    ];
    for (const [hubType, childType, count] of cases) {
      if (hubType !== 'related') await page.locator(`#svg .node[data-hub="${hubType}"]`).click();
      const layout = await page.evaluate(({ hubType, childType }) => {
        const position = element => {
          const circle = element.querySelector('circle:not(.hit):not(.related-halo)');
          return { x: Number(circle.getAttribute('cx')), y: Number(circle.getAttribute('cy')) };
        };
        const hub = position(document.querySelector(`#svg .node[data-hub="${hubType}"]`));
        const children = [...document.querySelectorAll(`#svg .node[data-type="${childType}"]`)].map(position);
        const branches = [...document.querySelectorAll('#svg .graph-branch')].map(line => ({
          x1: Number(line.getAttribute('x1')), y1: Number(line.getAttribute('y1')),
          x2: Number(line.getAttribute('x2')), y2: Number(line.getAttribute('y2'))
        }));
        const spine = document.querySelector('#svg .graph-spine')?.getAttribute('d');
        return { hub, children, branches, spine };
      }, { hubType, childType });
      assert.equal(layout.children.length, count, `${hubType} keeps every source-backed node`);
      assert.equal((layout.children[0].y + layout.children.at(-1).y) / 2, layout.hub.y,
        `${hubType} children align with their parent`);
      assert(layout.children.every(point => point.x === layout.children[0].x), `${hubType} shares an aligned lane`);
      assert.equal(layout.branches.length, count);
      assert(layout.branches.every(branch => branch.y1 === branch.y2 && branch.x2 > branch.x1),
        `${hubType} branches are horizontal`);
      assert(layout.spine && layout.spine.includes(`${layout.hub.y}`), `${hubType} has a parent rail`);
      const column = await page.evaluate(() => {
        const position = element => {const circle=element.querySelector('circle:not(.hit)');return{x:Number(circle.getAttribute('cx')),y:Number(circle.getAttribute('cy'))}};
        return {root:position(document.querySelector('#svg .node[data-type="company"]')),
          hubs:[...document.querySelectorAll('#svg .node.hub')].map(position)};
      });
      assert(column.hubs.every(point=>point.x===column.hubs[0].x),`${hubType}: category hubs stay in one column`);
      assert(Math.abs(column.root.y-(column.hubs[0].y+column.hubs.at(-1).y)/2)<.01,
        `${hubType}: root stays centered between connected companies and awards`);
      await assertLayout(page, `${hubType} expanded`);
      if (hubType === 'related' && process.env.TEI_GRAPH_RELATED_SCREENSHOT)
        await page.locator('.graph').screenshot({ path: process.env.TEI_GRAPH_RELATED_SCREENSHOT });
      if (hubType === 'procurement' || hubType === 'judicial') {
        await page.locator(`#svg .node[data-type="${childType}"]`).first().click();
        const descendants = await page.evaluate(type => {
          const position = element => {
            const circle = element.querySelector('circle:not(.hit):not(.related-halo)');
            return { x: Number(circle.getAttribute('cx')), y: Number(circle.getAttribute('cy')) };
          };
          const parent = position(document.querySelector(`#svg .node[data-type="${type}"]`));
          const childType = type === 'judicial_year' ? 'judicial' : 'procurement_year';
          const points = [...document.querySelectorAll(`#svg .node[data-type="${childType}"]`)].map(position);
          const lines = [...document.querySelectorAll('#svg .graph-branch')].filter(line => Number(line.getAttribute('x1')) === 740);
          return { parent, points, lines: lines.map(line => [line.getAttribute('y1'), line.getAttribute('y2')]) };
        }, childType);
        assert.equal(descendants.points.length, hubType === 'judicial' ? 8 : 2);
        assert.equal((descendants.points[0].y + descendants.points.at(-1).y) / 2, descendants.parent.y);
        assert(descendants.lines.every(([y1, y2]) => y1 === y2), 'Nested branches are horizontal');
        await assertLayout(page, `${hubType} nested`);
        if (hubType === 'judicial') {
          if (process.env.TEI_GRAPH_JUDICIAL_SCREENSHOT)
            await page.locator('.graph').screenshot({ path: process.env.TEI_GRAPH_JUDICIAL_SCREENSHOT });
          await page.locator('#svg .node[data-type="judicial"] circle:not(.hit)').first().click();
          assert.equal(await page.locator('#nodeInfoBody a[href^="https://judicial.gov.tw/"]').count(), 1);
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
      }
      if (await page.locator('#closeNode').isVisible()) await page.locator('#closeNode').click();
    }
    for (const width of [1440, 1280, 1024, 768]) {
      await page.setViewportSize({ width, height: 900 });
      const graph = await page.locator('#svg').boundingBox();
      assert(graph && graph.width > 200 && graph.height > 200, `Graph visible at ${width}px`);
      assert.equal(await page.locator('#svg .node[data-type="procurement_year"]').count(), 2);
      await assertLayout(page, `${width}px`);
      if (width===768 && process.env.TEI_GRAPH_NARROW_SCREENSHOT)
        await page.locator('.graph').screenshot({path:process.env.TEI_GRAPH_NARROW_SCREENSHOT});
    }
    await page.locator('#svg .node[data-type="procurement_city"]').first().click();
    await assertLayout(page,'768px with award details open');
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
