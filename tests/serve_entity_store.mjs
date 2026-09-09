/** Local-only verification gateway over PostgreSQL. Not a replacement for PostgREST.
 * Usage: node tests/serve_entity_store.mjs .build/entity-bundle.json
 * Publishes the supplied draft bundle only in an ephemeral, in-memory database.
 */
import { PGlite } from '@electric-sql/pglite';
import fs from 'node:fs';
import http from 'node:http';
const db = new PGlite();
await db.exec('create role anon; create role authenticated; create role service_role;');
for (const file of fs.readdirSync('supabase/migrations').filter(x=>x.endsWith('.sql')).sort()) {
  await db.exec(fs.readFileSync(`supabase/migrations/${file}`, 'utf8'));
}
const bundle = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
await db.query('select tei_ingest_bundle($1::jsonb)', [JSON.stringify(bundle)]);
await db.exec("update entities set publication_status='published'; update evidence_records set publication_status='published'; update relationships set status='published';");
const allowed = new Set(['entities','relationships','evidence_records','entity_evidence','relationship_evidence']);
const server = http.createServer(async (req,res) => {
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    const table = url.pathname.replace('/rest/v1/','');
    if(req.method !== 'GET' || !allowed.has(table)) throw new Error('unsupported verification request');
    const params=[]; const clauses=[];
    for(const [key,value] of url.searchParams) {
      if(['select','limit','order'].includes(key)) continue;
      if(key==='or') {
        const match=value.match(/^\(source_entity_id\.eq\.([0-9a-f-]+),target_entity_id\.eq\.([0-9a-f-]+)\)$/);
        if(!match) throw new Error('unsupported filter');
        params.push(match[1],match[2]);
        clauses.push(`(source_entity_id=$${params.length-1} or target_entity_id=$${params.length})`);
      } else {
        if(!['id','entity_id','relationship_id','publication_status','status','relationship_type'].includes(key)) throw new Error('unsupported column');
        const match=value.match(/^(eq|gt)\.(.+)$/);
        if(!match) throw new Error('unsupported operation');
        params.push(match[2]); clauses.push(`${key} ${match[1]==='eq'?'=':'>'} $${params.length}`);
      }
    }
    const order=url.searchParams.get('order') || 'id.asc';
    const terms=order.split(',').map(x=>{
      if(!/^(id|evidence_id|fact_type)\.(asc|desc)$/.test(x)) throw new Error('unsupported order');
      return x.replace('.',' ');
    });
    const limit=Number(url.searchParams.get('limit')||50);
    if(!Number.isInteger(limit)||limit<1||limit>51) throw new Error('invalid limit');
    const rows=await db.transaction(async tx=>{
      await tx.exec('set local role anon;');
      const rows=(await tx.query(`select * from public.${table} ${clauses.length?'where '+clauses.join(' and '):''} order by ${terms.join(',')} limit ${limit}`,params)).rows;
      if(table==='entity_evidence'||table==='relationship_evidence') {
        for(const row of rows) {
          row.evidence=(await tx.query('select * from evidence_records where id=$1',[row.evidence_id])).rows[0]||null;
        }
      } else {
        const fields=(url.searchParams.get('select')||'').split(',');
        for(let i=0;i<rows.length;i++) rows[i]=Object.fromEntries(fields.map(k=>[k,rows[i][k]]));
      }
      return rows;
    });
    res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(rows));
  }catch(error){res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:error.message}));}
});
server.listen(8766,'127.0.0.1',()=>console.log(JSON.stringify({verification_store:'http://127.0.0.1:8766',company_id:bundle.entities.find(x=>x.entity_type==='Company').id,relationship_id:bundle.relationships[0].id})));
async function close(){server.close();await db.close();process.exit();}
process.on('SIGTERM',close);process.on('SIGINT',close);
