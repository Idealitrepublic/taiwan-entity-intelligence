/** Browser regression: NODE_PATH=<playwright modules> node tests/graph_expanded_hubs_browser.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const company = 'company:22099131';
const nodes = [
  { id: company, type: 'company', label: '測試公司' },
  ...['甲', '乙', '丙'].map((name, index) => ({ id: `person:${index}`, type: 'person', label: `董事${name}`, properties: { position: '董事' } })),
  ...['第24條', '第32條', '第36條'].map((law, index) => ({ id: `penalty:${index}`, type: 'penalty', label: `勞動基準法${law}`, properties: { date: `2025-0${index + 1}-01`, fine: '10000' } })),
  ...Array.from({ length: 50 }, (_, index) => ({ id: `judicial:${index}`, type: 'judicial', label: `裁判 ${index + 1}`, properties: { date: `${2025 - Math.floor(index / 5)}-01-01`, jid: `J-${index}`, source_url: 'https://judicial.gov.tw/record' } }))
];
const awards = [
  { id: 'a', title: '臺北市採購案一', agency: '臺北市政府', date: '2025-01-01' },
  { id: 'b', title: '臺北市採購案二', agency: '臺北市政府', date: '2024-01-01' },
  { id: 'c', title: '臺中市採購案', agency: '臺中市政府', date: '2025-01-01' }
];
const body = { status: 'ok', uniform_number: '22099131', company_name: '測試公司', company: {}, people: [],
  graph: { nodes, edges: [] }, evidence: [], labor_penalties: [], judicial_result: { records: [], matched: 0 }, evidence_status: {} };

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
        : path === '/api/company-related/22099131' ? { status: 'ok', uniform_number: '22099131', items: [] } : {};
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(result) });
    });
    await page.goto('https://tei.local/');
    await page.locator('#q').fill('22099131');
    await page.locator('#search').click();
    await page.locator('#svg .node[data-hub="procurement"]').waitFor();
    const cases = [
      ['person', 'person', 3], ['penalty', 'law_group', 3], ['judicial', 'judicial_year', 10], ['procurement', 'procurement_city', 2]
    ];
    for (const [hubType, childType, count] of cases) {
      await page.locator(`#svg .node[data-hub="${hubType}"]`).click();
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
        assert.equal(descendants.points.length, hubType === 'judicial' ? 5 : 2);
        assert.equal((descendants.points[0].y + descendants.points.at(-1).y) / 2, descendants.parent.y);
        assert(descendants.lines.every(([y1, y2]) => y1 === y2), 'Nested branches are horizontal');
        if (hubType === 'judicial') {
          if (process.env.TEI_GRAPH_JUDICIAL_SCREENSHOT)
            await page.locator('.graph').screenshot({ path: process.env.TEI_GRAPH_JUDICIAL_SCREENSHOT });
          await page.locator('#svg .node[data-type="judicial"]').first().click();
          assert.equal(await page.locator('#nodeInfoBody a[href^="https://judicial.gov.tw/"]').count(), 1);
        }
        if (hubType === 'procurement' && process.env.TEI_GRAPH_SCREENSHOT)
          await page.locator('.graph').screenshot({ path: process.env.TEI_GRAPH_SCREENSHOT });
      }
      await page.locator('#closeNode').click();
    }
    for (const width of [1440, 1280, 1024, 768]) {
      await page.setViewportSize({ width, height: 900 });
      const graph = await page.locator('#svg').boundingBox();
      assert(graph && graph.width > 200 && graph.height > 200, `Graph visible at ${width}px`);
      assert.equal(await page.locator('#svg .node[data-type="procurement_year"]').count(), 2);
    }
    assert.deepEqual(errors, []);
    console.log('All expanded graph categories, judgment years and award years align with horizontal branches.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
