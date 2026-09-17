"""Canonical WSGI entrypoint shared by every Vercel domain."""
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs
from http import HTTPStatus
from concurrent.futures import ThreadPoolExecutor
import urllib.request
from src import cloud_company as core
from src.sources.procurement import lookup_awards
from src.entities.api import dispatch_entity_api
from src.public_config import SUPABASE_PUBLISHABLE_KEY
from src.workspaces import dispatch_workspace_api

WEB = Path(__file__).parent / 'web'

def db_count(table):
    req = urllib.request.Request(f'{core.SUPABASE}/rest/v1/{table}?select=*', method='HEAD', headers={'apikey': core.SUPABASE_KEY, 'Authorization': f'Bearer {core.SUPABASE_KEY}', 'Prefer': 'count=exact'})
    with urllib.request.urlopen(req, timeout=8) as response:
        return int(response.headers['Content-Range'].split('/')[-1])

def workspace_public_config():
    url = os.environ.get('TEI_ENTITY_SUPABASE_URL') or os.environ.get(
        'SUPABASE_URL', 'https://rztdbdurkjfrirsrrhtu.supabase.co')
    key = os.environ.get('TEI_ENTITY_ANON_KEY') or os.environ.get('SUPABASE_ANON_KEY')
    if not key and url.rstrip('/') == 'https://rztdbdurkjfrirsrrhtu.supabase.co':
        key = SUPABASE_PUBLISHABLE_KEY
    return {'supabase_url': url, 'publishable_key': key, 'auth_enabled': bool(url and key)}


def dispatch(path, query, method='GET', payload=None, authorization=None):
    if path.rstrip('/') == '/api/v1/workspace-config':
        if method not in ('GET', 'HEAD'):
            return 405, {'error': 'Method not allowed'}, None
        return 200, workspace_public_config(), None
    if path.rstrip('/').startswith('/api/v1/workspaces'):
        return dispatch_workspace_api(
            'GET' if method == 'HEAD' else method, path, payload, authorization)
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
        db = {'configured': bool(core.SUPABASE_KEY), 'connected': False}
        if core.SUPABASE_KEY:
            try:
                tables = ['source_files', 'companies', 'people', 'evidence', 'source_records']
                with ThreadPoolExecutor(max_workers=4) as pool:
                    db.update(zip(tables, pool.map(db_count, tables)))
                db['connected'] = True
            except Exception:
                db['error'] = '資料庫連線失敗，請檢查伺服器金鑰與資料表權限。'
        return (200 if db['connected'] else 503), {'status': 'ok' if db['connected'] else 'degraded', 'version': '9.3-directional-filters', 'supabase': db}, None
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
    if path.startswith('/api/company/') or path == '/api/company-sources':
        uniform = path[len('/api/company/'):] if path.startswith('/api/company/') else query.get('uniform', [''])[0]
        if not re.fullmatch(r'[0-9]{8}', uniform):
            return 400, {'status': 'error', 'error': '統編必須是 8 碼數字。'}, None
        data = core.build_company(uniform)
        return (404 if data.get('status') == 'not_found' else 200), data if path != '/api/company-sources' else {'status':data['status'],'sources':data['evidence_status']}, None
    return 404, {'status': 'error', 'error': 'Not found'}, None

def app(environ, start_response):
    try:
        method = environ.get('REQUEST_METHOD', 'GET').upper()
        path = environ.get('PATH_INFO', '/')
        request_payload = None
        if path.rstrip('/').startswith('/api/v1/workspaces') and method in ('POST', 'PATCH'):
            length = int(environ.get('CONTENT_LENGTH') or 0)
            if length <= 0 or length > 65536:
                raise ValueError('Invalid request body length')
            request_payload = json.loads(environ.get('wsgi.input').read(length))
        code, payload, content_type = dispatch(
            path, parse_qs(environ.get('QUERY_STRING', '')),
            method, request_payload, environ.get('HTTP_AUTHORIZATION'))
    except (ValueError, json.JSONDecodeError):
        code, payload, content_type = 400, {'error': 'Invalid JSON request'}, None
    except Exception:
        code, payload, content_type = 502, {'status': 'error', 'error': '上游資料來源暫時無法連線，請稍後再試。'}, None
    body = (payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)).encode()
    start_response(f'{code} {HTTPStatus(code).phrase}', [('Content-Type', content_type or 'application/json; charset=utf-8'), ('Cache-Control','no-store'), ('Content-Length',str(len(body))), ('X-Content-Type-Options','nosniff')])
    return [] if environ.get('REQUEST_METHOD') == 'HEAD' else [body]

# Explicit WSGI alias for Vercel's Python entrypoint detector.
application = app

if __name__ == '__main__':
    from wsgiref.simple_server import make_server
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '3000'))
    print(f'T.E.I. local server: http://{host}:{port}', flush=True)
    make_server(host, port, app).serve_forever()
