/** Real PostgreSQL engine (PGlite), not a SQL-text assertion or mocked database. */
import { PGlite } from '@electric-sql/pglite';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';

const db = new PGlite();
let checks = 0;
async function rejects(sql, message, params = []) {
  await assert.rejects(db.query(sql, params), undefined, message);
  checks++;
}
try {
  await db.exec('create role anon; create role authenticated; create role service_role;');
  const files = fs.readdirSync('supabase/migrations').filter(x => x.endsWith('.sql')).sort();
  for (const file of files) await db.exec(fs.readFileSync(`supabase/migrations/${file}`, 'utf8'));
  const bundle = JSON.parse(execFileSync('python', ['-c', `
import json
from src.entities.backfill import build_legacy_bundle
snapshot={"companies":[{"id":1,"uniform_number":"12345678","name":"測試公司","fetched_at":"2025-01-01T00:00:00+00:00","source":"MOEA/GCI","source_url":"https://example.gov.tw/company"}],"company_people":[{"id":1,"company_id":1,"person_name":"同名測試人","role":"董事","fetched_at":"2025-01-01T00:00:00+00:00","source":"MOEA/GCI","source_url":"https://example.gov.tw/director"},{"id":2,"company_id":1,"person_name":"同名測試人","role":"董事","fetched_at":"2025-01-01T00:00:00+00:00","source":"MOEA/GCI","source_url":"https://example.gov.tw/director"}]}
print(json.dumps(build_legacy_bundle(snapshot)[0]))
`], { encoding: 'utf8' }));
  const company = bundle.entities.find(x => x.entity_type === 'Company');
  const [rel, second] = bundle.relationships;
  const evidenceId = rel.primary_evidence_id;
  await db.exec('set role service_role;');
  await db.query('select public.tei_ingest_bundle($1::jsonb)', [JSON.stringify(bundle)]);
  await db.query('select public.tei_ingest_bundle($1::jsonb)', [JSON.stringify(bundle)]);
  assert.equal((await db.query('select count(*)::int n from public.entities')).rows[0].n, 3);
  assert.equal((await db.query('select count(*)::int n from public.relationships')).rows[0].n, 2);
  checks += 2;
  const badBundle = structuredClone(bundle);
  badBundle.entities[0].id = '11111111-1111-4111-8111-111111111111';
  await rejects('select public.tei_ingest_bundle($1::jsonb)', 'source identity cannot map to a different ID', [JSON.stringify(badBundle)]);
  await db.exec('reset role; set role anon;');
  assert.equal((await db.query('select count(*)::int n from public.entities')).rows[0].n, 0);
  checks++;
  await rejects('select * from public.entity_identifiers', 'private identifiers are unreadable');
  await rejects('select * from public.legacy_entity_map', 'legacy mapping is private');
  await rejects('select * from public.resolution_candidates', 'resolution candidates are private');
  await rejects('select public.tei_ingest_bundle($1::jsonb)', 'public write RPC denied', [JSON.stringify(bundle)]);
  await rejects("update public.entities set display_name='tampered'", 'public writes denied');
  await rejects('truncate public.entities cascade', 'public truncate denied');
  await db.exec('reset role; set role service_role;');
  await rejects("update public.relationships set status='published' where id=$1", 'draft evidence/endpoints cannot publish', [rel.id]);
  await db.exec("update public.entities set publication_status='published'; update public.evidence_records set publication_status='published';");
  await rejects("update public.relationships set status='published', confidence='LOW' where id=$1", 'low confidence cannot publish', [rel.id]);
  await rejects('update public.relationships set primary_evidence_id=null where id=$1', 'all relationships require evidence', [rel.id]);
  await rejects('update public.relationships set source_entity_id=$1,target_entity_id=$2 where id=$3', 'wrong relationship direction rejected', [company.id, rel.source_entity_id, rel.id]);
  await rejects("update public.relationships set amount='NaN',currency='TWD' where id=$1", 'NaN amount rejected', [rel.id]);
  await rejects("update public.relationships set amount=200 where id=$1", 'currency required', [rel.id]);
  await rejects("update public.relationships set percentage=101 where id=$1", 'percentage bounded', [rel.id]);
  await rejects("update public.relationships set start_date='2025-01-01',end_date='2024-01-01' where id=$1", 'time order checked', [rel.id]);
  await rejects("update public.evidence_records set summary='changed' where id=$1", 'evidence content immutable', [evidenceId]);
  await rejects('delete from public.evidence_records where id=$1', 'linked evidence cannot be deleted', [evidenceId]);
  await db.exec("update public.relationships set status='published'; set constraints all immediate; reset role; set role anon;");
  assert.equal((await db.query('select count(*)::int n from public.relationships')).rows[0].n, 2);
  checks++;
  const companySearch = await db.query("select * from public.search_entities('測試公司', null, 20)");
  assert.equal(companySearch.rows.length, 1);
  assert.equal(companySearch.rows[0].entity_type, 'Company');
  assert.equal(companySearch.rows[0].public_identifier, '12345678');
  const idSearch = await db.query("select * from public.search_entities('12345678', 'Company', 20)");
  assert.equal(idSearch.rows[0].match_type, 'identifier_exact');
  const sameName = await db.query("select * from public.search_entities('同名測試人', 'Person', 20)");
  assert.equal(sameName.rows.length, 2, 'same-name source observations must remain separate');
  assert.notEqual(sameName.rows[0].entity_id, sameName.rows[1].entity_id);
  assert.equal((await db.query('select count(*)::int n from public.entity_public_identifiers')).rows[0].n, 1);
  assert.equal((await db.query("select prosecdef from pg_proc where proname='search_entities'")).rows[0].prosecdef, false);
  checks += 6;
  await rejects("select * from public.search_entities('王', null, 20)", 'one-character enumeration denied');
  await rejects("select * from public.search_entities('測試', null, 21)", 'unbounded result limit denied');
  await rejects("select * from public.search_entities('測試', 'Arbitrary', 20)", 'unknown entity type denied');
  await rejects("insert into public.entity_search_terms values ($1,'篡改','篡改','alias')", 'public search projection writes denied', [company.id]);
  await db.exec('reset role; set role service_role;');
  await db.query("update public.evidence_records set status='retracted' where id=$1", [evidenceId]);
  assert.equal((await db.query('select status from public.relationships where id=$1', [rel.id])).rows[0].status, 'retracted');
  checks++;
  await db.exec('reset role; set role anon;');
  assert.equal((await db.query('select count(*)::int n from public.relationships')).rows[0].n, 1);
  assert.equal((await db.query('select count(*)::int n from public.evidence_records where id=$1', [evidenceId])).rows[0].n, 0);
  checks += 2;
  await db.exec('reset role; set role service_role;');
  await db.query('select public.tei_ingest_bundle($1::jsonb)', [JSON.stringify(bundle)]);
  assert.equal((await db.query('select status from public.relationships where id=$1', [rel.id])).rows[0].status, 'retracted');
  checks++;
  await db.query("update public.entities set publication_status='withdrawn' where id=$1", [second.source_entity_id]);
  assert.equal((await db.query('select status from public.relationships where id=$1', [second.id])).rows[0].status, 'retracted');
  checks++;
  await db.exec('reset role; set role authenticated;');
  await rejects('select * from public.entity_identifiers', 'authenticated role cannot read private IDs');
  await rejects("delete from public.relationships", 'authenticated role cannot write');
  await db.exec('reset role;');
  const exposed = await db.query("select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and not c.relrowsecurity");
  assert.deepEqual(exposed.rows, []);
  checks++;
  console.log(`PostgreSQL integration: ${checks} checks passed; migration, idempotency, constraints, retraction and RLS verified.`);
} finally {
  await db.close();
}
