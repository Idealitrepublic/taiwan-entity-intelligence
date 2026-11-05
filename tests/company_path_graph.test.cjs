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

function pointerHarness(targetClass, mode='legacy') {
  const registered=html.split('\n').find(row=>row.trimStart().startsWith("graphSvg.addEventListener('pointerdown',"));
  assert(registered, 'Missing shipped graph pointer handler');
  const calls=[];
  const target={dataset:{nodeId:'node-a'},closest:selector=>
    selector.split(',').some(value=>value.trim()==='.'+targetClass)?target:null};
  const context=vm.createContext({graphMode:mode,dragState:null,nodeDragState:null,panX:0,panY:0,
    knowledgeGraph:{nodes:new Map([['node-a',{}]])},
    knowledgePositions:()=>new Map([['node-a',{x:10,y:20}]]),
    graphSvg:{getBoundingClientRect:()=>({width:1000,height:700}),
      classList:{add:value=>calls.push(value)},setPointerCapture:id=>calls.push(id)}});
  const handler=registered.trim().slice("graphSvg.addEventListener('pointerdown',".length,-2);
  vm.runInContext('('+handler+')',context)({button:0,clientX:100,clientY:100,pointerId:7,
    target,stopPropagation:()=>calls.push('stop')});
  return {context,calls};
}

test('legacy evidence and canonical edges never start background pointer capture',()=>{
  for(const edge of ['legacy-evidence-edge','edge-group']) {
    const result=pointerHarness(edge);
    assert.equal(result.context.dragState,null);
    assert.deepEqual(result.calls,[]);
  }
});
test('blank canvas still pans and knowledge nodes still drag',()=>{
  const canvas=pointerHarness('background');
  assert(canvas.context.dragState);
  assert.deepEqual(canvas.calls,['dragging',7]);
  const node=pointerHarness('node','knowledge');
  assert.equal(node.context.nodeDragState.id,'node-a');
  assert.equal(node.context.dragState,null);
  assert.deepEqual(node.calls,['stop','dragging',7]);
});

