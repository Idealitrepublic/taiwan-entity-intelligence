#!/usr/bin/env python3
"""Read-only health for the current public product; never changes sync state."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ops_backup import database_environment, executable  # noqa: E402
from scripts.run_dev import read_local_env  # noqa: E402

SQL = """begin read only;
set local role anon;
select jsonb_build_object(
 'entities',(select jsonb_object_agg(entity_type,n) from
  (select entity_type,count(*) n from public.entities group by entity_type) x),
 'relationships',(select count(*) from public.relationships),
 'evidence',(select count(*) from public.evidence_records),
 'invalid_edges',(select count(*) from public.relationships r
  left join public.entities s on s.id=r.source_entity_id
  left join public.entities t on t.id=r.target_entity_id
  left join public.evidence_records ev on ev.id=r.primary_evidence_id
  where s.id is null or t.id is null or ev.id is null
   or nullif(ev.source_url,'') is null or ev.source_locator='{}'::jsonb or ev.retrieved_at is null),
 'missing_provenance',(select count(*) from public.evidence_records
  where nullif(source_url,'') is null or source_locator='{}'::jsonb or retrieved_at is null),
 'duplicate_edges',(select count(*) from (select 1 from public.relationships
  group by source_entity_id,target_entity_id,relationship_type,primary_evidence_id having count(*)>1) d),
 'missing_glyph_names',(select count(*) from public.entities where display_name ~ '[?�]'),
 'fullwidth_question_names_for_review',(select count(*) from public.entities where display_name like '%？%'),
 'freshness',(select jsonb_agg(x order by source_name) from
  (select source_name,count(*) records,min(retrieved_at) oldest_retrieved_at,max(retrieved_at) latest_retrieved_at
   from public.evidence_records group by source_name) x));
