const assert=require('node:assert/strict');
const vm=require('node:vm');
const {html,loadDisplay}=require('./web_display_harness.cjs');
function shipped(start,end){const a=html.indexOf(start),b=html.indexOf(end,a);assert(a>=0&&b>a);return html.slice(a,b)}
function node(id,type,name){return{id,entity_type:type,display_name:name}}
const A=node('a','Company','甲公司'),B=node('b','Company','乙公司'),P=node('p','Politician','同一官方識別的政治人物');
function segment(from,to,id,reverse=false,kind='POLITICAL_CONTRIBUTION_TO'){
 return{from_entity:from,to_entity:to,relationship:{id,relationship_type:kind,source_entity_id:reverse?to.id:from.id,target_entity_id:reverse?from.id:to.id,primary_evidence_id:`e-${id}`,start_date:'2024-01-03',amount:0,currency:'TWD'},evidence:{id:`e-${id}`,title:'<來源標題>',source_name:'官方來源',source_record_id:'row=1',source_url:'https://example.gov.tw/record',retrieved_at:'2026-10-31T00:00:00Z'}};
}
function path(){return{found:true,depth:2,source_entity:A,target_entity:B,segments:[segment(A,P,'one'),segment(P,B,'two',true)],max_depth:3}}
function mockElement(id){const classes=new Set();return{dataset:{nodeId:id},classList:{toggle(k,on){on?classes.add(k):classes.delete(k)},contains:k=>classes.has(k)},style:{setProperty(){}},classes}}
function harness(){
 const panel={hidden:true,innerHTML:'',listeners:{},addEventListener(k,f){this.listeners[k]=f}},elements={connectionSummary:panel,pathResult:{innerHTML:''}};
 const nodes=[mockElement('a'),mockElement('p'),mockElement('b'),mockElement('unrelated')],edges=[];const calls=[];
 const context=vm.createContext({URL,console,$:id=>elements[id],num:Number,current:null,graphMode:'legacy',expandedHub:null,connectionTargetId:null,connectionFocusOn:true,connectionModel:null,knowledgeGraph:null,lastGraphView:{edges:[]},pathRangeLabels:{3:'最多2個中介'},document:{querySelectorAll:selector=>selector==='#svg .node'?nodes:edges},renderGraph:()=>calls.push('render'),focusLegacyExpansion:()=>calls.push('fit'),collapseGraph:()=>calls.push('return'),showKnowledgeEdge:edge=>calls.push(edge.id),showNode:node=>calls.push(node.id),setPathEndpoint:(role,entity)=>calls.push([role,entity.id]),findRelationshipPath:()=>calls.push('find'),renderPathGraph:()=>true});
 loadDisplay(context);
 vm.runInContext(html.split('\n').find(x=>x.startsWith('  function safeSourceUrl(')),context);
 vm.runInContext(shipped('  function connectionName(', '  function renderPathResult('),context);
 return{context,elements,panel,nodes,calls};
}
function test(name,f){try{f();console.log('PASS '+name)}catch(e){console.error('FAIL '+name,e);process.exitCode=1}}
test('shared political recipient has plain-language summary without reversing donation direction',()=>{
 const h=harness();h.context.data=path();const model=vm.runInContext('connectionPathModel(data)',h.context);assert(model);
 h.context.model=model;assert(vm.runInContext('connectionNarrative(model)',h.context).includes('各有政治獻金紀錄'));
 h.context.graphMode='path';h.context.knowledgeGraph={pathData:path(),edges:new Map([['two',{id:'two'}]])};
 vm.runInContext('renderConnectionSummary()',h.context);const out=h.panel.innerHTML;
 vm.runInContext(shipped('  function renderPathResult(', '  function renderPathGraph('),h.context);
 vm.runInContext('renderPathResult(data)',h.context);
 assert(h.elements.pathResult.innerHTML.includes('乙公司 → 同一官方識別的政治人物'));
 assert(!h.elements.pathResult.innerHTML.includes('政治人物 → 乙公司'));
 assert(out.includes('乙公司 → 同一官方識別的政治人物'));assert(!out.includes('政治人物 → 乙公司'));
 assert(out.includes('2024-01-03'));assert(out.includes('TWD 0'));assert(out.includes('原始來源 / Original source'));assert(out.includes('&lt;來源標題&gt;'));
 assert(h.nodes[1].classes.has('connection-bridge'));assert(h.nodes[3].classes.has('connection-dim'));
 assert(!h.nodes[1].classes.has('connection-dim'));
 h.panel.listeners.click({target:{closest:()=>({hasAttribute:k=>k==='data-connection-evidence',dataset:{connectionEvidence:'1'}})}});assert(h.calls.includes('two'));
});
test('same names with different IDs, absent Evidence and paths beyond three links cannot produce an explanation',()=>{
 for(const change of [d=>d.segments[1].from_entity={...P,id:'other'},d=>d.segments[0].evidence=null,d=>d.depth=4,d=>d.target_entity={...B,id:'other'}]){
  const h=harness(),d=path();change(d);h.context.data=d;assert.equal(vm.runInContext('connectionPathModel(data)',h.context),null);
 }
});
test('direct and three-link paths retain endpoint order and every intermediate',()=>{
 for(const d of [{...path(),depth:1,segments:[segment(A,B,'r')]},(()=>{const Q=node('q','GovernmentAgency','共同機關');return{...path(),depth:3,segments:[segment(A,P,'r1'),segment(P,Q,'r2'),segment(Q,B,'r3',true)]}})()]){
  const h=harness();h.context.data=d;const m=vm.runInContext('connectionPathModel(data)',h.context);assert.equal(m.nodes.length,d.depth+1);assert.equal(m.steps.length,d.depth);
 }
});
function legacyGraph(){return{nodes:[{id:'root',type:'company',label:'甲公司'},{id:'bridge',type:'related_connection',label:'法人董監事 · 董事',evidence:{source_name:'官方董監事',source_record_id:'row=1',source_url:'https://example.gov.tw/directors'}},{id:'other',type:'related_company',label:'乙公司',uniform_number:'12345678',connection_id:'bridge',properties:{'連結類型 / Connection':'法人董監事所代表公司'}}]}}
test('legacy company summary uses its source connector, not a fabricated direct Relationship',()=>{
 const h=harness();h.context.current={graph:legacyGraph()};vm.runInContext('renderConnectionSummary()',h.context);
 assert(!h.panel.hidden);assert(h.panel.innerHTML.includes('法人董監事所代表公司'));assert(h.panel.innerHTML.includes('來源連結 / Source connection'));assert(h.panel.innerHTML.includes('日期未提供'));
 assert(!h.panel.innerHTML.includes('RELATIONSHIP'));assert(!h.panel.innerHTML.includes('class="connection-chip" style="--connection-color:#7fb0ff">法人董監事'));assert(h.panel.innerHTML.includes('來源連接 / Source connector'));h.context.current.graph.nodes[1].evidence.source_url='javascript:alert(1)';vm.runInContext('renderConnectionSummary()',h.context);assert(h.panel.hidden);
});
test('focus switch preserves branch data and restores unrelated nodes',()=>{
 const h=harness();h.context.current={graph:legacyGraph()};h.context.expandedHub='related';vm.runInContext('renderConnectionSummary()',h.context);
 const original=JSON.stringify(h.context.current.graph);assert(h.nodes[3].classes.has('connection-dim'));
 h.panel.listeners.click({target:{closest:()=>({hasAttribute:k=>k==='data-connection-focus'})}});
 assert.equal(h.context.connectionFocusOn,false);assert(!h.nodes[3].classes.has('connection-dim'));assert.equal(JSON.stringify(h.context.current.graph),original);
});
test('unverified loaded co-occurrence is a candidate action and never a confirmed arrow',()=>{
 const h=harness();h.context.graphMode='knowledge';h.context.knowledgeGraph={rootProfile:A,rootId:'a',nodes:new Map([['a',A],['b',B]])};vm.runInContext('renderConnectionSummary()',h.context);
 assert(h.panel.innerHTML.includes('尚未查核'));assert(!h.panel.innerHTML.includes('class="connection-arrow"'));
 h.panel.listeners.click({target:{closest:()=>({hasAttribute:k=>k==='data-connection-find'})}});assert.deepEqual(h.calls,[['source','a'],['target','b'],'find']);
});
test('no result clears stale relation claims and preserves bounded-coverage warning',()=>{
 const h=harness();vm.runInContext(shipped('  function renderPathResult(', '  function renderPathGraph('),h.context);
 vm.runInContext('renderPathResult({found:false,truncated:true,coverage_note:"目前來源範圍"})',h.context);
 assert(!h.panel.hidden);assert(h.panel.innerHTML.includes('不代表兩家公司沒有關係'));assert(h.panel.innerHTML.includes('目前來源範圍'));assert(!h.panel.innerHTML.includes('connection-arrow'));
});
test('path edge labels include relationship and actual date; source graph retains expand/drag/evidence controls',()=>{
 const h=harness();h.context.edge=segment(A,P,'one').relationship;assert(vm.runInContext('connectionEdgeLabel(edge)',h.context).includes('2024-01-03'));
 assert(html.includes('.graph svg[data-path-graph="true"] .edge-label{opacity:1'));
 assert(html.includes("state.pathData=data"));assert(html.includes('renderKnowledgeSummary(nodes,edges);renderConnectionSummary()'));
 assert(html.includes("line.dataset.connectionSource=edge.source"));
 assert(html.includes('@media(max-width:720px){.connection-summary{max-height:none;'));
});

