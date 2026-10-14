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
  registry.websiteCard=()=>'';
  vm.runInContext(shipped('  function companyOverview(', '  function renderRecordPanes('),registry);
  const overview=vm.runInContext("companyOverview({company_name:'測試公司',uniform_number:'96979933'},{Company_Status_Desc:'核准設立'},[],null,false)",registry);
  assert.equal((overview.match(/測試公司/g)||[]).length,1);
  assert.equal((overview.match(/96979933/g)||[]).length,1);
  assert(!overview.includes('企業 / Company · 96979933'));
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
test('path action buttons appear for published companies only; reports stay available', () => {
  const context = vm.createContext({esc: value => String(value)});
  vm.runInContext(shipped('  function pathEntityActions(', '  let pathRequestSerial='), context);
  const company = vm.runInContext("pathEntityActions({id:'c',entity_type:'Company',display_name:'公司'})", context);
  const politician = vm.runInContext("pathEntityActions({id:'p',entity_type:'Politician',display_name:'立委'})", context);
  assert(company.includes('設為公司 A / Company A'));
  assert(company.includes('設為公司 B / Company B'));
  assert(!politician.includes('path-select'));
  assert(politician.includes('閱讀報告'));
  const live = vm.runInContext("pathEntityActions({id:'l',entity_type:'Company',display_name:'即時公司',public_identifier:'96979933',is_live_fallback:true})", context);
  assert(live.includes('data-path-uniform="96979933"'));
  assert(!live.includes('report-export'));
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
    entityTypeLabels: {Company:'公司 / Company'},graphMode:'legacy',
    clearTimeout: () => {}, clearPathGraph: () => {},
    fetch: async (url, options) => {context.lastRequest = {url,options};return response},
  });
  vm.runInContext(`let pathRequestSerial=0,pathRequestController=null,pathLoading=false;
    let pathSelection={source:null,target:null};
    ${shipped('  function invalidatePathRequest()', '  function renderPathResult(').replace(/  for\(const role of\['source','target'\]\)[\s\S]*$/, '')}`, context);
  return {context,elements};
}
test('path endpoint search accepts exact-ID live registry companies but not people', async () => {
  const h = pathHarness({ok:true,json:async()=>({data:{items:[
    {entity_id:'canonical',display_name:'已發布公司',entity_type:'Company',context_label:'官方識別'},
    {entity_id:'live',display_name:'即時資料',entity_type:'Company',public_identifier:'96979933',is_live_fallback:true},
    {entity_id:'politician',display_name:'政治人物',entity_type:'Politician'},
  ]}})});
  await vm.runInContext("searchPathEndpoint('source','中華電信')", h.context);
  assert.equal(vm.runInContext('pathSearchState.source.items.size', h.context), 2);
  assert(h.elements.pathSourceMatches.innerHTML.includes('已發布公司'));
  assert(h.elements.pathSourceMatches.innerHTML.includes('官方識別'));
  assert(h.elements.pathSourceMatches.innerHTML.includes('即時資料'));
  assert(!h.elements.pathSourceMatches.innerHTML.includes('政治人物'));
  assert.equal(new URL(h.context.lastRequest.url,'https://test.invalid').searchParams.get('limit'),'12');
  assert.equal(new URL(h.context.lastRequest.url,'https://test.invalid').searchParams.get('entity_type'),'Company');
  vm.runInContext("setPathEndpoint('source',{id:'live',display_name:'即時資料',entity_type:'Company',public_identifier:'96979933',is_live_fallback:true})", h.context);
  assert(h.elements.pathSource.textContent.includes('即時資料'));
  assert(h.elements.pathSource.textContent.includes('即時登記'));
  vm.runInContext("setPathEndpoint('source',{id:'politician',entity_type:'Politician'})", h.context);
  assert(h.elements.pathSource.textContent.includes('即時資料'));
});
test('path endpoint search rejects live company without verified eight-digit identifier', async () => {
  const h = pathHarness({ok:true,json:async()=>({data:{items:[{entity_id:'live',is_live_fallback:true}]}})});
  await vm.runInContext("searchPathEndpoint('target','中華電信')", h.context);
  assert(h.elements.pathTargetMatches.innerHTML.includes('查無可選公司'));
  assert.equal(h.elements.pathTargetMatches.hidden,false);
});
test('company match does not repeat the same official identifier in context', async () => {
  const h = pathHarness({ok:true,json:async()=>({data:{items:[{
    entity_id:'company-id',display_name:'測試公司',entity_type:'Company',
    public_identifier:'04690983',context_label:'統一編號 / Company ID 04690983',
  }]}})});
  await vm.runInContext("searchPathEndpoint('source','04690983')", h.context);
  assert.equal((h.elements.pathSourceMatches.innerHTML.match(/04690983/g)||[]).length,1);
});
test('live shared-record result shows provenance without broken unpublished Entity links', () => {
  const elements={pathResult:{innerHTML:''}};
  const context=vm.createContext({$:id=>elements[id],esc:value=>String(value),
    num:Number,pathRangeLabels:{2:'最多 1 個中介'},relationshipLabels:{CONTRACT_WITH:'政府標案'},
    safeSourceUrl:value=>value||'',renderPathGraph:()=>true});
  vm.runInContext(shipped('  function renderPathResult(', '  function renderPathGraph('),context);
  vm.runInContext(`renderPathResult({found:true,backend:'live_verified_shared_records',
    depth:2,max_depth:2,interpretation:'不代表兩家公司有股權關係',coverage_note:'僅第一頁',
    segments:[{from_entity:{id:'a',display_name:'甲'},to_entity:{id:'g',display_name:'機關'},
      relationship:{relationship_type:'CONTRACT_WITH',start_date:'2026-01-01'},
      evidence:{id:'e',title:'公告',source_name:'政府來源',source_record_id:'case',
        source_url:'https://example.gov.tw/case',retrieved_at:'2026-10-15'}}]})`,context);
  const output=elements.pathResult.innerHTML;
  assert(output.includes('可驗證共用紀錄路徑'));
  assert(output.includes('不代表兩家公司有股權關係'));
  assert(output.includes('https://example.gov.tw/case'));
  assert(!output.includes('/entity/a'));
  assert(!output.includes('No published records'));
});
