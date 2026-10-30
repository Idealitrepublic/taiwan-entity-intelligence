"""Reproducible, read-only Development coverage/identity/capacity report.

No national denominator is invented. No private account rows are selected.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ingest_civil_organizations_dev import (  # noqa: E402
    DEVELOPMENT_WRITE_STOP_BYTES, development_environment,
)
from scripts.audit_graph_coverage_dev import is_development_target  # noqa: E402

SQL = """BEGIN READ ONLY;
select jsonb_build_object(
 'database_bytes',pg_database_size(current_database()),
 'entities',(select jsonb_object_agg(code,n) from (
   select t.code,count(e.id)::int n from public.entity_types t left join public.entities e
   on e.entity_type=t.code and e.publication_status='published' group by t.code) q),
 'relationships',(select count(*) from public.relationships where status='published'),
 'untraceable_relationships',(select count(*) from public.relationships r
   left join public.evidence_records ev on ev.id=r.primary_evidence_id
   left join public.entities s on s.id=r.source_entity_id left join public.entities t on t.id=r.target_entity_id
   where r.status='published' and (ev.id is null or ev.status<>'active' or ev.publication_status<>'published'
   or coalesce(ev.source_url,'')='' or s.publication_status<>'published' or t.publication_status<>'published')),
 'companies_without_exact_id',(select count(*) from public.entities e where e.entity_type='Company'
   and e.publication_status='published' and not exists(select 1 from public.entity_identifiers i
   where i.entity_id=e.id and i.namespace='tw:uniform_number' and i.confidence='EXACT')),
 'duplicate_exact_company_ids',(select count(*) from (select i.value from public.entity_identifiers i
   join public.entities e on e.id=i.entity_id where e.entity_type='Company' and e.publication_status='published'
   and i.namespace='tw:uniform_number' and i.confidence='EXACT' group by i.value having count(distinct e.id)>1) q),
 'source_records',(select jsonb_object_agg(dataset,n) from
   (select dataset,count(*)::int n from public.source_records group by dataset) q),
 'fact_records',jsonb_build_object(
   '政治獻金關係',(select count(*) from public.relationships where status='published' and relationship_type='POLITICAL_CONTRIBUTION_TO'),
   '財產申報紀錄',(select count(*) from public.asset_declarations where publication_status='published')),
 'freshness',(select jsonb_agg(q order by source_name) from (
   select source_name,count(*)::int records,min(retrieved_at) oldest,max(retrieved_at) newest,
   count(*) filter(where retrieved_at<now()-interval '30 days')::int older_30_days
   from public.evidence_records where publication_status='published' and status='active'
   group by source_name) q));
