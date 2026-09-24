#!/usr/bin/env python3
"""Stage Taipei corporate-donor rows from an official Control Yuan ZIP.

The source has no Legislative Yuan ``lgno``. This intentionally creates only
private draft Evidence, never a politician identity or public Relationship.
Individual donor records and masked personal identifiers are excluded.
"""

import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import io
import json
import re
import subprocess
import zipfile

from src.entities.models import evidence_from_projection


SOURCE_URL = ("https://ardata.cy.gov.tw/api/v1/Search/download?AccountNumber="
              "&DownloadType=3&ElectionArea=%E8%87%BA%E5%8C%97%E5%B8%82"
              "&ElectionName=113%E5%B9%B4%E7%AB%8B%E6%B3%95%E5%A7%94%E5%93%A1%E9%81%B8%E8%88%89"
              "&SearchType=2&Version=&YearOrSerial=1")
SOURCE_NAME = "監察院政治獻金公開查閱平臺"


def records():
    raw = subprocess.check_output(
        ["curl", "--fail", "--silent", "--show-error", "--location", SOURCE_URL],
        timeout=60)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        with archive.open("incomes.csv") as stream:
            yield from csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))


def normalize_row(row, retrieved_at):
    if row.get("收支科目") != "營利事業捐贈收入":
        return None
    uniform = (row.get("身分證／統一編號") or "").strip()
    if not re.fullmatch(r"[0-9]{8}", uniform):
        return None
    serial = (row.get("序號") or "").strip()
    donor = (row.get("捐贈者／支出對象") or "").strip()
    candidate = (row.get("擬參選人／政黨") or "").strip()
    compact_date = (row.get("交易日期") or "").strip()
    try:
        if not re.fullmatch(r"[0-9]{7}", compact_date):
            return None
        transaction_date = date(int(compact_date[:3]) + 1911,
                                int(compact_date[3:5]), int(compact_date[5:]))
        amount = Decimal((row.get("收入金額") or "").strip())
        if not amount.is_finite() or amount <= 0:
            return None
    except (ValueError, InvalidOperation):
        return None
    if not serial or not donor or not candidate:
        return None
    record_id = f"168061:taipei:incomes:{serial}"
    return evidence_from_projection(
        source_name=SOURCE_NAME, source_record_id=record_id,
        source_class="Government Open Data", source_url=SOURCE_URL,
        source_locator={"dataset": "168061", "archive_member": "incomes.csv",
                        "election_area": "臺北市", "election": row.get("選舉名稱"),
                        "filing": row.get("申報序號／年度"), "row_serial": serial,
                        "candidate_name": candidate, "donor_uniform_number": uniform,
                        "resolution_status": "UNRESOLVED"},
        title=f"政治獻金來源紀錄：{donor}",
        summary=f"{donor}（統編 {uniform}）→ {candidate}；{amount} TWD；{transaction_date}",
        observed_at=f"{transaction_date}T00:00:00+08:00",
        retrieved_at=retrieved_at).to_dict()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int)
    parser.add_argument("--count", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    retrieved_at = datetime.now(timezone.utc).isoformat()
    all_rows = list(records())
    evidence = [item for row in all_rows if (item := normalize_row(row, retrieved_at))]
    batches = [evidence[start:start + 100] for start in range(0, len(evidence), 100)]
    if args.count:
        print(len(batches))
    elif args.report:
        print(json.dumps({"source_rows": len(all_rows), "corporate_draft_evidence": len(evidence),
                          "batches": len(batches), "public_relationships": 0,
                          "reason": "candidate source lacks official legislator ID"},
                         ensure_ascii=False))
    elif args.batch is not None and 0 <= args.batch < len(batches):
        print(json.dumps({"entities": [], "identifiers": [], "evidence": batches[args.batch],
                          "entity_evidence": [], "relationships": [],
                          "relationship_evidence": [], "legacy_map": []},
                         ensure_ascii=False, separators=(",", ":")))
    else:
        parser.error("choose --count, --report, or a valid --batch index")


if __name__ == "__main__":
    main()
