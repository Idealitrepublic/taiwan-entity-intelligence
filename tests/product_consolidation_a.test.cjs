// Execute the shipped functions, not a copied implementation or token-only assertion.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('web/index.html', 'utf8');
function shipped(start, end) {
  const first = html.indexOf(start), last = html.indexOf(end, first);
  assert(first >= 0 && last > first, `Missing shipped function: ${start}`);
  return html.slice(first, last);
}
function oneLine(name) {
  const line = html.split('\n').find(row => row.trimStart().startsWith(`function ${name}(`));
  assert(line, `Missing ${name}`);
  return line;
}
function pathHarness() {
  const elements = Object.fromEntries(['pathFind','pathResult','pathDepth','pathSource','pathTarget'].map(id => [id, {value:'3',innerHTML:'',textContent:'',disabled:false}]));
  const requests = [], renders = [];
  const context = vm.createContext({AbortController,URLSearchParams,console,
    $:id=>elements[id],entityTypeLabels:{Company:'公司 / Company'},esc:String,
    renderPathResult:data=>renders.push(data),setTimeout:()=>1,clearTimeout:()=>{},
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  vm.runInContext(`let pathRequestSerial=0,pathRequestController=null,pathLoading=false;
    let pathSelection={source:{id:'A',display_name:'A',entity_type:'Company'},target:{id:'B',display_name:'B',entity_type:'Company'}};
    ${oneLine('invalidatePathRequest')}
    ${oneLine('renderPathSelection')}
    ${oneLine('setPathEndpoint')}
    ${shipped('  async function findRelationshipPath()', "  pathRange.addEventListener")}`,context);
  return {context,elements,requests,renders};
}
function reportHarness({popup=null,status=200,mime='application/pdf',bytes='%PDF-1.7 valid',modal=true}={}) {
  const events=[],requests=[],timers=[];
  const notice={appendChild:()=>events.push('append-active'),remove:()=>events.push('notice-remove')};
  const elements={workspaceDialog:{open:modal},workspaceMessage:notice};
  const link={remove:()=>events.push('remove'),click:()=>events.push('click')};
  const context=vm.createContext({AbortController,Blob,console,
    workspaceSession:{access_token:'test-session-only'},reportRequests:new Set(),$:id=>elements[id],
    workspaceAuthView:()=>events.push('signed-out'),workspaceMessage:message=>events.push(message),
    sessionStorage:{removeItem:()=>events.push('session-cleared')},
    window:{open:()=>popup},document:{createElement:tag=>tag==='a'?link:notice,querySelector:()=>({prepend:()=>events.push('prepend-notice')})},
    URL:{createObjectURL:()=>{events.push('object-url');return 'blob:test'},revokeObjectURL:()=>events.push('revoke')},
    setTimeout:(callback,delay)=>{timers.push({callback,delay});return timers.length},clearTimeout:()=>{},setInterval:()=>1,clearInterval:()=>{},
    fetch:async(url,options)=>{requests.push({url,options});return {ok:status===200,status,
      headers:{get:()=>mime},blob:async()=>new Blob([bytes]),text:async()=>'<html>Report</html>',json:async()=>({error:'Denied'})}}});
  vm.runInContext(shipped('  async function exportReport(', '  function workspaceItemTarget'),context);
  return {context,events,requests,timers,link,elements};
}
const cases=[];
function test(name,run){cases.push({name,run})}
test('range remains 1/2/3, not an API semantic change',()=>{
  for(const [depth,label] of [[1,'直接關係 / Direct'],[2,'最多 1 個中介 / Up to 1 intermediary'],[3,'最多 2 個中介 / Up to 2 intermediaries']])
    assert(html.includes(`<option value="${depth}"${depth===3?' selected':''}>${label}</option>`));
  assert(!html.includes('max depth 3'));
});
test('stale response cannot overwrite changed endpoints',async()=>{
  const h=pathHarness(),pending=vm.runInContext('findRelationshipPath()',h.context);
  assert.equal(h.elements.pathFind.disabled,true);
  vm.runInContext("setPathEndpoint('target',{id:'C',display_name:'C',entity_type:'Company'})",h.context);
  assert(h.requests[0].options.signal.aborted);
  h.requests[0].resolve({ok:true,json:async()=>({data:{found:true,old:true}})});
  await pending;
  assert.equal(h.renders.length,0);
  assert.equal(h.elements.pathTarget.textContent,'C · 公司 / Company');
  assert.equal(h.elements.pathFind.disabled,false);
});
test('changing range clears stale result and retains selected endpoints',()=>{
  const h=pathHarness();h.elements.pathResult.innerHTML='old route';
  vm.runInContext('invalidatePathRequest();renderPathSelection()',h.context);
  assert.equal(h.elements.pathResult.innerHTML,'');
  assert.equal(h.elements.pathSource.textContent,'A · 公司 / Company');
});
test('each range uses its existing exact max_depth and renders response',async()=>{
  for(const depth of ['1','2','3']){
    const h=pathHarness();h.elements.pathDepth.value=depth;
    const pending=vm.runInContext('findRelationshipPath()',h.context);
    assert.equal(new URL(h.requests[0].url,'https://test.invalid').searchParams.get('max_depth'),depth);
    h.requests[0].resolve({ok:true,json:async()=>({data:{found:true,depth}})});
    await pending;assert.equal(h.renders[0].depth,depth);assert.equal(h.elements.pathFind.disabled,false);
  }
});
test('empty/truncated path does not claim absence of relationships',()=>{
  const h=pathHarness();h.context.num=Number;h.context.pathRangeLabels={};
  vm.runInContext(shipped('  function renderPathResult(', '  async function findRelationshipPath('),h.context);
  vm.runInContext('renderPathResult({found:false,truncated:true})',h.context);
  assert(h.elements.pathResult.innerHTML.includes('不代表兩者沒有任何關係'));
  assert(h.elements.pathResult.innerHTML.includes('High-degree nodes truncated'));
});
test('path API error reenables button without bogus result',async()=>{
  const h=pathHarness(),pending=vm.runInContext('findRelationshipPath()',h.context);
  h.requests[0].resolve({ok:false,json:async()=>({error:'Unavailable'})});await pending;
  assert(h.elements.pathResult.innerHTML.includes('Unavailable'));assert.equal(h.renders.length,0);
  assert.equal(h.elements.pathFind.disabled,false);
});
test('live-company path action requires published exact identifier, never names',()=>{
  const code=shipped('  async function loadLiveCompanyContributions(', '  function pathEntityActions(');
  assert(code.includes("item.match_type==='identifier_exact'&&item.public_identifier===uniform&&!item.is_live_fallback"));
  assert(code.includes('pathEntityActions({id:match.entity_id'));
  assert(code.includes('serial!==companyRequestSerial'));
});
test('initial lazy load does not open an overlay that blocks node/edge pointer targets',async()=>{
  const node={id:'A',depth:0},state={nodes:new Map([['A',node]]),loading:new Set(),expanded:new Set(),hasMore:new Map(),cursors:new Map(),edges:new Map()};
  const shown=[],context=vm.createContext({knowledgeGraph:state,selectedNodeId:null,
    GRAPH_MAX_NODES:60,GRAPH_PAGE_SIZE:12,URLSearchParams,
    graphDepthLimit:()=>3,$:()=>({value:'',textContent:''}),renderKnowledgeGraph:()=>{},showKnowledgeNode:node=>shown.push(node.id),
    fetch:async()=>({ok:true,json:async()=>({data:{nodes:[node],edges:[],has_more:false}})})});
  const line=html.split('\n').find(row=>row.trimStart().startsWith('async function expandKnowledgeNode('));
  assert(line);vm.runInContext(line,context);
  await vm.runInContext("expandKnowledgeNode('A')",context);
  assert.equal(shown.length,0);
  state.expanded.clear();context.selectedNodeId='A';
  await vm.runInContext("expandKnowledgeNode('A')",context);
  assert.deepEqual(shown,['A']);
});
test('PDF download remains inside active modal, with visible retry and no navigation',async()=>{
  const h=reportHarness();await vm.runInContext("exportReport('workspace','id',true)",h.context);
  assert.equal(h.requests[0].options.headers.Authorization,'Bearer test-session-only');
  assert(h.requests[0].url.endsWith('?format=pdf'));
  assert.equal(h.link.download,'tei-workspace-id.pdf');
  assert(h.events.includes('append-active'));assert(h.events.includes('click'));
  assert.equal(h.events.includes('remove'),false);
  assert.equal(h.link.textContent,'儲存 PDF / Save PDF');
  assert(h.timers.some(timer=>timer.delay===600000));
  assert.equal(h.events.includes('revoke'),false);
});
test('public report keeps an accessible retry without opening the private dashboard',async()=>{
  const h=reportHarness({modal:false});await vm.runInContext("exportReport('entity','id',true)",h.context);
  assert(h.events.includes('prepend-notice'));assert(h.events.includes('append-active'));
  assert(!h.requests[0].options.headers.Authorization);
});
test('HTML instead of PDF and bogus PDF both reject without download',async()=>{
  for(const params of [{mime:'text/html'},{bytes:'not a PDF'}]){
    const h=reportHarness(params);
    await assert.rejects(vm.runInContext("exportReport('entity','id',true)",h.context));
    assert.equal(h.events.includes('click'),false);
  }
});
test('blocked pop-up has readable error, no fetch or main-window close',async()=>{
  const h=reportHarness();await assert.rejects(vm.runInContext("exportReport('entity','id',false)",h.context),/Allow report pop-ups/);
  assert.equal(h.requests.length,0);
});
test('expired Workspace auth is cleared; no private download',async()=>{
  const h=reportHarness({status:401});
  await assert.rejects(vm.runInContext("exportReport('workspace','id',true)",h.context));
  assert(h.events.includes('session-cleared'));assert(h.events.includes('signed-out'));
  assert.equal(h.events.includes('click'),false);
});
test('report preview navigation affects new window only',async()=>{
  const popup={closed:false,location:'about:blank',close(){this.closed=true}},h=reportHarness({popup});
  await vm.runInContext("exportReport('entity','id',false)",h.context);
  assert(h.requests[0].url.endsWith('?format=html'));
  assert.equal(popup.location,'blob:test');assert.equal(popup.opener,null);assert.equal(popup.closed,false);
});
(async()=>{for(const {name,run} of cases){await run();console.log(`PASS ${name}`)}console.log(`${cases.length} browser-function regression cases passed (not real-browser acceptance).`)})().catch(error=>{console.error(error);process.exitCode=1});
