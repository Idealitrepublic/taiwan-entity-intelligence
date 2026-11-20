#!/usr/bin/env python3
"""Exercise a reviewed case only after restoring to a disposable local cluster."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ops_restore_drill import drill, query  # noqa: E402
from scripts.run_dev import read_local_env  # noqa: E402
from src.entities.api import dispatch_entity_api  # noqa: E402
from src.entities.models import uuid_string  # noqa: E402
from src.entities.repository import EntityRepository  # noqa: E402


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def exercise_reviewed_path(local, packet):
    if not local.get('PGHOST', '').startswith('/private/tmp/tei-restore-') or local.get('PGUSER') != 'tei_restore':
        raise ValueError('Only a newly restored disposable local cluster is accepted')
    agency=packet['agency']
    check=query(local, "select to_json(exists(select 1 from public.entities where id="+literal(uuid_string(agency['id']))+
                "::uuid and entity_type='GovernmentAgency' and display_name="+literal(agency['display_name'])+
                " and source="+literal(agency['source'])+" and source_id="+literal(agency['source_id'])+"))")
    if not check:
        raise ValueError('Reviewed agency does not match the restored identity')
    # Deliberate writes are confined to this freshly created socket-only clone.
    query(local,"select public.tei_ingest_bundle("+literal(json.dumps(packet['bundle']))+"::jsonb)",read_only=False)
    query(local,"update public.evidence_records set publication_status='draft' where id in (select ee.evidence_id from public.entity_evidence ee join public.entities e on e.id=ee.entity_id where e.entity_type='CivilOrganization' and e.display_name like '%?%'); update public.entities set publication_status='draft' where entity_type='CivilOrganization' and display_name like '%?%';",read_only=False)

    def transport(table, params):
        if table=='rpc/graph_entity_neighbors':
            statement="select coalesce(json_agg(t),'[]') from public.graph_entity_neighbors(focus_id=>"+literal(uuid_string(params['focus_id']))+"::uuid,result_limit=>"+str(int(params['result_limit']))+") t"
        elif table=='relationships':
            groups=re.findall(r'(?:source|target)_entity_id\.in\.\(([^)]+)\)',params['or'])
            a,b=[','.join(literal(uuid_string(x))+'::uuid' for x in group.split(',')) for group in groups[:2]]
            statement="select coalesce(json_agg(to_jsonb(r)||jsonb_build_object('primary_evidence',to_jsonb(ev))),'[]') from (select * from public.relationships where ((source_entity_id in("+a+") and target_entity_id in("+b+")) or (source_entity_id in("+b+") and target_entity_id in("+a+"))) order by id limit 201) r join public.evidence_records ev on ev.id=r.primary_evidence_id"
        else:
            raise ValueError('Unexpected local acceptance read')
        return query(local,'set role anon; '+statement)

    repository=EntityRepository(transport=transport)
    queries=[]
    for depth in (1,2,3):
        code,response,_=dispatch_entity_api('/api/v1/paths',{'source':[packet['source_company_id']],
            'target':[packet['target_company_id']],'company_only':['1'],'max_depth':[str(depth)],'exact_depth':[str(depth)]},
            repository=repository,public_graph_only=True)
        if code!=200:
            raise RuntimeError('Local real-data path API failed')
        queries.append(response['data'])
    path=queries[-1]
    if not path['found'] or path['depth']!=3 or len(path['segments'])!=3:
        raise RuntimeError('Real two-intermediary route not found')
    node_ids={segment[side]['id'] for segment in path['segments'] for side in ('from_entity','to_entity')}
    if len(node_ids)!=4 or any(not segment['evidence'].get('source_url') for segment in path['segments']):
        raise RuntimeError('Path identity or provenance is incomplete')
    missing=query(local,"set role anon;select to_json(count(*)) from public.entities where display_name like '%?%'")
    if missing:
        raise RuntimeError('Local name quarantine failed')
    return {'result':'PASS','scope':'disposable_local_clone_only','shared_database_written':False,
            'missing_glyph_names_after_quarantine':missing,'depth_checks':[{k:r[k] for k in ('found','depth','exact_depth')} for r in queries],
            'path':path,'interpretation':packet['interpretation'],
            'neighborhoods':{entity_id:repository.graph_neighbors(entity_id,limit=25) for entity_id in node_ids}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir',required=True,type=Path)
    parser.add_argument('--local-env-file',required=True,type=Path)
    parser.add_argument('--proposal',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        values=read_local_env(args.local_env_file)
        packet=json.loads(args.proposal.read_text())
        result=drill(args.backup_dir,values['TEI_DEV_DATABASE_URL'],Path(values['TEI_BACKUP_AGE_IDENTITY']),
                     local_exercise=lambda env:exercise_reviewed_path(env,packet))
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'result':result['result'],'local_exercise':result['local_exercise']['result'],
                          'shared_database_written':False}))
        return 0
    except Exception as error:
        print(json.dumps({'result':'FAIL','error_type':type(error).__name__,
                          'detail':str(error) if type(error) in (RuntimeError,ValueError) else 'Sensitive details suppressed'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
