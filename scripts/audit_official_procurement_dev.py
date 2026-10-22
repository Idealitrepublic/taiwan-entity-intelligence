#!/usr/bin/env python3
"""Read-only recheck of Development's published awards against PCC pages.

The structured mirror is never accepted as independent official proof. This
check does not publish, alter, or infer new awards; an inaccessible page fails
closed and remains a review task.
"""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_graph_coverage_dev import is_development_target  # noqa: E402
from scripts.audit_p0_data_chain import development_environment, query  # noqa: E402


class TextTokens(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tokens = []
        self.skipped = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skipped += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skipped:
            self.skipped -= 1

    def handle_data(self, text):
        clean = unicodedata.normalize("NFKC", text).strip()
        if clean and not self.skipped:
            self.tokens.append(clean)


def official_row_matches(html, locator):
    parser = TextTokens()
    parser.feed(html)
    tokens = parser.tokens
    identifier = str(locator.get("bidder_uniform_number") or "")
    name = unicodedata.normalize("NFKC", str(locator.get("bidder_name") or "")).strip()
    title = unicodedata.normalize("NFKC", str(locator.get("title") or "")).strip()
    agency = unicodedata.normalize("NFKC", str(locator.get("agency") or "")).strip()
    case = str(locator.get("job_number") or "")
    amount = locator.get("amount")
    if (not re.fullmatch(r"[0-9]{8}", identifier) or not name or not title
            or not agency or not case or not isinstance(amount, int)):
        return False
    # The ID, name and winner flag must appear in one bidder block, not merely
    # somewhere on the same notice page.
    bidder = any(tokens[index:index + 6] == ["廠商代碼", identifier, "廠商名稱", name, "是否得標", "是"]
                 for index in range(max(0, len(tokens) - 5)))
    normalized_amount = str(amount)
    amount_present = any(re.sub(r"[^0-9]", "", token) == normalized_amount for token in tokens)
    return (bidder and title in tokens and agency in tokens and case in tokens
            and amount_present)


def audit():
    if not is_development_target(development_environment()):
        raise RuntimeError("Refusing non-Development database")
    rows = json.loads(query("""select coalesce(jsonb_agg(jsonb_build_object(
        'source_record_id',ev.source_record_id,'url',ev.source_url,
        'locator',ev.source_locator)),'[]'::jsonb)
        from public.relationships r join public.evidence_records ev
          on ev.id=r.primary_evidence_id
        where r.status='published' and r.relationship_type='CONTRACT_WITH';"""))
    checked = []
    for row in rows:
        url = str(row.get("url") or "")
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != "web.pcc.gov.tw"
                or not parsed.path.endswith("/QueryAtmAwardDetailHist") or not parsed.query):
            checked.append({"source_record_id": row.get("source_record_id"), "status": "invalid_official_locator"})
            continue
        try:
            result = subprocess.run(["curl", "-L", "--fail", "--silent", "--show-error",
                                     "--max-time", "20", url], capture_output=True,
                                    text=True, timeout=22)
            if result.returncode == 0 and ("驗證碼檢核" in result.stdout or "撲克牌" in result.stdout):
                status = "official_captcha_manual_review_required"
            elif result.returncode == 0 and official_row_matches(result.stdout, row.get("locator") or {}):
                status = "verified_official_row"
            else:
                status = "official_row_unavailable_or_mismatch"
        except (OSError, subprocess.TimeoutExpired):
            status = "official_row_unavailable_or_mismatch"
        checked.append({"source_record_id": row.get("source_record_id"), "status": status})
    return {"environment": "tei-development", "published_awards": len(rows),
            "official_rows_verified": sum(row["status"] == "verified_official_row" for row in checked),
            "items": checked}


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False))
