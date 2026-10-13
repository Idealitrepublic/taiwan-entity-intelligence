const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('web/index.html', 'utf8');
function shipped(start, end) {
  const first = html.indexOf(start), last = html.indexOf(end, first);
  assert(first >= 0 && last > first, `Missing shipped code: ${start}`);
  return html.slice(first, last);
}
function test(name, run) {
  Promise.resolve().then(run).then(() => console.log(`PASS ${name}`), error => {
    console.error(`FAIL ${name}`, error);
    process.exitCode = 1;
  });
}

const registry = vm.createContext({esc: value => String(value)});
vm.runInContext(shipped('  function formatRegistryAmount(', '  function companyOverview('), registry);
test('registry amounts preserve decimals and group thousands without floating-point conversion', () => {
  assert.equal(vm.runInContext("formatRegistryAmount('120000000000.50')", registry), 'NT$ 120,000,000,000.50');
  assert.equal(vm.runInContext("formatRegistryAmount('9007199254740993')", registry), 'NT$ 9,007,199,254,740,993');
  assert.equal(vm.runInContext("formatRegistryAmount('')", registry), '—');
});
test('company profile translates official fields once and keeps capital distinctions', () => {
  const fields = vm.runInContext(`companyRegistryFields(
    {uniform_number:'96979933'},
    {Company_Status_Desc:'核准設立',Responsible_Name:'代表',Company_Location:'臺北',
     Capital_Stock_Amount:'1000000',Paid_In_Capital_Amount:'500000',
     Register_Organization_Desc:'臺北市政府'})`, registry);
  assert.equal((fields.match(/公司狀態 \/ Status/g) || []).length, 1);
  assert(fields.includes('NT$ 1,000,000'));
  assert(fields.includes('NT$ 500,000'));
  assert(fields.includes('登記機關 / Registry authority'));
  assert(!fields.includes('Capital_Stock_Amount'));
  assert(!shipped('  function companyOverview(', '  function renderRecordPanes(').includes('rawGrid(company)'));
});
test('narrow path controls can shrink inside the mobile viewport', () => {
  assert(html.includes('.path-controls{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)'));
  assert(html.includes('.path-controls select,.path-controls button{min-width:0;width:100%'));
});
test('path match context replaces technical politician keys with a readable term', () => {
  const label = vm.runInContext("pathContextLabel('term:11;session:5;co_chair:N · 內政委員會')", pathHarness({}).context);
  assert.equal(label,'第 11 屆 · 第 5 會期 · 內政委員會');
  assert(!label.includes('co_chair'));
});

function pathHarness(response) {
  const elements = {
    pathSourceMatches: {hidden:true,innerHTML:''},
    pathTargetMatches: {hidden:true,innerHTML:''},
    pathResult: {innerHTML:''},
    pathFind: {textContent:'',disabled:true},
    pathSource: {textContent:''},
    pathTarget: {textContent:''},
  };
  const context = vm.createContext({
    AbortController, URLSearchParams, console,
    $: id => elements[id], esc: value => String(value),
    entityTypeLabels: {Company:'公司 / Company'},
    clearTimeout: () => {},
    fetch: async (url, options) => {context.lastRequest = {url,options};return response},
  });
  vm.runInContext(`let pathRequestSerial=0,pathRequestController=null,pathLoading=false;
    let pathSelection={source:null,target:null};
    ${shipped('  function invalidatePathRequest()', '  function renderPathResult(').replace(/  for\(const role of\['source','target'\]\)[\s\S]*$/, '')}`, context);
  return {context,elements};
}
test('path endpoint search selects only published canonical entities', async () => {
  const h = pathHarness({ok:true,json:async()=>({data:{items:[
    {entity_id:'canonical',display_name:'已發布公司',entity_type:'Company',context_label:'官方識別'},
    {entity_id:'live',display_name:'即時資料',entity_type:'Company',is_live_fallback:true},
  ]}})});
  await vm.runInContext("searchPathEndpoint('source','中華電信')", h.context);
  assert.equal(vm.runInContext('pathSearchState.source.items.size', h.context), 1);
  assert(h.elements.pathSourceMatches.innerHTML.includes('已發布公司'));
  assert(h.elements.pathSourceMatches.innerHTML.includes('官方識別'));
  assert(!h.elements.pathSourceMatches.innerHTML.includes('即時資料'));
  assert.equal(new URL(h.context.lastRequest.url,'https://test.invalid').searchParams.get('limit'),'12');
  vm.runInContext("setPathEndpoint('source',{id:'live',is_live_fallback:true})", h.context);
  assert.equal(h.elements.pathSource.textContent,'');
});
test('path endpoint search reports no canonical match without claiming no live company', async () => {
  const h = pathHarness({ok:true,json:async()=>({data:{items:[{entity_id:'live',is_live_fallback:true}]}})});
  await vm.runInContext("searchPathEndpoint('target','中華電信')", h.context);
  assert(h.elements.pathTargetMatches.innerHTML.includes('即時公司資料'));
  assert.equal(h.elements.pathTargetMatches.hidden,false);
});
