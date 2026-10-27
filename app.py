"""Canonical WSGI entrypoint shared by every Vercel domain."""
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlencode
from http import HTTPStatus
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import urllib.request
from src import cloud_company as core
from src.sources.procurement import lookup_awards
from src.live_related_companies import related_companies
from src.entities.api import dispatch_entity_api
from src.runtime_config import private_supabase_config
from src.reports import dispatch_report_api
from src.workspaces import dispatch_workspace_api
from src.watchlists import dispatch_watchlist_api
from src.rate_limit import client_identity, request_allowed
from src.source_incidents import active_source_notices

WEB = Path(__file__).parent / 'web'
STATUS_CACHE = {}
STATUS_CACHE_LOCK = Lock()

def db_count(table, **filters):
    query = urlencode({'select': '*', **filters})
    req = urllib.request.Request(f'{core.SUPABASE}/rest/v1/{table}?{query}', method='HEAD', headers={'apikey': core.SUPABASE_KEY, 'Authorization': f'Bearer {core.SUPABASE_KEY}', 'Prefer': 'count=exact'})
    with urllib.request.urlopen(req, timeout=8) as response:
        return int(response.headers['Content-Range'].split('/')[-1])

def workspace_public_config():
    url, key = private_supabase_config()
    return {'supabase_url': url, 'publishable_key': key, 'auth_enabled': bool(url and key)}


def log_event(level, event, **fields):
    """Emit one redacted JSON line for Vercel Runtime Logs and local stderr."""
    record = {'level': level, 'event': event, **fields}
    print(json.dumps(record, ensure_ascii=False, separators=(',', ':')),
          file=sys.stderr, flush=True)


def dispatch(path, query, method='GET', payload=None, authorization=None):
    if path.rstrip('/') == '/api/v1/workspace-config':
        if method not in ('GET', 'HEAD'):
            return 405, {'error': 'Method not allowed'}, None
        return 200, workspace_public_config(), None
    if path.rstrip('/').startswith('/api/v1/reports'):
        if method not in ('GET', 'HEAD'):
            return 405, {'error': 'Method not allowed'}, None
        return dispatch_report_api(
            path, query, authorization=authorization)
    if path.rstrip('/').startswith('/api/v1/workspaces'):
        return dispatch_workspace_api(
            'GET' if method == 'HEAD' else method, path, payload, authorization)
    if (path.rstrip('/').startswith('/api/v1/watchlist')
            or path.rstrip('/').startswith('/api/v1/alerts')):
        return dispatch_watchlist_api(
            'GET' if method == 'HEAD' else method, path, query, payload, authorization)
    if path.startswith('/api/v1/'):
        if method not in ('GET', 'HEAD'):
            return 405, {'error': 'Method not allowed'}, None
        return dispatch_entity_api(path, query)
    entity_uuid = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    page_route = path == '/' or bool(re.fullmatch(rf'/(?:entity|graph|politician)/{entity_uuid}/?', path))
    if page_route or path in ('/app.js', '/tei-enhancements.js'):
        name = 'index.html' if page_route else path[1:]
        return 200, (WEB / name).read_text(), 'text/html; charset=utf-8' if page_route else 'application/javascript; charset=utf-8'
    if path == '/api/status':
        cache_key = (core.SUPABASE, id(db_count))
        with STATUS_CACHE_LOCK:
            cached = STATUS_CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < 55:
            saved = cached[1]
            return saved[0], {**saved[1], 'source_notices': active_source_notices()}, None
        db = {'configured': bool(core.SUPABASE_KEY), 'connected': False}
        if core.SUPABASE_KEY:
            tables = ['source_files', 'companies', 'people', 'evidence', 'source_records']
            counts = {
                'companies': ('entities', {'entity_type': 'eq.Company'}),
                'people': ('entities', {'entity_type': 'in.(Person,Politician,GovernmentOfficial)'}),
                'entities': ('entities', {}),
                'entity_evidence': ('entity_evidence', {}),
                'evidence_records': ('evidence_records', {}),
                'relationships': ('relationships', {}),
            }
            specs = [(name, name, {}) for name in tables] + [
                ('canonical.' + name, table, filters)
                for name, (table, filters) in counts.items()]

            def checked_count(spec):
                label, table, filters = spec
                try:
                    return label, db_count(table, **filters), False
                except Exception:
                    return label, None, True

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(checked_count, specs))
            failed_specs = [spec for spec, result in zip(specs, results) if result[2]]
            if failed_specs:
                # Exact counts on large Evidence tables can fail briefly during
                # cold starts. Retry only those counts without repeating successes.
                with ThreadPoolExecutor(max_workers=2) as pool:
                    retried = dict((label, (label, value, failed))
                                   for label, value, failed in pool.map(checked_count, failed_specs))
                results = [retried.get(result[0], result) for result in results]
            for label, value, _ in results:
                if label.startswith('canonical.'):
                    db.setdefault('canonical', {})[label.split('.', 1)[1]] = value
                else:
                    db[label] = value
            db['legacy'] = {key: db[key] for key in ('companies', 'people', 'evidence')}
            db['connected'] = any(value is not None for _, value, _ in results)
            db['partial'] = db['connected'] and any(failed for _, _, failed in results)
            if not db['connected']:
                db['error'] = '資料庫連線失敗，請檢查伺服器金鑰與資料表權限。'
        code = 200 if db['connected'] else 503
        body = {'status': 'partial' if db.get('partial') else 'ok' if db['connected'] else 'degraded',
                'version': '9.3-directional-filters', 'supabase': db,
                'source_notices': active_source_notices()}
        if db['connected']:
            with STATUS_CACHE_LOCK:
                STATUS_CACHE[cache_key] = (time.monotonic(), (code, body))
        return code, body, None
    if path == '/api/domain-check':
        try:
            return 200, core.check_domain(query.get('domain',[''])[0]), None
        except ValueError as exc:
            return 400, {'error':str(exc)}, None
    if path.startswith('/api/procurement/'):
        uniform = path[len('/api/procurement/'):]
        if not re.fullmatch(r'[0-9]{8}', uniform):
            return 400, {'status': 'error', 'error': '統編必須是 8 碼數字。'}, None
        return 200, lookup_awards(uniform), None
    if path.startswith('/api/company-related/'):
        if method not in ('GET', 'HEAD'):
            return 405, {'error': 'Method not allowed'}, None
        uniform = path[len('/api/company-related/'):]
        if not re.fullmatch(r'[0-9]{8}', uniform):
            return 400, {'error': '統編必須是 8 碼數字。'}, None
        try:
            result = related_companies(uniform)
        except RuntimeError:
            return 503, {'status': 'unavailable', 'error': '官方公司登記暫時無法查詢。'}, None
        return (200 if result else 404), result or {'status': 'not_found', 'items': []}, None
    if path.startswith('/api/company/') or path == '/api/company-sources':
        uniform = path[len('/api/company/'):] if path.startswith('/api/company/') else query.get('uniform', [''])[0]
        if not re.fullmatch(r'[0-9]{8}', uniform):
            return 400, {'status': 'error', 'error': '統編必須是 8 碼數字。'}, None
        data = core.build_company(uniform)
        return (404 if data.get('status') == 'not_found' else 200), data if path != '/api/company-sources' else {'status':data['status'],'sources':data['evidence_status']}, None
    return 404, {'status': 'error', 'error': 'Not found'}, None