test('shared canonical node renders Company A → agency → Company B with clickable evidence edges',()=>{
  const h=harness();
  assert.equal(vm.runInContext('renderPathGraph(data)',Object.assign(h.context,
    {data:path([segment(A,shared,'r1'),segment(shared,B,'r2',true)])})),true);
  assert.equal(h.context.graphMode,'path');
  assert.equal(h.context.knowledgeGraph.nodes.size,3);
  assert.equal(h.context.knowledgeGraph.edges.size,2);
  assert.equal(h.context.knowledgeGraph.edges.get('r2').source,'b');
  assert.equal(h.context.knowledgeGraph.edges.get('r2').primary_evidence.source_name,'Official source');
  assert.equal(h.context.knowledgeGraph.expanded.size,0);
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
test('published company selected from live overview retains its exact ID for a mixed published/live path',()=>{
  const loader=shipped('  async function loadLiveCompanyContributions(', '  function pathEntityActions(');
  assert.match(loader,/public_identifier:match\.public_identifier/);
  const context=vm.createContext({esc:value=>String(value)});
  vm.runInContext(line('pathEntityActions'),context);
  const actions=vm.runInContext('pathEntityActions(entity)',Object.assign(context,{entity:{
    id:'a3bcec97-5ef2-5bb3-ba8f-bde444835ec5',display_name:'大魯閣實業股份有限公司',
    entity_type:'Company',public_identifier:'04690983'}}));
  assert.match(actions,/data-path-uniform="04690983"/);
  assert.match(actions,/data-path-role="source"/);
});


test('query preview keeps both companies visible without inventing a relationship',()=>{
 const h=harness();vm.runInContext(line('renderPathEndpoints'),h.context);
 assert.equal(vm.runInContext('renderPathEndpoints()',h.context),true);
 assert.equal(h.context.knowledgeGraph.nodes.size,2);
 assert.equal(h.context.knowledgeGraph.edges.size,0);
 assert.equal(h.context.knowledgeGraph.nodes.get('a').pathRole,'公司 A / Company A');
 assert.equal(h.context.knowledgeGraph.nodes.get('b').pathRole,'公司 B / Company B');
 h.context.pathSelection.target=A;
 assert.equal(vm.runInContext('renderPathEndpoints()',h.context),false);
});
test('successful path marks the actual bridge and both endpoint roles',()=>{
 const h=harness();Object.assign(h.context,{data:path([segment(A,shared,'r1'),segment(shared,B,'r2',true)])});
 vm.runInContext('renderPathGraph(data)',h.context);
 assert.equal(h.context.knowledgeGraph.nodes.get('shared').pathRole,'連結節點 / Connecting node');
 assert.equal(h.context.knowledgeGraph.nodes.get('b').pathRole,'公司 B / Company B');
});

(async()=>{
 const h=harness(),requests=[];
 Object.assign(h.context,{URLSearchParams,encodeURIComponent,GRAPH_PAGE_SIZE:20,GRAPH_MAX_NODES:60,
   graphDepthLimit:()=>1,fitGraphBounds:()=>{},showKnowledgeNode:()=>{},autoExpandPublishedCompanies:()=>{},
   fetch:async(url)=>{requests.push(url);return{ok:true,json:async()=>({data:h.context.reply})}}});
 Object.assign(h.context,{data:path([segment(A,shared,'r1'),segment(shared,B,'r2',true)])});
 vm.runInContext('renderPathGraph(data)',h.context);
 h.elements.relationshipFilter.value='STALE_HIDDEN_FILTER';
 vm.runInContext(shipped('  async function expandKnowledgeNode(', '  async function openEntityGraph('),h.context);
 const original=h.context.knowledgeGraph.pathData,extra={id:'extra',entity_type:'Company',display_name:'Additional company'};
 h.context.reply={nodes:[shared,A,extra],edges:[{id:'new',source:'extra',target:'shared',primary_evidence:{id:'proof',source_url:'https://example.gov.tw/proof'}}],has_more:true,next_cursor:'page-two'};
 await vm.runInContext("expandKnowledgeNode('shared')",h.context);
 assert.equal(requests.length,1);assert(!requests[0].includes('relationship_type'));
 assert.equal(h.context.knowledgeGraph.nodes.size,4);assert.equal(h.context.knowledgeGraph.edges.size,3);
 assert.equal(h.context.knowledgeGraph.nodes.get('b').depth,2);
 assert.equal(h.context.knowledgeGraph.nodes.get('a').depth,0);
 assert.equal(h.context.knowledgeGraph.pathData,original);assert.equal(h.context.knowledgeGraph.pathExplored,true);
 h.context.reply={nodes:[extra,shared],edges:[],has_more:false};
 await vm.runInContext("expandKnowledgeNode('shared')",h.context);
 assert(requests[1].includes('after=page-two'));assert.equal(h.context.knowledgeGraph.nodes.size,4);
 await vm.runInContext("expandKnowledgeNode('shared')",h.context);assert.equal(requests.length,2);
 h.context.knowledgeGraph.manualPositions=new Map([['b',{x:700,y:360}]]);
 h.context.reply={nodes:[extra,{id:'deeper',entity_type:'GovernmentAgency'}],edges:[{id:'deep-edge',source:'extra',target:'deeper',primary_evidence:{id:'deep-proof'}}]};
 await vm.runInContext("expandKnowledgeNode('extra')",h.context);
 assert(h.context.knowledgeGraph.nodes.has('deeper'));assert.equal(h.context.knowledgeGraph.nodes.get('deeper').depth,3);
 assert.equal(h.context.knowledgeGraph.manualPositions.size,0,'new branch restores the automatic path layout after a drag');
 for(let i=h.context.knowledgeGraph.nodes.size;i<60;i++)h.context.knowledgeGraph.nodes.set('cap-'+i,{id:'cap-'+i,depth:4});
 const before=requests.length;await vm.runInContext("expandKnowledgeNode('deeper')",h.context);assert.equal(requests.length,before);
 console.log('PASS path nodes and newly added nodes expand, paginate, deduplicate, preserve anchors and obey 60-node cap');
})().catch(error=>{console.error(error);process.exitCode=1});

test('path click directly expands on the same canvas without opening a detail overlay',()=>{
 const calls=[],node={id:'bridge',entity_type:'Politician'},info={hidden:false};
 const context=vm.createContext({graphMode:'path',knowledgeGraph:{nodes:new Map([['bridge',node]])},
  nodeDragState:{id:'bridge',moved:false},dragState:null,suppressNodeClick:false,selectedNodeId:null,
  $:()=>info,showKnowledgeNode:()=>calls.push('details'),expandKnowledgeNode:id=>calls.push(id),
  renderKnowledgeGraph:()=>{},setTimeout:()=>{},graphSvg:{classList:{remove(){}},hasPointerCapture:()=>false}});
 const code=html.split('\n').find(row=>row.trimStart().startsWith('const stopDrag='));
 vm.runInContext(code,context);vm.runInContext('stopDrag({pointerId:1})',context);
 assert.deepEqual(calls,['bridge']);assert.equal(info.hidden,true);assert.equal(context.selectedNodeId,'bridge');
});

test('loading ring tracks path and neighbor requests and clears on completion',()=>{
 const panel={hidden:true},label={textContent:''},attrs={},svg={setAttribute:(k,v)=>attrs[k]=v};
 const context=vm.createContext({$:id=>({graphLoading:panel,graphLoadingText:label,svg})[id],pathLoading:true,knowledgeGraph:null});
 vm.runInContext(line('updateGraphLoading'),context);
 vm.runInContext('updateGraphLoading()',context);assert.equal(panel.hidden,false);assert.equal(attrs['aria-busy'],'true');
 context.pathLoading=false;context.knowledgeGraph={loading:new Set(['one','two'])};
 vm.runInContext('updateGraphLoading()',context);assert(label.textContent.includes('2'));assert(!label.textContent.includes('%'));
 context.knowledgeGraph.loading.clear();vm.runInContext('updateGraphLoading()',context);
 assert.equal(panel.hidden,true);assert.equal(attrs['aria-busy'],'false');
 assert(html.includes('exact_depth:'));assert(html.includes('prefers-reduced-motion:reduce'));
});

test('expanded graphs use uniform measured spacing and keep nodes, labels and routed lines apart',()=>{
 const context=vm.createContext({graphMode:'path',knowledgeGraph:{manualPositions:new Map(),edges:new Map()},graphDepthLimit:()=>3,num:Number,graphContext:null,relationshipLabels:{MEMBER_OF:'成員 / Member of'},entityTypeLabels:{Company:'公司 / Company'},connectionEdgeLabel:edge=>edge.label});
 vm.runInContext(shipped('  function graphTextWidth(', '  function createKnowledgeGraph(')+shipped('  function knowledgeMetrics(', '  function showKnowledgeNode('),context);
 for(const count of [3,12,23,60]){
  const nodes=[{...A,depth:0},{...shared,depth:1},{...B,depth:2}];
  for(let i=3;i<count;i++)nodes.push({id:'n'+i,depth:i<14?2:3,display_name:'很長的官方公司名稱及 English organization '+i,entity_type:i%2?'Company':'GovernmentAgency'});
  const edges=nodes.slice(1).map((n,i)=>({id:'edge'+i,source:n.depth===1?'a':n.depth===2?'shared':'n3',target:n.id,label:'政治獻金 / Political contribution\n2023-10-13',relationship_type:'MEMBER_OF'}));
  context.nodes=nodes;context.edges=edges;const layout=vm.runInContext('knowledgeLayout(nodes,edges)',context);
  const boxes=nodes.map(n=>{const p=layout.positions.get(n.id),m=context.knowledgeMetrics(n);return{id:n.id,left:p.x-m.halfWidth,right:p.x+m.halfWidth,top:p.y-m.top,bottom:p.y+m.bottom}});
  function overlaps(a,b){return a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top}
  for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++)assert(!overlaps(boxes[i],boxes[j]),'node overlap');
  const routes=[...layout.routes.values()];for(let i=0;i<routes.length;i++){
   for(const box of boxes)assert(!overlaps(routes[i].labelBox,box),'label/node overlap');
   for(let j=i+1;j<routes.length;j++)assert(!overlaps(routes[i].labelBox,routes[j].labelBox),'edge label overlap');
   for(let k=1;k<routes[i].points.length;k++){const [x1,y1]=routes[i].points[k-1],[x2,y2]=routes[i].points[k],segment={left:Math.min(x1,x2)-.1,right:Math.max(x1,x2)+.1,top:Math.min(y1,y2)-.1,bottom:Math.max(y1,y2)+.1};for(const box of boxes.filter(b=>![edges[i].source,edges[i].target].includes(b.id)))assert(!overlaps(segment,box),'line crosses unrelated node');for(const other of routes)assert(!overlaps(segment,other.labelBox),'line crosses label')}
  }
  for(const depth of [2,3]){const rows=nodes.filter(n=>n.depth===depth).map(n=>layout.positions.get(n.id).y);for(let i=1;i<rows.length;i++)assert.equal(rows[i]-rows[i-1],layout.rowPitch)}
 }
});

test('expanding a shared person keeps the company path level and bundles repeated evidence',()=>{
 const data=path([segment(A,shared,'r1'),segment(shared,B,'r2',true)]);
 const state={pathData:data,rootId:A.id,manualPositions:new Map()};
 const context=vm.createContext({graphMode:'path',knowledgeGraph:state,num:Number,graphContext:null,
   relationshipLabels:{CONTRACT_WITH:'標案 / Contract'},entityTypeLabels:{Company:'公司 / Company'},
   connectionEdgeLabel:edge=>edge.label||'政治獻金 / Political contribution\n2023-10-13'});
 vm.runInContext(shipped('  function graphTextWidth(', '  function createKnowledgeGraph(')+shipped('  function knowledgeMetrics(', '  function showKnowledgeNode('),context);
 const spine=[{...A,pathRole:'公司 A / Company A'},{...shared,pathRole:'連結節點 / Connecting node'},{...B,pathRole:'公司 B / Company B'}];
 const original=data.segments.map(({relationship:r})=>({...r,source:r.source_entity_id,target:r.target_entity_id}));
 const children=Array.from({length:9},(_,i)=>({id:'neighbor'+i,entity_type:i%2?'Company':'GovernmentAgency',
   display_name:'延伸關係及 English organization '+i,expandedFromId:shared.id}));
 const branchEdges=children.map((node,i)=>({id:'branch'+i,source:i%2?node.id:shared.id,target:i%2?shared.id:node.id}));
 const extraRecord={...branchEdges[0],id:'different-evidence',primary_evidence_id:'proof-2'};
 const before=context.groupedGraphLayout(spine,original);
 const after=context.groupedGraphLayout([...spine,...children],[...original,...branchEdges,extraRecord]);
 for(const node of spine)assert.deepEqual(after.positions.get(node.id),before.positions.get(node.id));
 assert.equal(new Set(children.map(node=>after.positions.get(node.id).y)).size,2,'nine neighbors fit in two rows');
 assert.equal(after.routes.size,11,'one visible line per pair');
 assert.deepEqual(Array.from(after.routes.get('branch0').records,record=>record.id),['branch0','different-evidence']);
 assert.equal(after.routes.get('branch0').lines.length,0,'details stay in evidence panel');
 assert(after.routes.get('branch0').hitRoute,'each branch has its own evidence hit area');
 assert(after.routes.get('r1').main&&after.routes.get('r2').main);
 assert(after.routes.get('r2').points[0][0]>after.routes.get('r2').points.at(-1)[0],'arrow retains source-to-target direction');
 assert(after.routes.get('r2').points.every(([,y])=>y===350),'main route remains horizontal');
});

test('typed zones contain only their own nodes and visible routes avoid unrelated zones',()=>{
 const data=path([segment(A,shared,'r1'),segment(shared,B,'r2',true)]);
 const state={pathData:data,rootId:A.id,manualPositions:new Map()};
 const context=vm.createContext({graphMode:'path',knowledgeGraph:state,num:Number,graphContext:null,
   relationshipLabels:{},entityTypeLabels:{},connectionEdgeLabel:()=> '政治獻金 / Political contribution\n2023-10-13'});
 vm.runInContext(shipped('  function graphTextWidth(', '  function createKnowledgeGraph(')+shipped('  function knowledgeMetrics(', '  function showKnowledgeNode('),context);
 const nodes=[{...A,pathRole:'公司 A'}, {...shared,entity_type:'Politician',pathRole:'中介'}, {...B,pathRole:'公司 B'}];
 const edges=data.segments.map(({relationship:r})=>({...r,source:r.source_entity_id,target:r.target_entity_id}));
 for(const [type,amount,parent] of [['Company',4,shared.id],['GovernmentAgency',4,shared.id],['PoliticalParty',1,shared.id],['Politician',9,'GovernmentAgency0']]){
  for(let index=0;index<amount;index++){
   const id=type+index;
   nodes.push({id,display_name:'公開紀錄名稱及 English name '+index,entity_type:type,expandedFromId:parent});
   edges.push({id:'rel-'+id,source:parent,target:id});
  }
 }
 edges.push({id:'cross-evidence',source:'Politician0',target:'PoliticalParty0'});
 const {zones,positions,routes}=context.groupedGraphLayout(nodes,edges);
 assert(zones.some(zone=>zone.type==='Company'&&zone.ids.length===4));
 assert.equal(zones.filter(zone=>zone.type==='Politician').reduce((total,zone)=>total+zone.ids.length,0),10);
 for(const node of nodes){
  const p=positions.get(node.id),zone=zones.find(z=>z.ids.includes(node.id));
  assert.equal(zone.type,node.entity_type);
  assert(p.x>zone.left&&p.x<zone.right&&p.y>zone.top&&p.y<zone.bottom);
 }
 for(let i=0;i<zones.length;i++)for(const b of zones.slice(i+1)){
  const a=zones[i];
  assert(a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top,'typed frames never overlap');
 }
 for(const [id,geometry] of routes){
  const edge=edges.find(e=>e.id===id);
  for(let i=1;i<geometry.points.length;i++){
   const [x,y]=geometry.points[i-1],[u,v]=geometry.points[i];
   assert(x===u||y===v,'route is orthogonal');
   for(const zone of zones.filter(z=>!z.ids.includes(edge.source)&&!z.ids.includes(edge.target))){
    assert(!(x===u?x>zone.left&&x<zone.right&&Math.max(y,v)>zone.top&&Math.min(y,v)<zone.bottom:
      y>zone.top&&y<zone.bottom&&Math.max(x,u)>zone.left&&Math.min(x,u)<zone.right),
      id+' crosses an unrelated '+zone.type+' frame');
   }
  }
 }
 assert(routes.get('cross-evidence').secondary);
 assert(html.includes(':not(.show-cross-links) .path-cross-link{display:none}'));
});