ROLLBACK;"""

TYPE_LABELS = {
    'Company': '公司', 'Person': '人物', 'Politician': '政治人物',
    'GovernmentOfficial': '政府官員', 'GovernmentAgency': '政府機關',
    'PoliticalParty': '政黨', 'CivilOrganization': '民間團體', 'Contract': '標案',
    'Judgment': '裁判', 'Penalty': '裁罰', 'PoliticalContribution': '政治獻金實體',
    'AssetDeclaration': '財產申報實體', 'LegislativeBill': '議案', 'LobbyingRecord': '遊說紀錄',
}


def read_counts():
    env = development_environment()
    if not is_development_target(env):
        raise RuntimeError('Only the verified Development project can be queried')
    result = subprocess.run(['psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1'],
                            input=SQL, text=True, capture_output=True, env=env, timeout=60)
    if result.returncode:
        raise RuntimeError('Development quality query failed; connection details suppressed')
    return json.loads(result.stdout.strip())


def report_markdown(counts):
    required = ('database_bytes', 'relationships', 'untraceable_relationships',
                'companies_without_exact_id', 'duplicate_exact_company_ids')
    if any(type(counts.get(key)) is not int or counts[key] < 0 for key in required):
        raise ValueError('Missing or invalid measured counters; do not substitute zero')
    if counts['untraceable_relationships'] > counts['relationships']:
        raise ValueError('Traceability counters do not reconcile')
    entities = counts['entities']
    if not isinstance(entities, dict) or any(type(n) is not int or n < 0 for n in entities.values()):
        raise ValueError('Invalid published-entity counters')
    room = max(0, DEVELOPMENT_WRITE_STOP_BYTES-counts['database_bytes'])
    lines = ['# Development 資料缺口與容量核對', '',
             f"取得時間：{datetime.now(ZoneInfo('Asia/Taipei')).isoformat()}",
             '範圍：tei-development；只讀查詢，沒有呼叫司法院API或修改Production。', '',
             '## 已發布實體與來源範圍', '',
             '| 類別 | 已發布實體筆數 | 全國／歷年涵蓋率 |', '|---|---:|---|']
    lines += [f"| {TYPE_LABELS.get(kind, '其他實體')} | {n:,} | 未知；尚無可核對的完整母體 |"
              for kind, n in sorted(entities.items())]
    lines += ['', '政治獻金主要以關係、財產申報以既有專用資料表保存；該實體類型為零不代表其紀錄為零。',
              '政府機關／議案的本機索引不包含於上述網站發布數；不得將來源列數當已核對公司數。', '',
              *[f'- {kind}：{n:,} 筆（與實體筆數分開）。' for kind,n in (counts.get('fact_records') or {}).items()], '',
              '## 身分與證據閘門', '',
              f"- 已發布關係：{counts['relationships']:,}；缺公開端點或有效主來源網址：{counts['untraceable_relationships']:,}。",
              f"- 已發布公司缺精確統編：{counts['companies_without_exact_id']:,}；精確統編重複對應多家公司：{counts['duplicate_exact_company_ids']:,}。",
              '- 這些檢查不等於所有人物身分已核對；來源中的同名人物與裁判名稱命中仍不得直接合併。', '',
              '## 免費容量與發布閘門', '',
              f"- 實測資料庫：{counts['database_bytes']:,} bytes；保守停止線：{DEVELOPMENT_WRITE_STOP_BYTES:,} bytes。",
              f'- 至操作停止線的差額：{room:,} bytes，不是全部可用額度或供應商配額。',
              '- 董監事批次工具新增預估成長檢查，超出停止線在上傳前拒絕；確認旗標不能覆蓋此限制。',
              '- 不刪除歷史、收藏或原件來騰空間，不自動升級；完整機關／議案原件仍保存在本機私有目錄。', '',
              '## 來源保存紀錄', '', '| 類別 | 索引列數 |', '|---|---:|']
    source_labels = {'penalties':'勞動裁罰', 'moea_officers':'公司董監事', 'procurement':'政府採購',
                     'judicial':'司法來源', 'nonprofit_tax':'非營利事業稅籍', 'anti_fraud':'反詐騙網域'}
    lines += [f"| {source_labels.get(kind, '其他既有來源')} | {n:,} |"
              for kind,n in sorted((counts.get('source_records') or {}).items())]
    lines += ['', '## 來源取得時間分布', '',
              '超過30日僅為檢查提示，不代表內容失效。最新一筆不能代表整個來源都已更新。取得時間不是來源發布日期。', '',
              '| 來源 | 公開證據 | 最早取得 | 最新取得 | 超過30日 |', '|---|---:|---|---|---:|']
    for row in counts['freshness']:
        name = str(row['source_name']).replace('|', '／').replace('\n', ' ')
        lines.append(f"| {name} | {row['records']:,} | {row['oldest']} | {row['newest']} | {row['older_30_days']:,} |")
    lines += ['', '## 尚未消除的缺口', '',
              '- 全國／歷年母體、不可取得來源、非公司法律身分、未核對人物與司法歷史索引仍有缺口。',
              '- 官方API單筆未命中只能記為本次未取得，不推論事業不存在，不以同名或其他公司的資料補值。',
              '- 這份報告的關聯完整性、容量、來源時間分開呈現，不輸出虛構的總完成率或全國100%。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    counts = read_counts()
    args.output.write_text(report_markdown(counts))
    print(json.dumps({'target':'tei-development', 'report_written':True,
                      'untraceable_relationships':counts['untraceable_relationships']}))


if __name__ == '__main__':
    main()