test('expanded graph keeps the same summary and listeners visible; narrowing restores it to the sidebar',()=>{
 const h=harness();let focused=false,wide=true,moves=0;
 const graph={appendChild(panel){panel.parentElement=this;moves++}},right={querySelector(){return{after(panel){panel.parentElement=right;moves++}}}};
 h.elements.rightPanel=right;h.panel.parentElement=right;
 h.context.document.querySelector=selector=>selector==='.graph'?graph:selector==='.main.graph-focused'&&focused?{}:null;
 h.context.matchMedia=()=>({matches:wide});const listener=h.panel.listeners.click;
 vm.runInContext('placeConnectionSummary()',h.context);assert.equal(moves,0);
 focused=true;vm.runInContext('placeConnectionSummary()',h.context);assert.equal(h.panel.parentElement,graph);
 assert.equal(h.panel.listeners.click,listener);
 wide=false;vm.runInContext('placeConnectionSummary()',h.context);assert.equal(h.panel.parentElement,right);
 assert.equal(moves,2);assert(html.includes('placeConnectionSummary();resetGraphView()'));
});
test('expanded fit reserves the actual summary rectangle instead of hiding company B underneath it',()=>{
 const context=vm.createContext({document:{querySelector:()=>({getBoundingClientRect:()=>({left:660})})},$:()=>({getScreenCTM:()=>({inverse:()=>({})}),getBoundingClientRect:()=>({left:0,right:1000,top:0,bottom:700}),createSVGPoint:()=>({matrixTransform(){return{x:this.x,y:this.y}}})})});
 vm.runInContext(shipped('  function graphFitArea(', '  function fitGraphBounds('),context);
 const area=vm.runInContext('graphFitArea()',context);assert.equal(area.x,24);assert.equal(area.width,614);assert.equal(area.x+area.width,638);assert(area.x+area.width<660);
 context.document.querySelector=()=>null;assert.equal(vm.runInContext('graphFitArea().width',context),900);
});

