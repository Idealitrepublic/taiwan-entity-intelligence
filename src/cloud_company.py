from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote, urlparse

from .public_config import SUPABASE_PUBLISHABLE_KEY
from .sources.judicial_index import records_for_company

COMPANY_API = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
DIRECTOR_API = "https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396"
SUPABASE = os.environ.get("SUPABASE_URL", "https://rztdbdurkjfrirsrrhtu.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("VITE_SUPABASE_ANON_KEY") or SUPABASE_PUBLISHABLE_KEY
JUDICIAL_SEARCH = "https://judgment.judicial.gov.tw/FJUD/qryresult.aspx?kw={}&judtype=JUDBOOK"

WEBSITE_OVERRIDES = {
    "96979933": {"url": "https://www.cht.com.tw/", "source": "中華電信官方網站 / Chunghwa Telecom official website"},
    "23060248": {"url": "https://www.family.com.tw/", "source": "全家便利商店官方網站 / FamilyMart official website"},
    "22099131": {"url": "https://www.tsmc.com/", "source": "台積公司官方網站 / TSMC official website"},
    "22555003": {"url": "https://www.7-11.com.tw/", "source": "統一超商官方網站 / 7-ELEVEN Taiwan official website"},
}


def _json_get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": "T.E.I./7.0", "Accept": "application/json, text/plain, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig", "replace"))


def _rows(payload):
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "records", "items", "result", "rows", "value"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _moea_rows(api: str, uniform: str, top: int):
    params = urllib.parse.urlencode({"$format": "json", "$filter": f"Business_Accounting_NO eq {uniform}", "$skip": "0", "$top": str(top)})
    return _rows(_json_get(api + "?" + params))


def _supabase_evidence(uniform: str):
    if not SUPABASE_KEY:
        return [], False
    params = urllib.parse.urlencode({"select": "*", "entity_type": "eq.company", "entity_key": f"eq.{uniform}", "limit": "100"})
    req = urllib.request.Request(f"{SUPABASE}/rest/v1/evidence?{params}", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8-sig", "replace"))
            return (data if isinstance(data, list) else []), True
    except Exception:
        return [], False


def _supabase_company(uniform: str):
    if not SUPABASE_KEY:
        return None
    params = urllib.parse.urlencode({"select": "*", "uniform_number": f"eq.{uniform}", "limit": "1"})
    req = urllib.request.Request(f"{SUPABASE}/rest/v1/companies?{params}", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8-sig", "replace"))
            return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None


def build_company(uniform: str):
    company_rows = _moea_rows(COMPANY_API, uniform, 1)
    if not company_rows:
        return {"status": "not_found", "uniform_number": uniform, "company_name": uniform, "company": {}, "people": [], "graph": {"nodes": [], "edges": []}, "evidence": [], "evidence_count": 0, "evidence_status": {"公司登記": {"status": "not_found", "matched": 0}}, "data_mode": "live_moea_core"}

    company = company_rows[0]
    name = str(company.get("Company_Name") or company.get("Juristic_Person_Name") or uniform)

    director_rows = []
    director_error = None
    try:
        director_rows = _moea_rows(DIRECTOR_API, uniform, 1000)
    except Exception as exc:
        director_error = f"{type(exc).__name__}: {exc}"

    people, nodes, edges = [], [{"id": f"company:{uniform}", "type": "company", "label": name, "properties": {"uniform_number": uniform, "source": "經濟部商工行政資料開放平台"}}], []
    for idx, row in enumerate(director_rows[:50], 1):
        person = row.get("Person_Name") or row.get("person_name") or row.get("Name")
        if not person:
            continue
        position = row.get("Person_Position_Name") or row.get("position") or row.get("Position") or "董監事"
        shares = row.get("Person_Shareholding") or row.get("shares")
        representative = row.get("Representative") or row.get("representative")
        people.append({"uniform_number": uniform, "company_name": name, "person_name": person, "position": position, "shares": shares, "representative": representative})
        pid = f"person:{person}:{idx}"
        nodes.append({"id": pid, "type": "person", "label": person, "properties": {"position": position, "shares": shares, "representative": representative, "source": "經濟部公司登記董監事資料"}})
        edges.append({"source": f"company:{uniform}", "target": pid, "relationship": position, "properties": {"source": "MOEA_DIRECTOR_API", "live": True}})

    evidence, db_ok = _supabase_evidence(uniform)
    local_company = _supabase_company(uniform) if SUPABASE_KEY else None

    website_url = None
    website_host = None
    for key, value in company.items():
        if value is None:
            continue
        k, v = str(key).lower(), str(value).strip()
        if not v or not any(t in k for t in ("url", "website", "網址", "網站")):
            continue
        try:
            raw = v if "://" in v else "https://" + v
            host = urllib.parse.urlparse(raw).hostname
            if host:
                website_url, website_host = raw, host.removeprefix("www.")
                break
        except Exception:
            pass

    statuses = {
        "公司登記": {"status": "ok", "matched": 1},
        "董監事": {"status": "ok" if director_rows else ("partial" if director_error else "ok"), "matched": len(people), **({"message": f"董監事來源暫時不可用：{director_error}"} if director_error else {})},
        "我的資料": {"status": "ok" if db_ok else ("not_configured" if not SUPABASE_KEY else "partial"), "matched": len(evidence)},
        "裁罰": {"status": "not_available_in_public_runtime", "matched": 0, "message": "即時裁罰來源由 Supabase evidence layer 分流。"},
        "165": {"status": "not_available_in_public_runtime", "matched": 0, "message": "即時反詐來源由 Supabase evidence layer 分流。"},
        "標案": {"status": "not_available_in_public_runtime", "matched": 0, "message": "即時標案來源由 Supabase evidence layer 分流。"},
        "司法院": {"status": "link", "matched": 0, "url": JUDICIAL_SEARCH.format(urllib.parse.quote_plus(name))},
    }

    return {
        "status": "ok", "uniform_number": uniform, "company": company, "company_name": name,
        "website_url": website_url, "website_host": website_host, "people": people,
        "graph": {"nodes": nodes, "edges": edges}, "evidence": evidence, "evidence_count": len(evidence),
        "local_context": {"configured": bool(SUPABASE_KEY), "company": local_company, "evidence": evidence, "evidence_count": len(evidence)},
        "evidence_status": statuses,
        "website_crosscheck": {"status": "not_available_in_public_runtime", "matched": 0, "website_url": website_url, "website_host": website_host, "records": [], "message": "網址×165 交叉比對不在 Vercel 核心路由執行。"},
        "judicial_search_url": JUDICIAL_SEARCH.format(urllib.parse.quote_plus(name)),
        "data_mode": "live_moea_core_plus_supabase",
        "evidence_note": "來源讀取成功與是否命中是兩個不同指標；公開紀錄不直接等於法律結論。",
    }


def indexed_records(uniform, company_name):
    def fetch(field, value):
        params = urllib.parse.urlencode({'select': '*', field: 'eq.' + value, 'limit': '100', 'order': 'id'})
        req = urllib.request.Request(f'{SUPABASE}/rest/v1/source_records?{params}', headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'})
        with urllib.request.urlopen(req, timeout=8) as response:
            return json.load(response)
    records = fetch('uniform_number', uniform) + fetch('company_name', company_name)
    return list({json.dumps(row['raw'], sort_keys=True, ensure_ascii=False): row for row in records}.values())


_base_company = build_company


def penalty_source_info(row):
    """Describe source availability without pretending a dataset page is a record URL."""
    url = str(row.get('source_url') or '').strip()
    raw = row.get('raw') or {}
    legal_text = ' '.join(str(raw.get(key, '')) for key in ('違法法規法條', '違反法規內容', '法規名稱'))
    is_labor = '勞動' in legal_text or '勞基法' in legal_text or 'labor' in str(row.get('title') or '').lower()
    portal = 'https://announcement.mol.gov.tw/' if is_labor else 'https://www.moenv.gov.tw/'
    return {
        'record_url': None,
        'dataset_url': url or portal,
        'link_status': 'dataset_only',
        'message': '政府來源未提供永久的單筆網址，因此無法直接定位此筆裁罰；下方連結僅為資料集／查詢入口。',
    }


def build_company(uniform):
    data = _base_company(uniform)
    if data.get('status') != 'ok':
        return data
    data.setdefault('evidence', [])
    data.setdefault('graph', {'nodes': [], 'edges': []})
    data['graph'].setdefault('nodes', [])
    data['graph'].setdefault('edges', [])
    data.setdefault('judicial_search_url', JUDICIAL_SEARCH.format(urllib.parse.quote_plus(data.get('company_name') or uniform)))
    override = WEBSITE_OVERRIDES.get(uniform)
    if not data.get('website_url') and override:
        data['website_url'] = override['url']
        data['website_host'] = urllib.parse.urlparse(override['url']).hostname.removeprefix('www.')
        data['website_source'] = override['source']
        data['website_verification'] = 'curated_official_url'
    elif data.get('website_url'):
        data['website_source'] = '公司登記開放資料欄位 / company registry open-data field'
        data['website_verification'] = 'government_registry_field'
    else:
        data['website_source'] = None
        data['website_verification'] = 'not_available'
    data['evidence_status']['165'] = {'status':'not_checked','matched':0,'message':'反詐索引已就緒；有公司網址時自動比對，也可輸入待查網域。'}
    try:
        rows = indexed_records(uniform, data['company_name'])
        penalty = [r for r in rows if r['dataset'] == 'penalties']
        data['labor_penalties'] = []
        for row in penalty:
            source = penalty_source_info(row)
            data['labor_penalties'].append(dict(
                row['raw'],
                _id=row.get('id'),
                _source_name=row.get('title'),
                _record_url=source['record_url'],
                _dataset_url=source['dataset_url'],
                _source_link_status=source['link_status'],
                _source_message=source['message'],
            ))
        data['evidence_status']['裁罰'] = {'status': 'ok', 'matched': len(penalty), 'message': '已匯入公開裁罰資料；公司名稱精確比對，仍須核對原文。'}
        for row in rows:
            source = penalty_source_info(row) if row['dataset'] == 'penalties' else {'record_url': row.get('source_url')}
            data['evidence'].append({'id':row['id'], 'title':row['title'], 'summary':row['summary'], 'source_type':row['dataset'], 'source_url':source.get('record_url'), 'event_date':row['raw'].get('處分日期') or row['raw'].get('date'), 'match_rule':'exact_company_name_or_uniform', 'raw':row['raw']})
        data['evidence_count'] = len(data['evidence'])
    except Exception:
        data['evidence_status']['裁罰'] = {'status':'partial','matched':0,'message':'裁罰索引暫時無法讀取。'}
        data['labor_penalties'] = []
    judicial = records_for_company(data['company_name'])
    data['judicial_records'] = judicial['records']
    data['judicial_result'] = judicial
    data['evidence_status']['司法院'] = {'status': judicial['status'], 'matched': judicial['matched'], 'message': judicial['interpretation'], 'url': data['judicial_search_url']}
    for row in judicial['records']:
        data['evidence'].append({'id':'judicial:'+row['jid'], 'title':row['title'], 'summary':row['summary'], 'source_type':'judicial', 'source_url':row['source_url'], 'event_date':row.get('date'), 'match_rule':judicial['match_rule'], 'raw':row})
    company_node = f"company:{uniform}"
    for idx, row in enumerate(data['labor_penalties']):
        node_id = 'penalty:' + str(row.get('_id') or idx)
        title = row.get('違法法規法條') or row.get('法規名稱') or row.get('_source_name') or '裁罰紀錄'
        data['graph']['nodes'].append({'id':node_id, 'type':'penalty', 'label':str(title), 'properties':{'date':row.get('處分日期') or row.get('date'), 'agency':row.get('主管機關'), 'fine':row.get('罰鍰金額'), 'disposition':row.get('處分字號'), 'fact':row.get('違反法規內容')}})
        data['graph']['edges'].append({'source':company_node, 'target':node_id, 'relationship':'labor_penalty', 'properties':{'source':row.get('_source_name'), 'evidence_id':row.get('_id')}})
    for row in judicial['records']:
        node_id = 'judicial:' + row['jid']
        data['graph']['nodes'].append({'id':node_id, 'type':'judicial', 'label':str(row.get('title') or '裁判書'), 'properties':{'date':row.get('date'), 'jid':row['jid'], 'source_url':row['source_url']}})
        data['graph']['edges'].append({'source':company_node, 'target':node_id, 'relationship':'mentioned_in_judgment', 'properties':{'source':'司法院 JDoc API', 'legal_conclusion':False}})
    data['evidence_count'] = len(data['evidence'])
    if data.get('website_host'):
        try:
            website_check = check_domain(data['website_host'])
            website_check['website_url'] = data.get('website_url')
            website_check['website_source'] = data.get('website_source')
            website_check['website_verification'] = data.get('website_verification')
            data['website_crosscheck'] = website_check
            hits = website_check['anti_fraud']['matched']
            data['evidence_status']['165'] = {'status':'alert' if hits else 'ok', 'matched':hits, 'message':'以完整網域精確比對 165 與數位發展部公開資料。'}
        except Exception:
            data['website_crosscheck'] = {'status':'partial', 'domain':data.get('website_host'), 'website_url':data.get('website_url'), 'anti_fraud':{'matched':0,'records':[]}, 'message':'反詐網域索引暫時無法讀取。'}
    return data


def check_domain(value):
    host = urllib.parse.urlparse(value if '://' in value else 'https://' + value).hostname
    if not host or '.' not in host or len(host) > 253:
        raise ValueError('請輸入有效網站網域。')
    host = host.lower().removeprefix('www.').rstrip('.')
    params = urllib.parse.urlencode({'select':'id,title,domain,raw,source_url','domain':'eq.'+host,'dataset':'eq.anti_fraud','limit':'100'})
    req = urllib.request.Request(f'{SUPABASE}/rest/v1/source_records?{params}',headers={'apikey':SUPABASE_KEY,'Authorization':f'Bearer {SUPABASE_KEY}'})
    with urllib.request.urlopen(req,timeout=8) as response:
        rows=json.load(response)
    return {'status':'ok','domain':host,'anti_fraud':{'status':'ok','matched':len(rows),'records':[dict(r['raw'],source_name=r['title']) for r in rows],'rule':'exact_domain','limited':len(rows)==100}}
