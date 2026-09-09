// Application HTTP -> public-role PostgreSQL verification through a local test adapter.
// Not a claim that Supabase/PostgREST or a production migration has been exercised.
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const http=require('node:http');
const assert=require('node:assert/strict');
const children=[];
const input=process.argv[2];
if(!input)throw Error('Usage: node tests/entity_http_flow.cjs <draft-bundle.json>');
function child(cmd,args,env={}) {
  const p=spawn(cmd,args,{env:{...process.env,...env},stdio:['ignore','pipe','pipe']});
  children.push(p);p.stderr.on('data',x=>process.stderr.write(x));return p;
}
function get(url){return new Promise((resolve,reject)=>{
  const r=http.get(url,res=>{let body='';res.on('data',x=>body+=x);res.on('end',()=>resolve({status:res.statusCode,body}));});
  r.on('error',reject);r.setTimeout(10000,()=>r.destroy(Error('Request timeout')));
});}
async function ready(url){for(let i=0;i<60;i++){try{if((await get(url)).status===200)return;}catch{}await new Promise(r=>setTimeout(r,200));}throw Error('Verification server did not start');}
(async()=>{try{
  child('node',['tests/serve_entity_store.mjs',input]);
  child('python',['app.py'],{TEI_ENTITY_API_ENABLED:'1',TEI_ENTITY_SUPABASE_URL:'http://127.0.0.1:8766',TEI_ENTITY_ANON_KEY:'local-verification'});
  await ready('http://127.0.0.1:8000/');
  await ready('http://127.0.0.1:8766/rest/v1/entities?select=id&limit=1');
  const bundle=JSON.parse(fs.readFileSync(input));
  const company=bundle.entities.find(x=>x.entity_type==='Company').id;
  const paths=[`/api/v1/entities/${company}`,`/api/v1/entities/${company}/relationships?limit=2`,`/api/v1/relationships/${bundle.relationships[0].id}`,`/api/v1/evidence/${bundle.relationships[0].primary_evidence_id}`];
  for(const path of paths){
    const r=await get('http://127.0.0.1:8000'+path);
    assert.equal(r.status,200,r.body);
    const d=JSON.parse(r.body).data;
    if(d.evidence)assert.ok(d.evidence.length>0);
    if(d.items)assert.ok(d.items.length<=2);
    console.log(JSON.stringify({path,status:r.status,evidence:d.evidence?.length,items:d.items?.length,has_more:d.has_more}));
  }
  console.log('Application HTTP / PostgreSQL flow passed. All data was ephemeral.');
}finally{for(const p of children)p.kill('SIGTERM');}})().catch(e=>{console.error(e);process.exitCode=1;});
