"""Publish source-scoped EY minister roster observations, never global people.

Only factual name/office/profile URL fields are retained, without photographs,
biographies, contact data, inferred terms or name-based cross-source links.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ingest_civil_organizations_dev import apply_bundles  # noqa: E402
from src.entities.models import Entity, evidence_from_projection, stable_id  # noqa: E402

SOURCE = "行政院部會首長名錄（來源觀察）"
URL = "https://www.ey.gov.tw/Page/7AC6136EBB87A125"
ROLES = r"代理主任委員|代理委員長|主任委員|部長|主計長|人事長|總裁|院長"


class Cards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.card = None
        self.rows = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "li" and "member_img" in attrs.get("class", ""):
            self.card = {"text": []}
        if self.card is not None and tag == "a":
            self.card.update(url=attrs.get("href"), title=attrs.get("title"))

    def handle_data(self, value):
        if self.card is not None and value.strip():
            self.card["text"].append(value.strip())

    def handle_endtag(self, tag):
        if tag == "li" and self.card is not None:
            self.rows.append(self.card)
            self.card = None


def build(payload, *, retrieved_at, expected_rows=31):
    digest = hashlib.sha256(payload).hexdigest()
    cards = Cards()
    cards.feed(payload.decode("utf-8"))
    if len(cards.rows) != expected_rows or not cards.rows:
        raise ValueError("Official roster count changed; review required")
    bundle = {key: [] for key in ("entities", "identifiers", "evidence", "entity_evidence", "relationships", "relationship_evidence", "legacy_map")}
    agencies = set()
    for index, row in enumerate(cards.rows, 1):
        if len(row["text"]) != 2:
            raise ValueError("Official name/office fields changed")
        agency, label = row["text"]
        match = re.fullmatch(r"(.+?)\s*(" + ROLES + r")", label)
        parsed = urlsplit(row.get("url") or "")
        if (not match or agency in agencies or parsed.scheme != "https" or parsed.username or parsed.password
                or not ((parsed.hostname or "").endswith(".gov.tw") or parsed.hostname == "www.edu.tw")):
            raise ValueError("Ambiguous office, role or unofficial profile URL")
        agencies.add(agency)
        name, role = match.groups()
        record_id = f"ey-ministers:{digest}:row:{index}"
        entity = Entity(id=stable_id("entity", "ey:minister-roster-observation", record_id),
                        entity_type="GovernmentOfficial", canonical_name=name.strip(), display_name=name.strip(),
                        source=SOURCE, source_id=record_id, identity_status="SOURCE_SCOPED", publication_status="published")
        proof = evidence_from_projection(source_name=SOURCE, source_record_id=record_id,
            source_class="Primary Source", source_url=URL,
            source_locator={"snapshot_sha256": digest, "source_row": index, "agency": agency, "role": role,
                            "profile_url": row["url"], "identity_scope": "official_roster_observation_only",
                            "term_start": None, "term_end": None, "observed_at": retrieved_at},
            title=f"行政院名錄：{agency}｜{name.strip()}｜{role}",
            summary=f"官方名錄於取得時列示：{agency} {name.strip()} {role}。僅為來源觀察，未與同名人物合併；任期日期未提供。",
            observed_at=retrieved_at, retrieved_at=retrieved_at, publication_status="published")
        bundle["entities"].append(entity.to_dict())
        bundle["evidence"].append(proof.to_dict())
        bundle["entity_evidence"].append({"entity_id": entity.id, "evidence_id": proof.id, "fact_type": "official_position_observation"})
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html_path", type=Path)
    parser.add_argument("--apply-dev", action="store_true")
    args = parser.parse_args()
    path = args.html_path.resolve()
    if path.is_relative_to(ROOT) or path.stat().st_mode & 0o077:
        parser.error("Use an owner-only official snapshot outside the repository")
    bundle = build(path.read_bytes(), retrieved_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
    if args.apply_dev:
        apply_bundles([bundle], source_name=SOURCE)
    print(json.dumps({"applied_to_development": args.apply_dev, "official_roster_observations": len(bundle["entities"]),
                      "relationships_created": 0, "global_person_merges": 0,
                      "scope": "EY minister roster snapshot only; not all public officials"}))


if __name__ == "__main__":
    main()
