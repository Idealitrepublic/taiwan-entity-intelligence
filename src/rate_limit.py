"""Small process-local burst guard; Vercel WAF remains the outer rate-limit layer."""
from __future__ import annotations

import threading
import time
import ipaddress
import os


class FixedWindowLimiter:
    def __init__(self, window_seconds=60):
        self.window_seconds = window_seconds
        self._entries = {}
        self._lock = threading.Lock()

    def allow(self, key, limit, now=None):
        now = time.monotonic() if now is None else now
        window = int(now // self.window_seconds)
        with self._lock:
            previous_window, count = self._entries.get(key, (window, 0))
            if previous_window != window:
                count = 0
            if count >= limit:
                return False
            self._entries[key] = (window, count + 1)
            if len(self._entries) > 5000:
                self._entries = {
                    item: value for item, value in self._entries.items()
                    if value[0] >= window - 1
                }
            return True


LIMITER = FixedWindowLimiter()


def client_identity(environ):
    """Use Vercel's overwritten client-IP header, never arbitrary local XFF."""
    candidates = []
    if os.environ.get('VERCEL'):
        candidates.append(environ.get('HTTP_X_VERCEL_FORWARDED_FOR'))
    candidates.append(environ.get('REMOTE_ADDR'))
    for candidate in candidates:
        try:
            return str(ipaddress.ip_address(str(candidate).strip()))
        except ValueError:
            continue
    return 'unknown'


def request_allowed(path, client):
    if not path.startswith('/api/') or path in ('/api/status', '/api/v1/workspace-config'):
        return True
    limit = 120 if path.startswith(('/api/v1/workspaces', '/api/v1/watchlist',
                                    '/api/v1/alerts')) else 60
    route_group = '/'.join(path.split('/', 4)[:4])
    return LIMITER.allow(f'{client}:{route_group}', limit)
