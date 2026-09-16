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
  await db.exec("update public.relationships set status='published'; set constraints all immediate;");
  await db.exec(`insert into public.entities
    (id, entity_type, canonical_name, display_name, source, source_id, identity_status, publication_status)
    values
    ('33333333-3333-4333-8333-333333333333', 'Politician', '林立委', '林立委', 'fixture', 'legislator', 'SOURCE_SCOPED', 'published'),
    ('44444444-4444-4444-8444-444444444444', 'GovernmentAgency', '交通部', '交通部', 'fixture', 'agency', 'EXACT', 'published'),
    ('55555555-5555-4555-8555-555555555555', 'GovernmentOfficial', '王次長', '王次長', 'fixture', 'official', 'SOURCE_SCOPED', 'published'),
    ('88888888-8888-4888-8888-888888888888', 'PoliticalParty', '測試黨', '測試黨', 'fixture', 'party', 'EXACT', 'published'),
    ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'LegislativeBill', '測試法案', '測試法案', 'fixture', 'bill', 'EXACT', 'published')`);
  await db.query(`insert into public.politician_terms
    (id, politician_entity_id, term_number, constituency, constituency_type,
     party_entity_id, start_date, end_date, primary_evidence_id, publication_status)
    values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      '33333333-3333-4333-8333-333333333333', 11, '臺北市第一選舉區', 'district',
      '88888888-8888-4888-8888-888888888888', '2024-02-01', '2028-01-31', $1, 'published')`,
    [evidenceId]);
  await db.exec('set constraints all immediate;');
  await rejects(`insert into public.politician_terms
    (politician_entity_id, term_number, constituency, constituency_type,
     party_entity_id, start_date, primary_evidence_id, publication_status)
    values ('33333333-3333-4333-8333-333333333333', 12, '錯誤選區', 'district',
      '44444444-4444-4444-8444-444444444444', '2028-02-01', $1, 'published')`,
    'published term rejects a non-party entity', [evidenceId]);
  await db.exec("insert into public.entity_aliases(entity_id, alias, source) values ('44444444-4444-4444-8444-444444444444', 'ＭＯＴＣ', 'fixture')");
  await rejects("insert into public.entity_search_terms values ('44444444-4444-4444-8444-444444444444','ＭＯＴＣ','ＭＯＴＣ','alias')", 'search projection requires normalized terms');
  await db.exec('reset role; set role anon;');
  assert.equal((await db.query('select count(*)::int n from public.relationships')).rows[0].n, 2);
  checks++;
  const politicianTerms = await db.query(`select term_number,constituency,start_date,end_date
    from public.politician_terms where politician_entity_id='33333333-3333-4333-8333-333333333333'`);
  assert.equal(politicianTerms.rows.length, 1);
  assert.equal(politicianTerms.rows[0].term_number, 11);
  assert.equal(politicianTerms.rows[0].constituency, '臺北市第一選舉區');
  checks += 3;
  await rejects("insert into public.politician_terms(politician_entity_id,term_number,constituency,start_date,primary_evidence_id) values ('33333333-3333-4333-8333-333333333333',12,'篡改','2028-02-01',$1)", 'public term writes denied', [evidenceId]);
  const politicianIndexes = await db.query(`select indexname from pg_indexes where schemaname='public'
    and indexname in ('politician_terms_entity_period_idx','politician_terms_party_idx','politician_terms_evidence_idx')`);
  assert.equal(politicianIndexes.rows.length, 3);
  checks++;
  const companySearch = await db.query("select * from public.search_entities('測試公司', null, 20)");
  assert.equal(companySearch.rows.length, 1);
  assert.equal(companySearch.rows[0].entity_type, 'Company');
  assert.equal(companySearch.rows[0].public_identifier, '12345678');
  const idSearch = await db.query("select * from public.search_entities('12345678', 'Company', 20)");
  assert.equal(idSearch.rows[0].match_type, 'identifier_exact');
  const fullWidthIdSearch = await db.query("select * from public.search_entities('１２３４５６７８', 'Company', 20)");
  assert.equal(fullWidthIdSearch.rows[0].entity_id, company.id);
  const politicianSearch = await db.query("select * from public.search_entities('林立委', null, 20)");
  assert.equal(politicianSearch.rows[0].entity_type, 'Politician');
  const agencySearch = await db.query("select * from public.search_entities('交通', 'GovernmentAgency', 20)");
  assert.equal(agencySearch.rows[0].entity_type, 'GovernmentAgency');
  const agencyAliasSearch = await db.query("select * from public.search_entities('MOTC', null, 20)");
  assert.equal(agencyAliasSearch.rows[0].entity_type, 'GovernmentAgency');
  const officialSearch = await db.query("select * from public.search_entities('王次長', 'GovernmentOfficial', 20)");
  assert.equal(officialSearch.rows[0].entity_type, 'GovernmentOfficial');
  assert.equal((await db.query("select count(*)::int n from public.search_entities('林立委', 'Person', 20)")).rows[0].n, 0);
  const sameName = await db.query("select * from public.search_entities('同名測試人', 'Person', 20)");
  assert.equal(sameName.rows.length, 2, 'same-name source observations must remain separate');
  assert.notEqual(sameName.rows[0].entity_id, sameName.rows[1].entity_id);
  assert.equal((await db.query('select count(*)::int n from public.entity_public_identifiers')).rows[0].n, 1);
  assert.equal((await db.query("select prosecdef from pg_proc where proname='search_entities'")).rows[0].prosecdef, false);
  checks += 12;
  await rejects("select * from public.search_entities('王', null, 20)", 'one-character enumeration denied');
  await rejects("select * from public.search_entities('測試', null, 21)", 'unbounded result limit denied');
  await rejects("select * from public.search_entities('測試', 'Arbitrary', 20)", 'unknown entity type denied');
  await rejects("insert into public.entity_search_terms values ($1,'篡改','篡改','alias')", 'public search projection writes denied', [company.id]);
  const graphRows = await db.query('select * from public.graph_entity_neighbors($1, 1, null, null)', [company.id]);
  assert.equal(graphRows.rows.length, 2, 'limit + 1 probe row is returned');
  assert.equal(graphRows.rows[0].focus_entity.id, company.id);
  assert.equal(graphRows.rows[0].relationship.relationship_type, 'DIRECTOR_OF');
  assert.equal(graphRows.rows[0].primary_evidence.status, 'active');
  checks += 4;
  const filteredGraphRows = await db.query(
    "select * from public.graph_entity_neighbors($1, 25, null, 'DIRECTOR_OF')", [company.id]);
  assert.equal(filteredGraphRows.rows.length, 2, 'relationship filter keeps matching edges');
  const cursorGraphRows = await db.query(
    'select * from public.graph_entity_neighbors($1, 1, $2, null)',
    [company.id, graphRows.rows[0].relationship.id]);
  assert.equal(cursorGraphRows.rows.length, 1, 'keyset cursor advances without overlap');
  assert.notEqual(cursorGraphRows.rows[0].relationship.id, graphRows.rows[0].relationship.id);
  checks += 3;
  const graphIndexes = await db.query(`select indexname from pg_indexes
    where schemaname='public' and indexname in
      ('relationships_source_type_idx','relationships_target_type_idx')`);
  assert.equal(graphIndexes.rows.length, 2, 'both graph endpoint access paths are indexed');
  checks++;
  await rejects('select * from public.graph_entity_neighbors($1, 26, null, null)', 'unbounded graph expansion denied', [company.id]);
  await rejects("select * from public.graph_entity_neighbors($1, 12, null, 'ARBITRARY')", 'unknown graph relationship type denied', [company.id]);
  await db.exec('reset role; set role service_role;');
  const contributionEvidenceId = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
  const contributionId = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
  await db.query(`insert into public.evidence_records
    (id,source_name,source_record_id,source_class,source_url,source_locator,title,summary,
     observed_at,retrieved_at,content_hash,status,publication_status)
    values ($1,'監察院政治獻金公開查閱平臺','112-legislator-A-0001','Government Open Data',
      'https://ardata.cy.gov.tw/data/search/advanced',
      '{"dataset":"political_contribution_public_platform","source_record_id":"112-legislator-A-0001","match_method":"exact_uniform_number","uniform_number":"12345678"}'::jsonb,
      '政治獻金：測試公司','測試公司 → 林立委；120000 TWD；營利事業捐贈；2024-01-15',
      '2024-01-15T00:00:00Z','2026-09-16T02:00:00Z',$2,'active','published')`,
    [contributionEvidenceId, '0'.repeat(64)]);
  await db.query(`insert into public.relationships
    (id,source_entity_id,target_entity_id,relationship_type,primary_evidence_id,
     start_date,date_precision,observed_at,amount,currency,source_role,confidence,status)
    values ($1,$2,'33333333-3333-4333-8333-333333333333','POLITICAL_CONTRIBUTION_TO',$3,
      '2024-01-15','day','2024-01-15T00:00:00Z',120000,'TWD','營利事業捐贈','EXACT','published')`,
    [contributionId, company.id, contributionEvidenceId]);
  await db.exec('set constraints all immediate; reset role; set role anon;');
  const companyContributions = await db.query(
    'select * from public.political_contributions_for_entity($1, 25, null)', [company.id]);
  assert.equal(companyContributions.rows.length, 1);
  assert.equal(companyContributions.rows[0].relationship.amount, 120000);
  assert.equal(companyContributions.rows[0].relationship.start_date, '2024-01-15');
  assert.equal(companyContributions.rows[0].relationship.source_role, '營利事業捐贈');
  assert.equal(companyContributions.rows[0].company_entity.id, company.id);
  assert.equal(companyContributions.rows[0].politician_entity.id,
    '33333333-3333-4333-8333-333333333333');
  assert.equal(companyContributions.rows[0].primary_evidence.source_record_id,
    '112-legislator-A-0001');
  assert.equal(companyContributions.rows[0].primary_evidence.source_url,
    'https://ardata.cy.gov.tw/data/search/advanced');
  const politicianContributions = await db.query(
    "select * from public.political_contributions_for_entity('33333333-3333-4333-8333-333333333333', 25, null)");
  assert.equal(politicianContributions.rows[0].relationship.id, contributionId);
  assert.equal((await db.query(
    "select prosecdef from pg_proc where proname='political_contributions_for_entity'"
  )).rows[0].prosecdef, false);
  checks += 10;
  await rejects('select * from public.political_contributions_for_entity($1, 26, null)',
    'unbounded contribution read denied', [company.id]);
  await rejects("insert into public.relationships(source_entity_id,target_entity_id,relationship_type,primary_evidence_id,start_date,date_precision,observed_at,amount,currency,source_role,confidence,status) values ($1,'33333333-3333-4333-8333-333333333333','POLITICAL_CONTRIBUTION_TO',$2,'2024-01-15','day','2024-01-15T00:00:00Z',1,'TWD','營利事業捐贈','EXACT','published')",
    'anon contribution writes denied', [company.id, contributionEvidenceId]);
  await db.exec('reset role; set role service_role;');
  const nonExactEvidenceId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
  await db.query(`insert into public.evidence_records
    (id,source_name,source_record_id,source_class,source_url,source_locator,title,summary,
     observed_at,retrieved_at,content_hash,status,publication_status)
    values ($1,'fixture','name-only','Government Open Data','https://example.gov.tw/source',
      '{"match_method":"name","uniform_number":"12345678"}'::jsonb,'名稱比對','',
      '2024-01-15T00:00:00Z','2026-09-16T02:00:00Z',$2,'active','published')`,
    [nonExactEvidenceId, '1'.repeat(64)]);
  await rejects(`insert into public.relationships
    (source_entity_id,target_entity_id,relationship_type,primary_evidence_id,start_date,
     date_precision,observed_at,amount,currency,source_role,confidence,status)
    values ($1,'33333333-3333-4333-8333-333333333333','POLITICAL_CONTRIBUTION_TO',$2,
      '2024-01-15','day','2024-01-15T00:00:00Z',1000,'TWD','名稱推測','EXACT','published')`,
    'name-only company match cannot publish', [company.id, nonExactEvidenceId]);
  // PGlite surfaces the deferred-trigger error but does not roll back the row
  // exactly like server PostgreSQL; remove that rejected fixture explicitly.
  await db.query('delete from public.relationships where primary_evidence_id=$1', [nonExactEvidenceId]);
  await db.exec('reset role; set role anon;');
  assert.equal((await db.query(
    'select count(*)::int n from public.political_contributions_for_entity($1, 25, $2)',
    [company.id, contributionId])).rows[0].n, 1, 'cursor leaves a sentinel focus row');
  checks++;
  await db.exec('reset role; set role service_role;');
  await db.query(`insert into public.relationships
    (id, source_entity_id, target_entity_id, relationship_type, primary_evidence_id,
     observed_at, confidence, status)
    values
    ('66666666-6666-4666-8666-666666666666', $1,
     '44444444-4444-4444-8444-444444444444', 'CONTRACT_WITH', $2,
     '2025-01-01T00:00:00Z', 'EXACT', 'published'),
    ('77777777-7777-4777-8777-777777777777',
     '55555555-5555-4555-8555-555555555555',
     '44444444-4444-4444-8444-444444444444', 'GOVERNMENT_POSITION', $2,
     '2025-01-01T00:00:00Z', 'EXACT', 'published')`, [company.id, evidenceId]);
  await db.exec('set constraints all immediate; reset role; set role anon;');
  const pathRows = await db.query(
    'select * from public.find_entity_relationship_path($1, $2, 3)',
    [rel.source_entity_id, '55555555-5555-4555-8555-555555555555']);
  assert.equal(pathRows.rows.length, 1);
  assert.equal(pathRows.rows[0].path_result.found, true);
  assert.equal(pathRows.rows[0].path_result.depth, 3);
  assert.equal(pathRows.rows[0].path_result.segments.length, 3);
  assert.equal(pathRows.rows[0].path_result.segments[0].evidence.id, evidenceId);
  assert.equal(pathRows.rows[0].path_result.segments[1].relationship.amount, null);
  assert.equal(pathRows.rows[0].path_result.segments[2].traversal_direction, 'reverse');
  assert.equal(pathRows.rows[0].path_result.relationship_limit_per_node, 50);
  checks += 8;
  const shallowPath = await db.query(
    'select * from public.find_entity_relationship_path($1, $2, 2)',
    [rel.source_entity_id, '55555555-5555-4555-8555-555555555555']);
  assert.equal(shallowPath.rows[0].path_result.found, false);
  assert.deepEqual(shallowPath.rows[0].path_result.segments, []);
  assert.equal((await db.query(
    "select count(*)::int n from public.find_entity_relationship_path($1, '99999999-9999-4999-8999-999999999999', 3)",
    [rel.source_entity_id])).rows[0].n, 0);
  assert.equal((await db.query(
    "select prosecdef from pg_proc where proname='find_entity_relationship_path'")).rows[0].prosecdef, false);
  checks += 4;
  await rejects('select * from public.find_entity_relationship_path($1, $1, 3)', 'identical endpoints denied', [rel.source_entity_id]);
  await rejects('select * from public.find_entity_relationship_path($1, $2, 0)', 'zero path depth denied', [rel.source_entity_id, company.id]);
  await rejects('select * from public.find_entity_relationship_path($1, $2, 4)', 'unbounded path depth denied', [rel.source_entity_id, company.id]);
  const lifecycleId = '22222222-2222-4222-8222-222222222222';
  await db.exec('reset role; set role service_role;');
  await db.query(`insert into public.entities
    (id, entity_type, canonical_name, display_name, source, source_id, identity_status, publication_status)
    values ($1, 'Company', '投影生命週期公司', '投影生命週期公司', 'fixture', 'lifecycle', 'EXACT', 'published')`,
    [lifecycleId]);
  await db.exec('reset role; set role anon;');
  assert.equal((await db.query("select count(*)::int n from public.search_entities('投影生命週期公司', null, 20)")).rows[0].n, 1);
  checks++;
  await db.exec('reset role; set role service_role;');
  await db.query("update public.entities set publication_status='withdrawn' where id=$1", [lifecycleId]);
  await db.exec('reset role; set role anon;');
  assert.equal((await db.query('select count(*)::int n from public.entity_search_terms where entity_id=$1', [lifecycleId])).rows[0].n, 0);
  assert.equal((await db.query("select count(*)::int n from public.search_entities('投影生命週期公司', null, 20)")).rows[0].n, 0);
  checks += 2;
  await db.exec('reset role; set role service_role;');
  await db.query("update public.entities set publication_status='published' where id=$1", [lifecycleId]);
  await db.exec('reset role; set role anon;');
  assert.equal((await db.query("select count(*)::int n from public.search_entities('投影生命週期公司', null, 20)")).rows[0].n, 1);
  checks++;
  await db.exec('reset role; set role service_role;');
  await db.query("update public.evidence_records set status='retracted' where id=$1", [evidenceId]);
  assert.equal((await db.query('select status from public.relationships where id=$1', [rel.id])).rows[0].status, 'retracted');
  checks++;
  await db.exec('reset role; set role anon;');
  assert.equal((await db.query('select count(*)::int n from public.relationships')).rows[0].n, 2);
  assert.equal((await db.query('select count(*)::int n from public.evidence_records where id=$1', [evidenceId])).rows[0].n, 0);
  checks += 2;
  await db.exec('reset role; set role service_role;');
  await db.query('select public.tei_ingest_bundle($1::jsonb)', [JSON.stringify(bundle)]);
  assert.equal((await db.query('select status from public.relationships where id=$1', [rel.id])).rows[0].status, 'retracted');
  checks++;
  await db.query("update public.entities set publication_status='withdrawn' where id=$1", [second.source_entity_id]);
  assert.equal((await db.query('select status from public.relationships where id=$1', [second.id])).rows[0].status, 'retracted');
  checks++;
  const assetEvidenceId = '12121212-1212-4212-8212-121212121212';
  const assetRelationshipId = '13131313-1313-4313-8313-131313131313';
  const linkedAssetId = '14141414-1414-4414-8414-141414141414';
  const unresolvedAssetId = '15151515-1515-4515-8515-151515151515';
  await db.query(`insert into public.evidence_records
    (id,source_name,source_record_id,source_class,source_url,source_locator,title,summary,
     observed_at,retrieved_at,content_hash,status,publication_status)
    values ($1,'監察院廉政專刊財產申報資料','302-legislator-asset-1','Government Open Data',
      'https://sunshine.cy.gov.tw/',
      '{"dataset":"asset_declaration","source_record_id":"302-legislator-asset-1","company_match_method":"exact_uniform_number","uniform_number":"12345678"}'::jsonb,
      '財產申報：測試公司股票','林立委持有測試公司股票 1000 股',
      '2025-11-01T00:00:00Z','2026-09-16T03:00:00Z',$2,'active','published')`,
    [assetEvidenceId, '2'.repeat(64)]);
  await db.query(`insert into public.relationships
    (id,source_entity_id,target_entity_id,relationship_type,primary_evidence_id,
     observed_at,amount,currency,quantity,quantity_unit,source_role,confidence,status)
    values ($1,'33333333-3333-4333-8333-333333333333',$2,'ASSET_OWNERSHIP',$3,
      '2025-11-01T00:00:00Z',300000,'TWD',1000,'股','STOCK','EXACT','published')`,
    [assetRelationshipId, company.id, assetEvidenceId]);
  await db.query(`insert into public.asset_declarations
    (id,politician_id,declaration_year,asset_type,asset_name,amount,currency,quantity,
     quantity_unit,company_name,company_entity_id,relationship_id,primary_evidence_id,
     publication_status)
    values
    ($1,'33333333-3333-4333-8333-333333333333',2025,'STOCK','測試公司普通股',
      300000,'TWD',1000,'股','測試公司',$2,$3,$4,'published'),
    ($5,'33333333-3333-4333-8333-333333333333',2025,'INSURANCE','來源僅載名稱之保險',
      null,null,1,'張','同名但未識別公司',null,null,$6,'published')`,
    [linkedAssetId, company.id, assetRelationshipId, assetEvidenceId, unresolvedAssetId,
      nonExactEvidenceId]);
  const draftAssetId = '17171717-1717-4717-8717-171717171717';
  const assetBundle = {entities: [], identifiers: [], evidence: [], entity_evidence: [],
    relationships: [], relationship_evidence: [], legacy_map: [], asset_declarations: [{
      id: draftAssetId, politician_id: '33333333-3333-4333-8333-333333333333',
      declaration_year: 2025, asset_type: 'CASH', asset_name: '現金', amount: '50000',
      currency: 'TWD', quantity: null, quantity_unit: null, company_name: null,
      company_entity_id: null, relationship_id: null, primary_evidence_id: evidenceId,
      publication_status: 'draft'}]};
  await db.query('select public.tei_ingest_asset_declaration_bundle($1::jsonb)',
    [JSON.stringify(assetBundle)]);
  await db.query('select public.tei_ingest_asset_declaration_bundle($1::jsonb)',
    [JSON.stringify(assetBundle)]);
  assert.equal((await db.query('select count(*)::int n from public.asset_declarations where id=$1',
    [draftAssetId])).rows[0].n, 1, 'asset ingestion is idempotent');
  checks++;
  await db.exec('set constraints all immediate; reset role; set role anon;');
  const assetRows = await db.query(`select id,politician_id,declaration_year,asset_type,
    asset_name,amount,quantity,company_name,company_entity_id,relationship_id,
    primary_evidence_id from public.asset_declarations order by id`);
  assert.equal(assetRows.rows.length, 2);
  assert.equal(assetRows.rows[0].asset_type, 'STOCK');
  assert.equal(assetRows.rows[0].company_entity_id, company.id);
  assert.equal(assetRows.rows[0].relationship_id, assetRelationshipId);
  assert.equal(assetRows.rows[1].company_name, '同名但未識別公司');
  assert.equal(assetRows.rows[1].company_entity_id, null, 'name-only company remains unresolved');
  checks += 6;
  const assetIndexes = await db.query(`select indexname from pg_indexes where schemaname='public'
    and indexname in ('asset_declarations_politician_id_idx',
      'asset_declarations_politician_year_idx','asset_declarations_politician_type_idx',
      'asset_declarations_company_idx','asset_declarations_evidence_idx')`);
  assert.equal(assetIndexes.rows.length, 5);
  checks++;
  await rejects(`insert into public.asset_declarations
    (politician_id,declaration_year,asset_type,asset_name,primary_evidence_id)
    values ('33333333-3333-4333-8333-333333333333',2025,'CASH','篡改',$1)`,
    'public asset declaration writes denied', [assetEvidenceId]);
  await rejects('select public.tei_ingest_asset_declaration_bundle($1::jsonb)',
    'public asset ingestion denied', [JSON.stringify({asset_declarations: []})]);
  await db.exec('reset role; set role service_role;');
  const badAssetId = '16161616-1616-4616-8616-161616161616';
  await rejects(`insert into public.asset_declarations
    (id,politician_id,declaration_year,asset_type,asset_name,company_name,
     company_entity_id,primary_evidence_id,publication_status)
    values ($1,'33333333-3333-4333-8333-333333333333',2025,'INSURANCE',
      '名稱推測資產','同名公司',$2,$3,'published')`,
    'name-only asset company cannot publish', [badAssetId, company.id, nonExactEvidenceId]);
  await db.query('delete from public.asset_declarations where id=$1', [badAssetId]);
  await db.query("update public.evidence_records set status='retracted' where id=$1", [assetEvidenceId]);
  assert.equal((await db.query('select publication_status from public.asset_declarations where id=$1',
    [linkedAssetId])).rows[0].publication_status, 'withdrawn');
  checks++;
  await db.exec('reset role; set role anon;');
  const remainingAssets = await db.query('select id from public.asset_declarations');
  assert.deepEqual(remainingAssets.rows, [{id: unresolvedAssetId}],
    'retracted Evidence hides only its declaration');
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
