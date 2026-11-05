const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('web/index.html','utf8');
const start=html.indexOf('  let workspaceRefresh='),end=html.indexOf('  const reportRequests=',start);
assert(start>0&&end>start);
function setup(fetch){
  const ctx=vm.createContext({fetch,Date,AbortController,setTimeout,clearTimeout,
    sessionStorage:{setItem(){},removeItem(){}},
    loadWorkspaceConfig:async()=>({supabase_url:'https://development.invalid',publishable_key:'public-test-key'})});
  vm.runInContext(`let workspaceEpoch=0,workspaceSession={access_token:'old',refresh_token:'refresh',user:{id:'owner'},expires_at:1};
    function clearWorkspaceSession(){workspaceEpoch++;workspaceSession=null}`+html.slice(start,end),ctx);
  return ctx;
}
const response=(status,data)=>({status,ok:status>=200&&status<300,json:async()=>data});
const renewed={access_token:'new',refresh_token:'rotated',user:{id:'owner'},expires_in:3600};
(async()=>{
  let configCalls=0;
  const configContext=vm.createContext({workspaceConfig:null,fetch:async()=>{
    configCalls++;return configCalls===1?response(503,{auth_enabled:false}):
      response(200,{auth_enabled:true,supabase_url:'https://development.invalid',publishable_key:'public-test-key'});
  }});
  vm.runInContext(html.split('\n').find(row=>row.trimStart().startsWith('async function loadWorkspaceConfig(')),configContext);
  await assert.rejects(vm.runInContext('loadWorkspaceConfig()',configContext));
  assert.equal(vm.runInContext('workspaceConfig',configContext),null,'failed config must remain retryable');
  await vm.runInContext('loadWorkspaceConfig()',configContext);
  await vm.runInContext('loadWorkspaceConfig()',configContext);assert.equal(configCalls,2);
  let refreshes=0,requests=0,release;
  let ctx=setup(async(url,options)=>{
    if(url.includes('refresh_token')){refreshes++;await new Promise(r=>release=r);return response(200,renewed)}
    requests++;assert.equal(options.headers.Authorization,'Bearer new');return response(200,{data:'private result'});
  });
  const first=vm.runInContext("workspaceRequest('/api/v1/workspaces')",ctx);
  const second=vm.runInContext("workspaceRequest('/api/v1/watchlist')",ctx);
  await new Promise(r=>setImmediate(r));assert.equal(refreshes,1);release();
  assert.deepEqual(await Promise.all([first,second]),['private result','private result']);assert.equal(requests,2);

  // A restored older session has no expiry metadata: renew on the first 401, once.
  refreshes=0;requests=0;
  ctx=setup(async(url,options)=>{
    if(url.includes('refresh_token')){refreshes++;return response(200,renewed)}
    requests++;return options.headers.Authorization==='Bearer new'?response(200,{data:'ok'}):response(401,{});
  });
  vm.runInContext('delete workspaceSession.expires_at',ctx);
  assert.equal(await vm.runInContext("workspaceRequest('/private')",ctx),'ok');assert.equal(refreshes,1);assert.equal(requests,2);

  // Invalid refresh clears private state; source/network failure preserves a retryable session.
  ctx=setup(async()=>response(400,{}));
  await assert.rejects(vm.runInContext("workspaceRequest('/private')",ctx));
  assert.equal(vm.runInContext('workspaceSession',ctx),null);
  ctx=setup(async()=>response(503,{}));
  await assert.rejects(vm.runInContext("workspaceRequest('/private')",ctx));
  assert.equal(vm.runInContext('workspaceSession.access_token',ctx),'old');
  ctx=setup(async()=>response(200,{...renewed,user:{id:'different-owner'}}));
  await assert.rejects(vm.runInContext("workspaceRequest('/private')",ctx),/Account changed/);
  assert.equal(vm.runInContext('workspaceSession',ctx),null,'a refresh must never switch owners');

  // Logging out while renewal is in flight must never resurrect the old account.
  ctx=setup(async()=>{await new Promise(r=>release=r);return response(200,renewed)});
  const pending=vm.runInContext("workspaceRequest('/private')",ctx);
  await new Promise(r=>setImmediate(r));vm.runInContext('clearWorkspaceSession()',ctx);release();
  await assert.rejects(pending,/Account changed/);assert.equal(vm.runInContext('workspaceSession',ctx),null);

  // Also guard the asynchronous JSON body, not just the response headers.
  ctx=setup(async()=>({status:200,ok:true,json:async()=>{await new Promise(r=>release=r);return{data:'old owner'}}}));
  vm.runInContext('workspaceSession.expires_at=Date.now()/1000+3600',ctx);
  const body=vm.runInContext("workspaceRequest('/private')",ctx);
  await new Promise(r=>setImmediate(r));vm.runInContext('clearWorkspaceSession()',ctx);release();
  await assert.rejects(body,/Account changed/);

  // An API that still rejects the renewed token is not retried forever.
  refreshes=0;requests=0;
  ctx=setup(async url=>{if(url.includes('refresh_token')){refreshes++;return response(200,renewed)}requests++;return response(401,{})});
  vm.runInContext('delete workspaceSession.expires_at',ctx);
  await assert.rejects(vm.runInContext("workspaceRequest('/private')",ctx));
  assert.equal(refreshes,1);assert.equal(requests,2);assert.equal(vm.runInContext('workspaceSession',ctx),null);
  assert(html.includes("const reportFetch=scope==='workspace'?workspaceFetch:fetch"),'private PDF uses the same guarded session transport');
  console.log('Workspace session: expiry, single-flight refresh, 401 retry, transient failure, logout isolation, body isolation and PDF transport PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
