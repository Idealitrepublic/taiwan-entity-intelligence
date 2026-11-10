/** Browser regression: NODE_PATH=<playwright modules> node tests/graph_continuous_browser.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

const html = fs.readFileSync('web/index.html', 'utf8');
const nodes = Array.from({length: 79}, (_, index) => ({
  id: `11111111-1111-4111-8111-${String(index).padStart(12, '0')}`,
  entity_type: 'GovernmentAgency', display_name: `公開資料單位 ${index}`
}));
const edge = (from, to) => ({
  id: `link-${from}-${to}`, source: nodes[from].id, target: nodes[to].id,
  relationship_type: 'MEMBER_OF', primary_evidence: {
    id: `proof-${from}-${to}`, source_record_id: `record-${from}-${to}`,
    source_name: '公開資料測試來源', source_url: 'https://example.gov.tw/record'
  }
});

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.TEI_BROWSER_PATH ||
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 900}});
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://tei.local/**', route => {
      const url = new URL(route.request().url());
      if (url.pathname.startsWith('/graph/')) return route.fulfill({contentType: 'text/html', body: html});
      let data = {};
      if (url.pathname.startsWith('/api/v1/entities/')) data = nodes[0];
      if (url.pathname.startsWith('/api/v1/graph/')) {
        const index = nodes.findIndex(node => url.pathname.endsWith(node.id));
        const cursor = url.searchParams.get('after');
        assert.equal(url.searchParams.get('limit'), '12');
        requests.push([index, cursor]);
        const links = index === 66 && !cursor ? nodes.slice(67).map((_, offset) => edge(66, 67 + offset))
          : index === 66 ? [edge(66, 0)] // A later page links back to the original root.
          : index < 66 ? [edge(index, index + 1)] : [];
        data = {nodes: [nodes[index], ...links.map(link => nodes.find(node => node.id === link.target))],
          edges: links, has_more: index === 66 && !cursor, next_cursor: index === 66 && !cursor ? links.at(-1).id : null};
      }
      return route.fulfill({json: {data}});
    });
    const graphNode = index => page.locator(`#svg .node[data-node-id="${nodes[index].id}"]`);
    const clickNode = index => graphNode(index).locator('circle:not(.hit)').click({timeout: 6000});
    await page.goto(`https://tei.local/graph/${nodes[0].id}`);
    await graphNode(1).waitFor();
    assert.equal(await page.locator('#hopLimit').inputValue(), '');
    for (let index = 1; index <= 66; index++) {
      await clickNode(index);
      await graphNode(index + 1).waitFor();
    }
    await graphNode(78).waitFor();
    assert.equal(await page.locator('#svg .node').count(), 79);
    assert.match(await page.locator('#graphSub').textContent(), /再點載入下一頁/);
    await clickNode(66);
    await page.locator('#svg .edge-group[data-edge-id="link-66-0"]').waitFor({state: 'attached'});
    assert.equal(await graphNode(0).count(), 1);
    assert.deepEqual(requests.slice(-2), [[66, null], [66, 'link-66-78']]);
    const count = requests.length;
    await clickNode(66);
    assert.equal(requests.length, count);
    await page.locator('#svg .edge-group[data-edge-id="link-66-0"]').dispatchEvent('click');
    assert.match(await page.locator('#nodeInfoBody').textContent(), /record-66-0/);
    await page.locator('#hopLimit').selectOption('1');
    await graphNode(1).waitFor();
    await clickNode(1);
    assert.match(await page.locator('#graphSub').textContent(), /已達所選層數/);
    assert.equal(await page.locator('#svg .node').count(), 2);
    assert.deepEqual(errors, []);
    console.log('PASS browser: 66 manual layers, 79 nodes, next-page cycle, evidence and optional depth filter');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1 });
