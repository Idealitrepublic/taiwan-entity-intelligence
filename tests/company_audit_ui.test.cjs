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
console.log('7 source-projection UI regression checks passed');