test('changing endpoints or relationship range clears the previous explanation before a new request',()=>{
 const h=harness();h.context.graphMode='path';h.context.knowledgeGraph={pathData:path()};vm.runInContext('renderConnectionSummary()',h.context);assert(!h.panel.hidden);
 Object.assign(h.context,{pathRequestSerial:0,pathRequestController:null,pathLoading:true,clearPathGraph:()=>{},clearTimeout:()=>{}});h.elements.pathFind={};
 vm.runInContext(html.split('\n').find(row=>row.startsWith('  function invalidatePathRequest(')),h.context);vm.runInContext('invalidatePathRequest()',h.context);
 assert(h.panel.hidden);assert.equal(h.panel.innerHTML,'');assert.equal(h.context.connectionModel,null);
});

test('changing range keeps the unverified company comparison action available',()=>{
 const h=harness();h.context.graphMode='knowledge';h.context.knowledgeGraph={rootProfile:A,rootId:'a',nodes:new Map([['a',A],['b',B]])};vm.runInContext('renderConnectionSummary()',h.context);
 Object.assign(h.context,{pathRequestSerial:0,pathRequestController:null,pathLoading:false,clearPathGraph:()=>{}});h.elements.pathFind={};
 vm.runInContext(html.split('\n').find(row=>row.startsWith('  function invalidatePathRequest(')),h.context);vm.runInContext('invalidatePathRequest()',h.context);
 assert(!h.panel.hidden);assert(h.panel.innerHTML.includes('data-connection-find'));assert(h.panel.innerHTML.includes('尚未查核'));
});
