const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('web/index.html', 'utf8');
function shipped(start, end) {
  const first = html.indexOf(start), last = html.indexOf(end, first);
  assert(first >= 0 && last > first, `Missing shipped function: ${start}`);
  return html.slice(first, last);
}
function line(name) {
  const result = html.split('\n').find(row => row.trimStart().startsWith(`function ${name}(`));
  assert(result, `Missing shipped function: ${name}`);
  return result;
}
const A = {id:'a',display_name:'Company A',entity_type:'Company'};
const B = {id:'b',display_name:'Company B',entity_type:'Company'};
const shared = {id:'shared',display_name:'Officially identified agency',entity_type:'GovernmentAgency'};
function segment(from, to, id, reverse=false) {
  return {from_entity:from,to_entity:to,traversal_direction:reverse?'reverse':'forward',
    relationship:{id,source_entity_id:reverse?to.id:from.id,
      target_entity_id:reverse?from.id:to.id,relationship_type:'CONTRACT_WITH',
      primary_evidence_id:`e-${id}`},
    evidence:{id:`e-${id}`,source_name:'Official source',
      source_url:`https://example.gov.tw/${id}`,retrieved_at:'2026-10-14T00:00:00Z'}};
}
function path(segments) {
  return {found:true,depth:segments.length,source_entity:A,target_entity:B,
    max_depth:3,shared_node_complete:true,segments};
}
function harness() {
  const elements = Object.fromEntries(['svg','graphEmpty','graphTitle','graphSub','collapse',
    'nodeInfo','relationshipFilter','pathResult'].map(id => [id,{dataset:{},textContent:'',hidden:false,
      innerHTML:'',replaceChildren(){this.children=[]}}]));
  const calls = [];
  const context = vm.createContext({$:id=>elements[id],hopLimit:{hidden:false},
    pathSelection:{source:A,target:B},graphMode:'legacy',knowledgeGraph:null,
    selectedNodeId:null,selectedEdgeId:null,
    renderKnowledgeGraph:()=>calls.push('render'),resetGraphView:()=>calls.push('fit')});
  vm.runInContext(`${line('createKnowledgeGraph')}\n${shipped('  function renderPathGraph(', '  async function findRelationshipPath(')}`,context);
  return {elements,calls,context};
}
function test(name, run) {
  try { run(); console.log(`PASS ${name}`); }
  catch (error) { console.error(`FAIL ${name}`,error); process.exitCode = 1; }
}

test('shared canonical node renders Company A → agency → Company B with clickable evidence edges',()=>{
  const h=harness();
  assert.equal(vm.runInContext('renderPathGraph(data)',Object.assign(h.context,
    {data:path([segment(A,shared,'r1'),segment(shared,B,'r2',true)])})),true);
  assert.equal(h.context.graphMode,'path');
  assert.equal(h.context.knowledgeGraph.nodes.size,3);
  assert.equal(h.context.knowledgeGraph.edges.size,2);
  assert.equal(h.context.knowledgeGraph.edges.get('r2').source,'b');
  assert.equal(h.context.knowledgeGraph.edges.get('r2').primary_evidence.source_name,'Official source');
  assert.equal(h.context.knowledgeGraph.expanded.size,3);
  assert.equal(h.elements.svg.dataset.pathGraph,'true');
  assert.equal(h.elements.graphTitle.textContent,'Company A ↔ Company B');
  assert.deepEqual(h.calls,['render','fit']);
  assert(html.includes('showKnowledgeEdge(edge)'));
});
test('different IDs with the same name never become a shared node',()=>{
  const h=harness(),lookalike={...shared,id:'other-shared'};
  const invalid=path([segment(A,shared,'r1'),segment(lookalike,B,'r2')]);
  assert.equal(vm.runInContext('renderPathGraph(data)',Object.assign(h.context,{data:invalid})),false);
  assert.equal(h.context.graphMode,'legacy');
  assert.equal(h.calls.length,0);
});
test('missing evidence, wrong endpoint or cyclic path never draws a graph',()=>{
  for(const data of [
    path([segment(A,shared,'r1'),{...segment(shared,B,'r2'),evidence:null}]),
    {...path([segment(A,B,'r1')]),target_entity:{...B,id:'wrong'}},
    {...path([segment(A,shared,'r1'),segment(shared,A,'r2'),segment(A,B,'r3')]),depth:3},
  ]) {
    const h=harness();
    assert.equal(vm.runInContext('renderPathGraph(data)',Object.assign(h.context,{data})),false);
    assert.equal(h.calls.length,0);
  }
});
test('path node positions honor actual segment count even when ordinary graph hop filter is one',()=>{
  const context=vm.createContext({graphMode:'path',knowledgeGraph:{manualPositions:new Map()},
    graphDepthLimit:()=>1,num:Number,graphContext:null,entityTypeLabels:{Company:'公司 / Company'}});
  vm.runInContext(shipped('  function graphTextWidth(', '  function createKnowledgeGraph(')+
    shipped('  function knowledgeMetrics(', '  function showKnowledgeNode('),context);
  const positions=vm.runInContext('knowledgePositions(nodes)',Object.assign(context,
    {nodes:[{id:'a',depth:0,entity_type:'Company',display_name:'Company A'},
      {id:'shared',depth:1,entity_type:'GovernmentAgency',display_name:'Officially identified agency'},
      {id:'b',depth:2,entity_type:'Company',display_name:'Company B'}]}));
  assert.equal(positions.size,3);
  assert(positions.get('a').x<positions.get('shared').x);
  assert(positions.get('shared').x<positions.get('b').x);
  assert(positions.get('shared').x-positions.get('a').x>100);
});
test('path range request invokes company-only finder and result is wired into graph renderer',()=>{
  assert(html.includes("company_only:'1'"));
  assert(html.includes('if(!renderPathGraph(data))'));
  assert(html.includes('共用節點已完整比對'));
  assert(html.includes('.graph svg[data-path-graph="true"] .edge'));
});
