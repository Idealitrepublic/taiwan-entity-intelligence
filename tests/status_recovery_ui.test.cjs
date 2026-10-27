const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('web/index.html','utf8');
const start=html.indexOf('  let statusInFlight='),end=html.indexOf('  const hubDefinitions=',start);
const elements={dbStatus:{innerHTML:''},systemStatus:{textContent:'',className:''}};
let requests=0,mode='failure',resolve;
const ctx=vm.createContext({$:id=>elements[id],Date,AbortController,setTimeout,clearTimeout,num:Number,sourceNotices:[],updateSourceNotice:()=>{},
 fetch:async()=>{requests++;if(mode==='failure')throw Error('network');if(mode==='pending')await new Promise(r=>resolve=r);return{ok:true,json:async()=>({supabase:{connected:true,canonical:{companies:462,people:121,entity_evidence:3,evidence_records:4},source_records:5,source_files:1}})}}});
vm.runInContext(html.slice(start,end),ctx);
(async()=>{
 await vm.runInContext('loadStatus()',ctx);
 assert.match(elements.systemStatus.textContent,/CHECKING/);
 assert.doesNotMatch(elements.systemStatus.textContent,/OFFLINE/);
 mode='success';await vm.runInContext('loadStatus()',ctx);
 assert.match(elements.systemStatus.textContent,/LIVE/);assert.match(elements.dbStatus.innerHTML,/462/);
 mode='failure';await vm.runInContext('loadStatus()',ctx);
 assert.match(elements.dbStatus.innerHTML,/462/);assert.match(elements.dbStatus.innerHTML,/not live/);
 mode='pending';const pending=vm.runInContext('loadStatus()',ctx);const before=requests;
 await vm.runInContext('loadStatus()',ctx);assert.equal(requests,before,'no concurrent status requests');
 resolve();await pending;assert.match(elements.systemStatus.textContent,/LIVE/);assert.doesNotMatch(elements.dbStatus.innerHTML,/status-stale/);
 assert(html.includes("window.addEventListener('online',loadStatus)"));
 assert(html.includes("setInterval(()=>{if(!document.hidden)loadStatus()},60000)"));
 console.log('Status recovery: initial failure, recovery, stale counts, concurrency, refresh PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
