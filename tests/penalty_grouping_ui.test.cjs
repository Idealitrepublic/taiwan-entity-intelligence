const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('web/index.html', 'utf8');
const section = (start, end) => {
  const from = html.indexOf(`  function ${start}(`);
  const to = html.indexOf(`  function ${end}(`, from);
  assert(from >= 0 && to > from, `${start} section exists`);
  return html.slice(from, to);
};
const ctx = vm.createContext({
  esc: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;'),
  rawGrid: () => '',
  filterState: {penaltyView: 'all', penaltyYear: '', penaltyCounty: '', penaltyLaw: ''},
});
vm.runInContext(section('normalizeLaw', 'groupedProcurementCityNodes'), ctx);
vm.runInContext(section('uniqueValues', 'judicialCard'), ctx);
const citations=JSON.parse(JSON.stringify(vm.runInContext(
  'penaltyCitations({label:"來源紀錄",properties:{law_text:"勞基法第24條第1項；第32條、性別工作平等法第13條；職業安全衛生法第6條：原始敘述"}})',ctx)));
assert.deepEqual(citations,[
  {law:'勞動基準法',article:'第24條第1項'},
  {law:'勞動基準法',article:'第32條'},
  {law:'性別平等工作法',article:'第13條'},
  {law:'職業安全衛生法',article:'第6條'}
]);
assert.deepEqual(JSON.parse(JSON.stringify(vm.runInContext(
  'penaltyCitations({properties:{law_text:"勞動基準法第24條第1項、第2項"}})',ctx))),[
  {law:'勞動基準法',article:'第24條第1項'},
  {law:'勞動基準法',article:'第24條第2項'}
]);
assert.deepEqual(JSON.parse(JSON.stringify(vm.runInContext(
  'penaltyCitations({label:"某公司",properties:{}})',ctx))),
  [{law:'法規未標示 / Law unavailable',article:'條款未標示 / Article unavailable'}]);
ctx.penaltyNodes=[{id:'same-record',label:'原始資料',properties:{law_text:'勞基法第24條；性別平等工作法第13條',date:'2026-01-01',agency:'臺北市政府'}}];
const legalGroups=JSON.parse(JSON.stringify(vm.runInContext('groupedLawNodes(penaltyNodes)',ctx)));
assert.equal(legalGroups.length,2,'One source record can appear under each cited law');
assert(legalGroups.every(group=>group.count===1),'Each law counts the original record once');
assert.equal(JSON.parse(JSON.stringify(vm.runInContext(
  'groupedPenaltyArticleNodes(penaltyNodes,"勞動基準法")',ctx)))[0].label,'第24條 · 1 筆');

const rows = [
  {處分日期: '20260105', 主管機關: '台北市勞動局', 違法法規法條: '勞基法第24條', 違反法規內容: 'EARLY-2026'},
  {處分日期: '20261005', 主管機關: '臺北市勞動局', 違法法規法條: '勞動基準法第32條第2項;勞基法第36條第1項', 違反法規內容: 'LATE-2026', _record_url: 'https://example.gov.tw/record/1'},
  {處分日期: '20251010', 主管機關: '高雄市政府', 違法法規法條: '性別平等工作法第13條', 違反法規內容: 'GENDER-2025'},
  {處分日期: '1120102', 主管機關: '南投縣政府', 違法法規法條: '勞動基準法第24條', 違反法規內容: 'ROC-2023'},
];
ctx.rows = rows;
ctx.status = {status: 'ok'};
let rendered = vm.runInContext('penaltyCard(rows,status)', ctx);
assert(rendered.includes('全部裁罰：年度 → 縣市'));
assert(rendered.indexOf('2026 年 / Year') < rendered.indexOf('2025 年 / Year'));
assert(rendered.indexOf('2025 年 / Year') < rendered.indexOf('2023 年 / Year'));
assert(rendered.includes('臺北市') && rendered.includes('高雄市'));
assert(rendered.indexOf('LATE-2026') < rendered.indexOf('EARLY-2026'));
assert.equal((rendered.match(/LATE-2026/g) || []).length, 1);
assert(rendered.includes('GENDER-2025'));
assert(rendered.includes('<details class="record-group" open>'));
assert(rendered.includes('https://example.gov.tw/record/1'));

ctx.filterState.penaltyView = 'labor';
rendered = vm.runInContext('penaltyCard(rows,status)', ctx);
assert(rendered.includes('勞基法：年度 → 法條'));
assert(rendered.includes('勞動基準法第24條'));
assert(rendered.includes('勞動基準法第32條第2項'));
assert(rendered.includes('勞動基準法第36條第1項'));
assert(!rendered.includes('GENDER-2025'));
assert.equal((rendered.match(/LATE-2026/g) || []).length, 2);
assert(rendered.includes('3 筆 / records'));
ctx.filterState.penaltyYear = '2026';
ctx.filterState.penaltyLaw = '勞動基準法第24條';
rendered = vm.runInContext('penaltyCard(rows,status)', ctx);
assert(rendered.includes('EARLY-2026') && !rendered.includes('LATE-2026'));
assert(!rendered.includes('ROC-2023'));

ctx.filterState.penaltyView = 'all';
ctx.filterState.penaltyLaw = '';
ctx.filterState.penaltyCounty = '臺北市';
rendered = vm.runInContext('penaltyCard(rows,status)', ctx);
assert(rendered.includes('LATE-2026') && !rendered.includes('GENDER-2025'));
assert.equal(vm.runInContext('penaltyDateKey({處分日期:"1120102"})', ctx), '20230102');
console.log('PASS penalty year/county and labor year/article grouping, sorting, evidence');
