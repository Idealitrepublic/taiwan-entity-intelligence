"""Unified Evidence schema used by all public-record connectors."""
import hashlib, json
from datetime import datetime, timezone
SCHEMA_VERSION='1.0'
def make_evidence(**kwargs):
    raw=kwargs.get('raw_payload'); source_name=str(kwargs['source_name']); record_id=str(kwargs['source_record_id']); entity_id=str(kwargs['entity_id']); fact_type=str(kwargs['fact_type'])
    evidence_id=hashlib.sha256(f'{source_name}|{record_id}|{entity_id}|{fact_type}'.encode()).hexdigest()
    return {'schema_version':SCHEMA_VERSION,'evidence_id':evidence_id,'observed_at':datetime.now(timezone.utc).isoformat(),'source':{'type':kwargs['source_type'],'name':source_name,'record_id':record_id,'url':kwargs['source_url'],'published_at':kwargs.get('source_published_at')},'subject':{'id':entity_id,'type':kwargs['entity_type']},'fact':{'type':fact_type,'relation':kwargs['relation_type'],'title':kwargs['title'],'summary':kwargs.get('summary')},'confidence':float(kwargs.get('confidence',1.0)),'raw':raw}
def dedupe_evidence(rows):
    seen=set(); out=[]
    for row in rows:
        key=row.get('evidence_id') or json.dumps(row,ensure_ascii=False,sort_keys=True,default=str)
        if key not in seen: seen.add(key); out.append(row)
    return out
