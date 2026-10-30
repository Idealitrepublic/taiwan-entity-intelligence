const assert = require('node:assert/strict');
const vm = require('node:vm');
const {html, loadDisplay} = require('./web_display_harness.cjs');
const elements = {alertBadge:{},alertItems:{},workspaceItems:{},workspaceCount:{}};
const ctx = vm.createContext({$:id=>elements[id],safeSourceUrl:value=>value,
  dashboardAlerts:[],activeWorkspace:null});
loadDisplay(ctx);
for (const name of ['nodeRows','renderAlerts','workspaceItemTarget','renderWorkspaceItems'])
  vm.runInContext(html.split('\n').find(row=>row.trimStart().startsWith(`function ${name}(`)),ctx);
const properties={position:'董事長',shares:0,identity_status:'source_scoped_observation',extra_field:'<unsafe>&'};
ctx.properties=properties;
const rendered=vm.runInContext('nodeRows(properties)',ctx);
for(const text of ['職稱 / Position','持有股份數 / Shares','Company-scoped observation','>0<','來源欄位 / extra field','&lt;unsafe&gt;&amp;'])
  assert(rendered.includes(text),text);
assert(!rendered.includes('extra_field'));
assert(!rendered.includes('source_scoped_observation'));
assert.equal(properties.identity_status,'source_scoped_observation');
assert.equal(vm.runInContext("displayDate('0850615')",ctx),'1996-06-15');
assert.equal(vm.runInContext("displayDate('20260230')",ctx),'20260230');
assert.equal(vm.runInContext("displayValue('constituency_type','proportional')",ctx),'全國不分區 / Proportional representation');
const context=vm.runInContext("displayContext('term:11;session:4;co_chair:N')",ctx);
assert(context.includes('屆別 / Term：11')&&context.includes('會期 / Session：4')&&context.includes('否 / No'));
assert.equal(vm.runInContext("displayContext('https://example.gov.tw/source_record?id=1')",ctx),
  'https://example.gov.tw/source_record?id=1');
ctx.dashboardAlerts=[{id:'a',event_type:'PROCUREMENT',entity:{display_name:'真實公開公司'},
  evidence:{title:'官方公告',summary:'<unsafe>',source_url:'https://web.pcc.gov.tw/notice'},
  event_observed_at:'2026-08-21',first_seen_at:'2026-10-30T12:00:00Z',read_at:null}];
vm.runInContext('renderAlerts(1)',ctx);
for(const text of ['政府標案更新 / Contract update','紀錄日期 / Record date','2026-08-21',
  '首次通知 / First notified','2026/10/30','標為已讀 / Read','&lt;unsafe&gt;','https://web.pcc.gov.tw/notice'])
  assert(elements.alertItems.innerHTML.includes(text),text);
assert(!elements.alertItems.innerHTML.includes('PROCUREMENT'));
ctx.dashboardAlerts[0].read_at='2026-10-30T12:05:00Z';
vm.runInContext('renderAlerts(0)',ctx);
assert(elements.alertItems.innerHTML.includes('標為未讀 / Unread'));
assert.equal(elements.alertBadge.hidden,true);
ctx.activeWorkspace={items:[{id:'saved',item_type:'EVIDENCE',title:'來源證據',evidence_id:'proof',owner_user_id:'owner',created_by_user_id:'owner'}]};
vm.runInContext('renderWorkspaceItems()',ctx);
for(const text of ['證據 / Evidence','識別與權限 / Identity & ownership','擁有者 / Owner ID：owner'])
  assert(elements.workspaceItems.innerHTML.includes(text),text);
console.log('PASS bilingual terminology, scope, dates, escaping, notification states and ownership details');
