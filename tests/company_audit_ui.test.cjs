const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('web/index.html', 'utf8');
const ctx = vm.createContext({esc:String,num:Number,recordText:String,recordDate:r=>r.date||'',penaltyDate:r=>r['處分日期']||r.date||'',recordYear:()=> '2026',
  filterState:{},uniqueValues:()=>[],filterBox:()=>'',filterSelect:()=>'',countyRank:()=>0,
  procurementCounty:()=> '未分類',rawGrid:()=>'',penaltyArticles:()=>[]});
vm.runInContext(html.split('\n').find(line=>line.includes('function penaltySignal(')),ctx);
assert(vm.runInContext("penaltySignal([],{status:'partial'})",ctx).includes('Count unknown, not zero'));
assert(!vm.runInContext("penaltySignal([],{status:'ok'})",ctx).includes('source unavailable'));
for (const [start,end] of [['penaltyRecord','penaltyCard'],['judicialCard','procurementCard'],['procurementCard','mergeProcurement']]) {
  const a=html.indexOf(`  function ${start}(`), b=html.indexOf(`  function ${end}(`,a);
  assert(a>=0 && b>a);
  vm.runInContext(html.slice(a,b),ctx);
}
assert(vm.runInContext("penaltyRecord({_identity_status:'candidate'})",ctx).includes('identity unverified'));
assert(!vm.runInContext("penaltyRecord({_identity_status:'verified_identifier'})",ctx).includes('identity unverified'));
ctx.result={limited:true,matched:85,records:[{jid:'J',date:'2025-07-31'}],coverage_note:'coverage warning',date_note:'date basis'};
let rendered=vm.runInContext('judicialCard(result)',ctx);
assert(rendered.includes('索引命中 85 筆，載入 1 筆'));
assert(rendered.includes('coverage warning') && rendered.includes('date basis'));
ctx.result={records:[{company_names:['WINNER','LOSER'],awardee_names:['WINNER'],date:'20261001'}]};
rendered=vm.runInContext('procurementCard(result)',ctx);
assert(rendered.includes('WINNER'));
assert(!rendered.includes('LOSER'));
const searchCalls=[];
const searchContext=vm.createContext({hideSearchResults:()=>{},
  searchCompany:async(uniform,item)=>searchCalls.push(['company',uniform,item?.entity_id]),
  openEntityGraph:async(id)=>searchCalls.push(['entity',id])});
const routeStart=html.indexOf('  async function openSearchResult(');
const routeEnd=html.indexOf('  async function searchCompany(',routeStart);
assert(routeStart>=0&&routeEnd>routeStart);
vm.runInContext(html.slice(routeStart,routeEnd),searchContext);
(async()=>{
  await vm.runInContext("openSearchResult({entity_type:'Company',public_identifier:'96979933',entity_id:'published-company'})",searchContext);
  await vm.runInContext("openSearchResult({entity_type:'Politician',entity_id:'politician'})",searchContext);
  assert.deepEqual(searchCalls,[['company','96979933','published-company'],['entity','politician']]);
  const overview=html.split('\n').find(line=>line.trimStart().startsWith('function companyOverview('));
  assert(overview);
  const overviewContext=vm.createContext({esc:String,companySearchItem:{entity_id:'published-company'},
    companyRegistryFields:()=>'',websiteCard:()=>''});
  vm.runInContext(overview,overviewContext);
  const snapshot=vm.runInContext("companyOverview({uniform_number:'96979933',data_mode:'published_registry_snapshot_plus_supabase'}, {}, [], {}, false)",overviewContext);
  assert(snapshot.includes('open-published-graph'));
  assert(snapshot.includes('官方登記快照'));
  assert(snapshot.includes('來源暫不可用'));
  assert(snapshot.includes('不能據此判定為零人'));
  assert(!snapshot.includes('目前無董監事資料'));
  assert(html.includes("$('people').textContent=data.data_mode==='published_registry_snapshot_plus_supabase'?'—':people.length"));
  assert(html.includes("count===null?'來源暫不可用 / Unavailable'"));
  assert(html.includes("const procurementUpdate=procurementPromise.then(procurement=>"));
  assert(html.includes("const relatedUpdate=relatedPromise.then(related=>"));
  assert(html.includes("await Promise.allSettled([procurementUpdate,relatedUpdate])"));
  assert(!html.includes('const [procurement,related]=await Promise.all([procurementPromise,relatedPromise])'));
  assert(html.includes("definition.group==='procurement'&&current?.procurement_result?.status==='partial'"));
  overviewContext.companySearchItem={entity_id:'fallback-company',is_live_fallback:true};
  const liveFallback=vm.runInContext("companyOverview({uniform_number:'96979933'}, {}, [], {}, false)",overviewContext);
  assert(!liveFallback.includes('open-published-graph'));
  let finishRelated;
  const relatedPending=new Promise(resolve=>{finishRelated=resolve});
  const controls={search:{disabled:false,textContent:''},domain:{value:''},graphSub:{textContent:''}};
  const renderCounts=[];
  const asyncContext=vm.createContext({companyRequestSerial:0,companySearchItem:null,relatedCompanyBranches:new Map(),
    $:id=>controls[id],Date,Promise,fetch:async url=>({ok:true,json:async()=>url.includes('/api/company-related/')?await relatedPending:url.includes('/api/procurement/')?{status:'ok',matched:71,records:[{id:'award'}]}:{uniform_number:'96979933',graph:{nodes:[],edges:[]}}}),
    mergeWebsiteCheck:()=>{},render:data=>renderCounts.push(data.procurement_result?.matched||0),mergeProcurement:(data,result)=>{data.procurement_result=result},mergeRelatedCompanies:()=>{},loadLiveCompanyContributions:async()=>{}});
  const searchStart=html.indexOf('  async function searchCompany('),searchEnd=html.indexOf('  async function search(){',searchStart);
  vm.runInContext(html.slice(searchStart,searchEnd),asyncContext);
  const searchTask=vm.runInContext("searchCompany('96979933')",asyncContext);
  await new Promise(resolve=>setImmediate(resolve));
  assert(renderCounts.includes(71),'awards must render without waiting for the related-company API');
  finishRelated({status:'partial',uniform_number:'96979933',items:[]});
  await searchTask;
  console.log('Company search and snapshot UI regression checks passed');
})().catch(error=>{console.error(error);process.exitCode=1});
console.log('7 source-projection UI regression checks passed');
