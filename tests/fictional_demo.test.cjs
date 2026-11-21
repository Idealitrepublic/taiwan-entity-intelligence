const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('web/index.html','utf8');
function section(start,end){const a=html.indexOf(start),b=html.indexOf(end,a);assert(a>=0&&b>a,start);return html.slice(a,b)}
const context=vm.createContext({fictionalDemoNotice:'Fictional demo'});
vm.runInContext(section('  function fictionalDemoData(', '  function fictionalDemoOverview('),context);
const data=vm.runInContext('fictionalDemoData()',context);
assert.equal(data.nodes.length,8);assert.equal(data.edges.length,10);assert.equal(data.records.length,6);
const nodes=new Map(data.nodes.map(n=>[n.id,n])),records=new Map(data.records.map(n=>[n.id,n]));
for(const node of nodes.values()){
  assert(node.is_demo);assert.equal(node.identity_status,'FICTIONAL');assert(node.id.startsWith('demo:'));
  assert(!node.public_identifier);assert(node.display_name.startsWith('範例'));
  assert(['Company','Person','GovernmentAgency','Contract'].includes(node.entity_type));
}
for(const edge of data.edges){
  assert(edge.is_demo);assert(nodes.has(edge.source));assert(nodes.has(edge.target));
  assert.equal(edge.source,edge.source_entity_id);assert.equal(edge.target,edge.target_entity_id);
  assert(records.has(edge.primary_evidence_id));assert.equal(edge.primary_evidence.id,edge.primary_evidence_id);
}
for(const evidence of records.values()){assert(evidence.is_demo);assert.equal(evidence.source_url,null);assert.equal(evidence.retrieved_at,null)}
assert(!JSON.stringify(data).match(/https?:|政治|裁罰|判決|96979933|22659295|54690903/));
assert(data.edges.some(e=>e.source==='demo:person-a'&&e.target==='demo:company-a'&&e.source_role.includes('Chair')));
assert.equal(data.edges.filter(e=>e.source==='demo:company-c'&&e.relationship_type==='DIRECTOR_OF').length,2);
assert.equal(data.edges.filter(e=>nodes.get(e.target).entity_type==='Contract').length,2);
assert.equal(data.edges.filter(e=>e.target==='demo:agency'&&nodes.get(e.source).entity_type==='Company').length,2);
for(const depth of [1,2,3]){
  const path=vm.runInContext(`fictionalDemoPath('demo:company-a','demo:company-b',${depth})`,context);
  assert.equal(path.found,depth>1);
  if(path.found){assert.equal(path.segments.length,depth);const chain=[path.source_entity.id,...path.segments.map(s=>s.to_entity.id)];assert.equal(new Set(chain).size,depth+1);assert.equal(chain.at(-1),'demo:company-b')}
}
for(const a of ['a','b','c'])for(const b of ['a','b','c'])if(a!==b)for(const depth of [1,2,3]){
 const path=vm.runInContext(`fictionalDemoPath('demo:company-${a}','demo:company-${b}',${depth})`,context);
 assert(path.is_demo);if(!path.found)continue;
 assert.equal(path.segments.length,depth);let previous=path.source_entity.id;
 for(const step of path.segments){assert.equal(step.from_entity.id,previous);assert.equal(step.relationship.primary_evidence_id,step.evidence.id);previous=step.to_entity.id}
 assert.equal(previous,path.target_entity.id);
}
assert(vm.runInContext("fictionalDemoPath('demo:company-a','demo:company-c',1).found",context));
for(const args of ["'real','demo:company-b',2","'demo:company-a','demo:company-a',2","'demo:company-a','demo:company-b',4"])
  assert.equal(vm.runInContext('fictionalDemoPath('+args+')',context),null);
data.nodes[0].display_name='modified';assert.equal(vm.runInContext('fictionalDemoData().nodes[0].display_name',context),'範例甲公司');
const actions=vm.createContext({esc:String});vm.runInContext(section('  function pathEntityActions(','  let connectionTargetId='),actions);
const controls=vm.runInContext("pathEntityActions({id:'demo:company-a',display_name:'範例甲公司',entity_type:'Company',is_demo:true})",actions);
assert(controls.includes('data-path-demo="true"'));assert(!/report-export|href=/.test(controls));
assert.equal(vm.runInContext("pathEntityActions({id:'demo:person-a',entity_type:'Person',is_demo:true})",actions),'');
// The demo uses the actual obstacle router; every unrelated node and label stays clear of the route.
context.knowledgeGraph={manualPositions:new Map()};context.knowledgeMetrics=()=>({radius:26,halfWidth:84,top:60,bottom:45});
vm.runInContext(section('  function graphConnector(', '  function groupedGraphLayout('),context);
vm.runInContext(section('  function fictionalDemoLayout(', '  function knowledgePositions('),context);
const layout=vm.runInContext('fictionalDemoLayout(fictionalDemoData().nodes,fictionalDemoData().edges)',context);
for(const e of vm.runInContext('fictionalDemoData().edges',context)){
 const route=layout.routes.get(e.id);assert(route&&route.points.length>=2);
 for(const n of nodes.values()){
  if([e.source,e.target].includes(n.id))continue;
  const p=layout.positions.get(n.id),box={left:p.x-84,right:p.x+84,top:p.y-60,bottom:p.y+45};
  for(let i=1;i<route.points.length;i++){
   const [a,b]=[route.points[i-1],route.points[i]];
   assert(a[0]===b[0]||a[1]===b[1]);
   assert(!(a[0]===b[0]?a[0]>box.left&&a[0]<box.right&&Math.min(a[1],b[1])<box.bottom&&Math.max(a[1],b[1])>box.top:a[1]>box.top&&a[1]<box.bottom&&Math.min(a[0],b[0])<box.right&&Math.max(a[0],b[0])>box.left),e.id+' crosses '+n.id);
  }
 }
}
const runtime={calls:[],knowledgeGraph:{is_demo:true,nodes:new Map([['demo:x',{id:'demo:x'}]]),loading:new Set()},expandFictionalNode:id=>runtime.calls.push(id)};
vm.createContext(runtime);vm.runInContext(section('  async function expandKnowledgeNode(','  async function openEntityGraph('),runtime);
(async()=>{await vm.runInContext("expandKnowledgeNode('demo:x')",runtime);assert.deepEqual(runtime.calls,['demo:x']);console.log('PASS fictional catalog, four scenarios, exact paths, isolation and demo expansion API guard')})().catch(e=>{console.error(e);process.exitCode=1});
