"""Cross-source intelligence linkage. Matches are signals, not criminal conclusions."""
from collections import defaultdict

def link_evidence(rows):
    groups=defaultdict(list)
    for row in rows:
        raw=row.get('raw') or {}
        for field in ('公司名稱','業者名稱','受處分人','行為人名稱','名稱','name'):
            value=str(raw.get(field) or '').replace(' ','').strip().casefold()
            if value:
                groups[value].append(row); break
    clusters=[]
    for entity_key,evidence in groups.items():
        sources=sorted({e.get('source',{}).get('name') for e in evidence if e.get('source',{}).get('name')})
        if len(sources)>=2:
            clusters.append({'entity_key':entity_key,'evidence_count':len(evidence),'source_count':len(sources),'sources':sources,'evidence_ids':[e.get('evidence_id') for e in evidence],'signal':'multi_source_match'})
    return {'clusters':clusters,'cluster_count':len(clusters)}