rollback;"""


def report(counts, now=None, *, known_issues=()):
    now = now or datetime.now(timezone.utc)
    failures = [key for key in ('invalid_edges', 'missing_provenance', 'duplicate_edges', 'missing_glyph_names')
                if counts.get(key) != 0]
    expected = {'Company', 'Politician', 'GovernmentOfficial', 'GovernmentAgency',
                'PoliticalParty', 'CivilOrganization', 'Contract'}
    if set(counts.get('entities') or {}) != expected:
        failures.append('public_entity_scope')
    freshness = []
    for row in counts.get('freshness') or []:
        parsed = datetime.fromisoformat(row['latest_retrieved_at'].replace('Z', '+00:00'))
        freshness.append({**row, 'latest_retrieval_age_hours': round((now-parsed).total_seconds()/3600, 2)})
    return {'generated_at': now.isoformat(), 'environment': 'tei-development',
            'scope': 'current_public_product_anon_rls', 'read_only': True,
            'high_count': len(failures), 'failures': failures, 'known_upstream_issues': list(known_issues),
            'counts': {**counts, 'freshness': freshness}, 'population_coverage': None,
            'freshness_certified': False,
            'limitations': ['官方母體與逐來源更新 SLA 尚未完整建立；不可由入庫筆數推估全臺覆蓋率。',
                            '資料取得時間不等於官方資料異動時間；即時公司登記與標案需另驗 API。',
                            f"公開範圍有 {counts.get('missing_glyph_names', '未知')} 筆 ASCII 問號／替代字元名稱；篩查不等於法定名稱覆核，不猜字改名。全形問號另列人工判別。",
                            '已撤下的裁判、裁罰、候選人、財產、遊說及 165 不列公開站 freshness；歷史同步健康另留原報告。']}


def markdown(value):
    names = {'Company':'公司','Politician':'立委／政治人物','GovernmentOfficial':'政府官員',
             'GovernmentAgency':'政府機關','PoliticalParty':'政黨','CivilOrganization':'民間團體','Contract':'標案'}
    rows = ['# 公開資料健康檢查', '', f"檢查時間：{value['generated_at']}。唯讀檢查 Development；正式站與 Preview 共用公開資料，本流程不寫入資料庫。", '',
            f"公開資料結構 High = {value['high_count']}；這不等於上線總驗收通過。", '',
            '| 類型 | anon/RLS 可見筆數 |', '|---|---:|']
    rows += [f'| {names.get(k,k)} | {v:,} |' for k,v in value['counts']['entities'].items()]
    rows += ['', f"關係 {value['counts']['relationships']:,} 筆；證據 {value['counts']['evidence']:,} 筆。",
             f"失效關係、缺來源、重複關係、公開缺字名稱：{', '.join(str(value['counts'][k]) for k in ('invalid_edges','missing_provenance','duplicate_edges','missing_glyph_names'))}。", '',
             '## 範圍與限制', ''] + ['- '+x for x in value['limitations']]
    rows += ['', '## 已隔離的來源問題', '']
    rows += [f"- {r['severity']}：{r['description']}（{r['records']} 筆；{r['scope']}）。" for r in value.get('known_upstream_issues', [])]
    rows += ['', '## 各來源實際取得時間', '', '| 來源 | 證據筆數 | 最早取得 | 最近取得 | 距最近取得小時 |', '|---|---:|---|---|---:|']
    rows += [f"| {r['source_name']} | {r['records']} | {r['oldest_retrieved_at']} | {r['latest_retrieved_at']} | {r['latest_retrieval_age_hours']} |" for r in value['counts']['freshness']]
    rows += ['', '原 Phase 6 全來源報告保留於 [歷史健康報告](archive/DATA_HEALTH_PHASE6_2026-11-04.md)。公開站檢查不修改司法 checkpoint，也不宣稱歷史上游錯誤已恢復。', '']
    return '\n'.join(rows)


def civil_review_issues(review, followup=None):
    if followup and followup.get('applied') is True:
        return [
            {'severity': 'Medium', 'records': followup['pending'],
             'scope': '原45筆名稱覆核母體，其他34筆已補證恢復公開',
             'description': '字形或同一身分仍有疑點，原件及實體保留待核'},
            {'severity': 'Medium', 'records': followup['confirmed_historical_held'],
             'scope': '名稱已核對，但有解散登記，未恢復公開',
             'description': '歷史名冊正常狀態與後續解散公告不一致，保留原證據'}]
    if review.get('action') != 'quarantined_after_explicit_shared_public_data_approval':
        return []
    return [
        {'severity': 'Medium', 'records': review['official_missing_glyph_confirmed'],
         'scope': '本輪45筆已隔離團體，不代表全臺母體',
         'description': '官方原件名稱同樣缺字，保留Evidence待官方補正'},
        {'severity': 'Medium', 'records': review['non_csv_review_pending'] + review['official_unavailable'],
         'scope': '本輪45筆已隔離團體，不推定缺字原因',
         'description': '官方非CSV／暫無法取得原件，待逐筆覆核'}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-env', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/public_release_health.json')
    parser.add_argument('--markdown', type=Path, default=ROOT/'docs/DATA_HEALTH.md')
    args = parser.parse_args()
    try:
        local = read_local_env(ROOT/'.env.local') if args.local_env else {}
        env = {k:v for k,v in os.environ.items() if not k.startswith('PG')}
        env.update(database_environment(local.get('TEI_DEV_DATABASE_URL') or os.environ.get('TEI_DEV_DATABASE_URL','')))
        env.update(PGCONNECT_TIMEOUT='15')
        run = subprocess.run([executable('psql'), '-XqAtw', '-v', 'ON_ERROR_STOP=1'], input=SQL,
                             text=True, capture_output=True, env=env, timeout=90)
        if run.returncode:
            raise RuntimeError('Read-only public health query failed; sensitive details suppressed')
        review_path=ROOT/'docs/CIVIL_NAME_QUALITY_REVIEW_2026-11-20.json'
        review=json.loads(review_path.read_text()) if review_path.exists() else {}
        followup_path = ROOT/'docs/CIVIL_NAME_VERIFICATION_2026-11-20.json'
        followup = json.loads(followup_path.read_text()) if followup_path.exists() else None
        issues = civil_review_issues(review, followup)
        value = report(json.loads(run.stdout),known_issues=issues)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        args.markdown.write_text(markdown(value))
        print(json.dumps({'scope':value['scope'],'high_count':value['high_count'],'freshness_certified':False}))
        return bool(value['high_count'])
    except Exception:
        print('Public health check failed; credentials and driver output suppressed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
