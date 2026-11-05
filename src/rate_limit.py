"""Small process-local burst guard; Vercel WAF remains the outer rate-limit layer."""
from __future__ import annotations

import threading
import time
import ipaddress
import os


class FixedWindowLimiter:
    def __init__(self, window_seconds=60, max_entries=5000):
        if window_seconds <= 0 or max_entries < 1:
            raise ValueError('Limiter window and capacity must be positive')
        self.window_seconds = window_seconds
        self.max_entries = max_entries
        self._entries = {}
        self._pruned_window = None
        self._lock = threading.Lock()

    def allow(self, key, limit, now=None):
        now = time.monotonic() if now is None else now
        window = int(now // self.window_seconds)
        with self._lock:
            if key not in self._entries and len(self._entries) >= self.max_entries:
                if self._pruned_window != window:
                    self._entries = {item: value for item, value in self._entries.items()
                                     if value[0] == window}
                    self._pruned_window = window
                # Preserve existing counters rather than evicting a limited client.
                if len(self._entries) >= self.max_entries:
                    return False
            previous_window, count = self._entries.get(key, (window, 0))
            if previous_window != window:
                count = 0
            if count >= limit:
                return False
            self._entries[key] = (window, count + 1)
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
    # Dynamic IDs and arbitrary unknown paths must not mint fresh rate buckets.
    parts = path.split('/')
    if len(parts) > 3 and parts[2] == 'v1':
        family = parts[3]
        known = {'search', 'paths', 'graph', 'entities', 'relationships', 'evidence',
                 'politicians', 'reports', 'workspaces', 'watchlist', 'alerts'}
        route_group = '/api/v1/' + (family if family in known else 'other')
    else:
        family = parts[2] if len(parts) > 2 else ''
        known = {'company', 'company-sources', 'company-related', 'procurement', 'domain-check'}
        route_group = '/api/' + (family if family in known else 'other')
    return LIMITER.allow(f'{client}:{route_group}', limit)
