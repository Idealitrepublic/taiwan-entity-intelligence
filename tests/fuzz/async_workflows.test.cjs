/** Seeded permutation fuzzing of shipped search lifecycle and stale-response guards. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('web/index.html','utf8');
function shipped(start,end){const a=html.indexOf(start),b=html.indexOf(end,a);assert(a>=0&&b>a);return html.slice(a,b)}
const helpers=shipped('  function beginInvestigation(', '  async function searchCompany(');
const search=shipped('  async function search(){', "  $('search').addEventListener");
const flush=()=>new Promise(r=>setImmediate(r));
let rng=Number(process.env.TEI_FUZZ_SEED||43817)>>>0;const random=()=>((rng=(Math.imul(rng,1664525)+1013904223)>>>0)/4294967296);
(async()=>{
 let total=0;
 for(let i=0;i<2000;i++){
  const controls={q:{value:'',focus(){}},entityTypeFilter:{value:''},search:{disabled:false},uniform:{},company:{}};
  const pending=[],display=[];let hidden=true;
  const context=vm.createContext({URLSearchParams,$:id=>controls[id],companyRequestSerial:0,activeNameRequest:null,nameSearchSerial:0,
   invalidatePathRequest(){},renderPathSelection(){},hideSearchResults(){hidden=true},
   renderSearchResults(data){display.push(data.tag);hidden=false},
   fetch:()=>new Promise((resolve,reject)=>pending.push({resolve,reject}))});
  vm.runInContext(helpers+search,context);
  const tasks=[];for(let j=0;j<3;j++){controls.q.value='查詢'+i+'-'+j;tasks.push(vm.runInContext('search()',context))}
  const cancel=i%5===0;if(cancel)vm.runInContext('dismissSearchResults()',context);
  else if(i%5===1)vm.runInContext('beginInvestigation()',context);
  const retired=cancel||i%5===1;
  const order=[0,1,2];for(let j=2;j>0;j--){const k=Math.floor(random()*(j+1));[order[j],order[k]]=[order[k],order[j]]}
  let latestDone=retired;
  for(const index of order){
   if(i%7===0&&index!==2)pending[index].reject(Error('retired request failure'));
   else pending[index].resolve({ok:true,json:async()=>({data:{tag:index}})});
   await flush();if(index===2)latestDone=true;
   if(!latestDone)assert.equal(controls.search.disabled,true,'An older completion enabled the active search button');
  }
  await Promise.all(tasks);
  if(retired){assert.deepEqual(display,[]);assert.equal(hidden,true,'Cancelled search reopened results')}
  else assert.deepEqual(display,[2],'Only the latest intent can paint results');
  assert.equal(controls.search.disabled,false,'Controls stayed stuck after completion/cancellation');total++;
 }
 console.log(`PASS ${total} response-order/cancel/error schedules; latest intent wins without stale button resets`);
})().catch(e=>{console.error(e);process.exitCode=1});