def app(environ, start_response):
    started = time.monotonic()
    method = environ.get('REQUEST_METHOD', 'GET').upper()
    path = environ.get('PATH_INFO', '/')
    request_id = environ.get('HTTP_X_VERCEL_ID') or str(uuid.uuid4())
    try:
        client = client_identity(environ)
        if not request_allowed(path, client):
            code, payload, content_type = 429, {
                'status': 'error', 'error': '請稍後再試 / Too many requests'}, None
        else:
            code = None
        request_payload = None
        private_write = (path.rstrip('/').startswith('/api/v1/workspaces')
                         or path.rstrip('/').startswith('/api/v1/watchlist')
                         or path.rstrip('/').startswith('/api/v1/alerts'))
        if code is None and private_write and method in ('POST', 'PATCH'):
            length = int(environ.get('CONTENT_LENGTH') or 0)
            if length <= 0 or length > 65536:
                raise ValueError('Invalid request body length')
            request_payload = json.loads(environ.get('wsgi.input').read(length))
        if code is None:
            code, payload, content_type = dispatch(
                path, parse_qs(environ.get('QUERY_STRING', '')),
                method, request_payload, environ.get('HTTP_AUTHORIZATION'))
    except (ValueError, json.JSONDecodeError) as exc:
        code, payload, content_type = 400, {'error': 'Invalid JSON request'}, None
        log_event('warning', 'request_rejected', request_id=request_id,
                  method=method, path=path, error_type=type(exc).__name__)
    except Exception as exc:
        code, payload, content_type = 502, {'status': 'error', 'error': '上游資料來源暫時無法連線，請稍後再試。'}, None
        log_event('error', 'request_failed', request_id=request_id,
                  method=method, path=path, error_type=type(exc).__name__)
    body = payload if isinstance(payload, bytes) else (
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)).encode()
    duration_ms = round((time.monotonic() - started) * 1000, 1)
    log_event('info', 'request_complete', request_id=request_id,
              method=method, path=path, status=code, duration_ms=duration_ms)
    headers = [('Content-Type', content_type or 'application/json; charset=utf-8'),
               ('Cache-Control','no-store'), ('Content-Length',str(len(body))),
               ('X-Content-Type-Options','nosniff'), ('X-Request-Id', request_id)]
    if code == 429:
        headers.append(('Retry-After', '60'))
    if code == 200 and content_type == 'application/pdf':
        # UUID/scopes were validated by the existing report endpoint.
        scope, record_id = path.rstrip('/').split('/')[-2:]
        headers.append(('Content-Disposition', f'attachment; filename="tei-{scope}-{record_id}.pdf"'))
    start_response(f'{code} {HTTPStatus(code).phrase}', headers)
    return [] if environ.get('REQUEST_METHOD') == 'HEAD' else [body]

# Explicit WSGI alias for Vercel's Python entrypoint detector.
application = app

if __name__ == '__main__':
    from wsgiref.simple_server import make_server
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '3000'))
    print(f'T.E.I. local server: http://{host}:{port}', flush=True)
    make_server(host, port, app).serve_forever()
