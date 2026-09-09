import { parse } from "jsr:@std/csv@1.0.6/parse";
const BASE=Deno.env.get('SUPABASE_URL')!;
const KEY=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const TOKEN_HASH=Deno.env.get('TEI_INGEST_TOKEN_HASH')||'';
const EXPIRES=Number(Deno.env.get("TEI_INGEST_EXPIRES")||"0");
const headers={apikey:KEY,Authorization:`Bearer ${KEY}`,'Content-Type':'application/json'};
async function api(path:string,init:RequestInit={}){const r=await fetch(BASE+'/rest/v1/'+path,{...init,headers:{...headers,...init.headers}});if(!r.ok)throw Error('Database HTTP '+r.status+': '+(await r.text()).slice(0,300));const t=await r.text();return t?JSON.parse(t):null}
function pick(r:any,keys:string[]){for(const k of keys)if(r[k])return String(r[k]).trim();return null}
async function ingest(id:string){
 const files=await api('source_files?select=*&id=eq.'+encodeURIComponent(id)+'&limit=1');if(!files.length)throw Error('Unknown file');const f=files[0];if(f.status==='indexed')return;
 try{
 if(!['penalties','anti_fraud'].includes(f.dataset))throw Error('Unsupported dataset: requires format-specific review');
 const response=await fetch(BASE+'/storage/v1/object/authenticated/tei-raw/'+f.object_path,{headers});if(!response.ok)throw Error('Storage HTTP '+response.status);
 const text=(await response.text()).replace(/^\uFEFF/,'');let rows:any;if(f.file_name.endsWith('.csv'))rows=parse(text,{skipFirstRow:true});else rows=JSON.parse(text);if(!Array.isArray(rows))throw Error('Expected record array');
 for(let offset=0;offset<rows.length;offset+=500){
 const records=rows.slice(offset,offset+500).map((r:any,i:number)=>{
 let domain=pick(r,['網域名稱','網域','網址','偽冒網址']);try{if(domain)domain=new URL(domain.includes('://')?domain:'https://'+domain).hostname.toLowerCase().replace(/^www\./,'')}catch{domain=null}
 return {id:id+':'+(offset+i),source_file_id:id,dataset:f.dataset,company_name:f.dataset==='penalties'?pick(r,['事業單位名稱或負責人','事業單位名稱','事業單位名稱(負責人)','name'])?.replace(/[（(][^()（）]*[)）]$/,'')||null:null,uniform_number:pick(r,['統一編號','統編']),domain,title:pick(r,['標題','網站名稱','case','違法法規法條','網站性質'])||f.file_name,summary:pick(r,['發佈內容','fact','違反法規內容','法律依據']),source_url:f.source_url,raw:r};});
 await api('source_records?on_conflict=id',{method:'POST',headers:{Prefer:'resolution=merge-duplicates,return=minimal'},body:JSON.stringify(records)});
 }
 await api('source_files?id=eq.'+id,{method:'PATCH',headers:{Prefer:'return=minimal'},body:JSON.stringify({status:'indexed',indexed_at:new Date().toISOString(),metadata:{...f.metadata,indexed_rows:rows.length}})});
 }catch(e){await api('source_files?id=eq.'+id,{method:'PATCH',headers:{Prefer:'return=minimal'},body:JSON.stringify({status:'failed',metadata:{...f.metadata,ingestion_error:String(e)}})});throw e}
}
Deno.serve(async req=>{const token=req.headers.get('x-ingest-token')||'';const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(token)))).map(x=>x.toString(16).padStart(2,'0')).join('');if(!TOKEN_HASH||req.method!=='POST'||digest!==TOKEN_HASH||Date.now()>EXPIRES)return new Response('Unauthorized',{status:401});try{const {id}=await req.json();EdgeRuntime.waitUntil(ingest(id).catch(e=>console.error(String(e))));return Response.json({accepted:true,id});}catch(e){return Response.json({error:String(e)},{status:500})}});
