"""Read-only Development report acceptance; credentials arrive on stdin only.

Input JSON: {"url": ..., "anon_key": ..., "accounts": [{"email": ..., "password": ...}, ...]}.
Never print the input, JWTs, private rows, or connection details.
"""
import json
import os
import sys
import urllib.request
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app
from src.reports import ReportService, dispatch_report_api
from src.workspaces import WorkspaceRepository


def authenticate(url, key, account):
    payload = json.dumps({"email": account["email"], "password": account["password"]}).encode()
    request = urllib.request.Request(
        f"{url}/auth/v1/token?grant_type=password", data=payload, method="POST",
        headers={"apikey": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)["access_token"]


def main():
    inputs = json.loads(sys.stdin.readline())
    url = inputs["url"].rstrip("/")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "canqjiokrtcxkwblhmml.supabase.co"
            or parsed.username or parsed.password or parsed.port or parsed.path
            or parsed.query or parsed.fragment):
        raise ValueError("Target is not the expected Development project")
    if len(inputs["accounts"]) != 2:
        raise ValueError("Exactly two independent accounts are required")
    key = inputs["anon_key"]
    os.environ["TEI_PRIVATE_SUPABASE_URL"] = url
    os.environ["TEI_PRIVATE_SUPABASE_ANON_KEY"] = key
    os.environ["TEI_ENTITY_SUPABASE_URL"] = url
    os.environ["TEI_ENTITY_ANON_KEY"] = key
    tokens = [authenticate(url, key, account) for account in inputs["accounts"]]
    own = WorkspaceRepository(tokens[0]).list()["items"]
    workspace = next((row for row in own if row.get("name", "").startswith("Isolation test1")), None)
    if not workspace:
        raise AssertionError("Expected first-account acceptance Workspace is missing")
    workspace_id = workspace["id"]
    if WorkspaceRepository(tokens[1]).get(workspace_id) is not None:
        raise AssertionError("Second account can read first-account Workspace")
    service = ReportService()
    path = f"/api/v1/reports/workspace/{workspace_id}"
    denied, _, _ = dispatch_report_api(
        path, {"format": ["pdf"]}, authorization=f"Bearer {tokens[1]}")
    if denied != 404:
        raise AssertionError("Second account can generate first-account report")
    report = service.workspace_report(workspace_id, tokens[0])
    expected = ("entity_profiles", "key_relationships", "penalties", "sources")
    counts = {name: len(report[name]) for name in expected}
    if min(counts.values()) < 1 or len(report["workspace_items"]) < 4:
        raise AssertionError("First-account report omits saved public facts")
    status, pdf, mime = dispatch_report_api(
        path, {"format": ["pdf"]}, authorization=f"Bearer {tokens[0]}")
    if status != 200 or mime != "application/pdf":
        raise AssertionError("First-account PDF endpoint failed")
    captured = []
    body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": path,
                         "QUERY_STRING": "format=pdf",
                         "HTTP_AUTHORIZATION": f"Bearer {tokens[0]}"},
                        lambda status_line, headers: captured.append((status_line, dict(headers)))))
    if (not captured or not captured[0][0].startswith("200 ") or
            captured[0][1].get("Content-Type") != "application/pdf" or
            not captured[0][1].get("Content-Disposition", "").endswith('.pdf"') or
            not body.startswith(b"%PDF-")):
        raise AssertionError("WSGI PDF transport or download headers failed")
    reader = PdfReader(BytesIO(pdf))
    if not pdf.startswith(b"%PDF-") or not reader.pages:
        raise AssertionError("Report is not a readable PDF")
    if not all(float(page.mediabox.width) > float(page.mediabox.height) for page in reader.pages):
        raise AssertionError("Report is not landscape on every page")
    text = "".join(page.extract_text() for page in reader.pages)
    if "Sources / 來源" not in text or "Penalties / 裁罰" not in text:
        raise AssertionError("Report PDF omits evidence sections")
    output = inputs.get("pdf_path")
    if output:
        path = Path(output)
        if not path.is_absolute() or not str(path).startswith("/private/tmp/"):
            raise ValueError("PDF output must be under /private/tmp")
        old_umask = os.umask(0o077)
        try:
            with path.open("xb") as output_file:
                output_file.write(pdf)
        finally:
            os.umask(old_umask)
    print(json.dumps({"result": "PASS", "other_account_report": "DENIED",
                      "workspace_items": len(report["workspace_items"]),
                      "sections": counts, "pdf_pages": len(reader.pages),
                      "pdf_bytes": len(pdf)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"result": "FAIL", "error_type": type(error).__name__}))
        raise SystemExit(1)
