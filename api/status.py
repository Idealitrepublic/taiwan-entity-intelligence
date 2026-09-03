from __future__ import annotations

import json
import os



def handler(request):
    if (request or {}).get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,OPTIONS",
                "Access-Control-Allow-Headers": "content-type, authorization, apikey",
            },
            "body": "",
        }

    supabase_configured = bool(
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("VITE_SUPABASE_ANON_KEY")
    )
    payload = {
        "status": "ok",
        "version": "6.3-core-isolated",
        "supabase": {"configured": supabase_configured},
        "routes": ["/api/status", "/api/company/{uniform}", "/api/company-sources"],
        "source_mode": "MOEA core on Vercel; optional evidence on Supabase",
    }
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(payload, ensure_ascii=False),
    }
