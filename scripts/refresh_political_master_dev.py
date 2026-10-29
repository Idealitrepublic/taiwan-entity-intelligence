"""Review an official LY refresh without overwriting published history.

Inputs are private local snapshots. Changed published facts stop the refresh;
new exact-ID committee observations and dated member re-verifications can be
published to Development only. No identity is inferred from a name alone.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ingest_civil_organizations_dev import development_environment  # noqa: E402
from src.entities.models import evidence_from_projection  # noqa: E402
from src.political_master import build_political_master_bundle  # noqa: E402

FIELDS = {
    "entities": ("entity_type", "canonical_name", "display_name", "source", "source_id", "identity_status"),
    "evidence": ("content_hash",),
    "politician_terms": ("politician_entity_id", "term_number", "constituency", "constituency_type",
                         "party_entity_id", "legislator_number", "start_date", "end_date", "primary_evidence_id"),
    "relationships": ("source_entity_id", "target_entity_id", "relationship_type", "primary_evidence_id",
                      "confidence", "start_date", "end_date", "date_precision", "source_role"),
}


def plan_refresh(bundle, before, *, snapshot_hash, retrieved_at):
    if len(snapshot_hash) != 64 or any(c not in "0123456789abcdef" for c in snapshot_hash):
        raise ValueError("Invalid official snapshot hash")
    day = datetime.fromisoformat(retrieved_at).date().isoformat()
    old = {key: {row["id"]: row for row in before[key]} for key in FIELDS}
    fresh = deepcopy(bundle)
    for key, fields in FIELDS.items():
        for row in bundle[key]:
            previous = old[key].get(row["id"])
            if previous and any(row.get(field) != previous.get(field) for field in fields):
                raise ValueError(f"Changed {key} requires a reviewed correction")
        fresh[key] = [row for row in fresh[key] if row["id"] not in old[key]]
    # Unidentified members remain unpublished. Committee rows require an exact
    # official legislator ID and already published source/target identities.
    publishable = {key for key, row in old["entities"].items()
                   if row.get("publication_status") == "published"}
    fresh["entities"] = [row for row in fresh["entities"]
                         if row["entity_type"] != "Politician" or row["identity_status"] == "EXACT"]
    publishable.update(row["id"] for row in fresh["entities"])
    fresh["relationships"] = [row for row in fresh["relationships"]
                              if row["source_entity_id"] in publishable
                              and row["target_entity_id"] in publishable
                              and row["confidence"] == "EXACT"]
    fresh["politician_terms"] = [row for row in fresh["politician_terms"]
                                if row.get("legislator_number") and row["politician_entity_id"] in publishable]
    used = {row[key] for row in fresh["relationships"] for key in ("source_entity_id", "target_entity_id")}
    used.update(row["politician_entity_id"] for row in fresh["politician_terms"])
    used.update(row["party_entity_id"] for row in fresh["politician_terms"] if row.get("party_entity_id"))
    fresh["entities"] = [row for row in fresh["entities"] if row["id"] in used]
    required = {row["primary_evidence_id"] for row in fresh["relationships"] + fresh["politician_terms"]}
    fresh["evidence"] = [row for row in fresh["evidence"] if row["id"] in required]
    new_evidence = {row["id"] for row in fresh["evidence"]}
    new_relationships = {row["id"] for row in fresh["relationships"]}
    fresh["entity_evidence"] = [row for row in fresh["entity_evidence"]
                                if row["evidence_id"] in new_evidence and row["entity_id"] in publishable]
    fresh["relationship_evidence"] = [row for row in fresh["relationship_evidence"]
                                      if row["relationship_id"] in new_relationships]
    fresh["identifiers"] = [row for row in fresh["identifiers"]
                            if row["entity_id"] in {item["id"] for item in fresh["entities"]}]
    fresh["legacy_map"] = []
    verified = 0
    for term in bundle["politician_terms"]:
        member = old["entities"].get(term["politician_entity_id"], {})
        if not (term.get("legislator_number") and member.get("publication_status") == "published"
                and member.get("identity_status") == "EXACT"):
            continue
        proof = next(row for row in bundle["evidence"] if row["id"] == term["primary_evidence_id"])
        checked = evidence_from_projection(
            source_name=proof["source_name"], source_record_id=f"verification:{proof['source_record_id']}:{day}",
            source_class=proof["source_class"], source_url=proof["source_url"],
            source_locator={**proof["source_locator"], "snapshot_sha256": snapshot_hash,
                            "verified_on": day, "verified_evidence_id": proof["id"],
                            "match_method": "unchanged_fact_exact_official_identifier"},
            title=proof["title"], summary=proof["summary"], observed_at=proof["observed_at"],
            retrieved_at=retrieved_at).to_dict()
        verified += 1
        if checked["id"] in old["evidence"]:
            continue
        fresh["evidence"].append(checked)
        fresh["entity_evidence"].append({"entity_id": member["id"], "evidence_id": checked["id"],
                                         "fact_type": "political_master_verification"})
        for relationship in old["relationships"].values():
            if relationship["primary_evidence_id"] == proof["id"]:
                fresh["relationship_evidence"].append({"relationship_id": relationship["id"],
                                                        "evidence_id": checked["id"], "support_type": "supports"})
    if len(fresh["evidence"]) > 400 or len(fresh["relationships"]) > 200 or len(fresh["entities"]) > 200:
        raise ValueError("Refresh exceeds bounded transaction limits")
    return fresh, {"verified_exact_members": verified, "new_rows": {k: len(v) for k, v in fresh.items()},
                   "name_only_publications": 0, "published_history_overwritten": 0}


def transaction(bundle):
    literal = json.dumps(bundle, ensure_ascii=False).replace("'", "''")
    def ids(key):
        return "ARRAY[" + ",".join("'" + row["id"] + "'::uuid" for row in bundle[key]) + "]::uuid[]"
    return ("BEGIN; SET LOCAL standard_conforming_strings=on; "
            "SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='90s'; "
            "DO $$BEGIN IF pg_database_size(current_database()) > 480000000 THEN "
            "RAISE EXCEPTION 'Development capacity guard'; END IF; END$$; SET LOCAL ROLE service_role; "
            f"SELECT public.tei_ingest_political_master_bundle('{literal}'::jsonb); "
            f"UPDATE public.entities SET publication_status='published' WHERE id=ANY({ids('entities')}) AND publication_status='draft'; "
            f"UPDATE public.evidence_records SET publication_status='published' WHERE id=ANY({ids('evidence')}) AND publication_status='draft'; "
            f"UPDATE public.politician_terms SET publication_status='published' WHERE id=ANY({ids('politician_terms')}) AND publication_status='draft'; "
            f"UPDATE public.relationships SET status='published' WHERE id=ANY({ids('relationships')}) AND status='draft'; "
            "SET CONSTRAINTS ALL IMMEDIATE; COMMIT;")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_directory", type=Path)
    parser.add_argument("--apply-dev", action="store_true")
    args = parser.parse_args()
    folder = args.snapshot_directory.resolve()
    if folder.is_relative_to(ROOT) or folder.stat().st_mode & 0o077:
        parser.error("Snapshots must be in an owner-only directory outside the repository")
    before = json.loads((folder / "development_before.json").read_text())
    members = json.loads((folder / "members.json").read_text())
    committees = json.loads((folder / "committees.json").read_text())
    stamp = datetime.fromtimestamp((folder / "members.json").stat().st_mtime, timezone.utc).isoformat()
    digest = hashlib.sha256((folder / "members.json").read_bytes()).hexdigest()
    bundle, quality = build_political_master_bundle(members, [r for r in committees if str(r.get("term")) == "11"], retrieved_at=stamp)
    if quality["skipped"] or any(row["severity"] == "high" for row in quality["quality_issues"]):
        parser.error("Official snapshot requires manual review")
    plan, report = plan_refresh(bundle, before, snapshot_hash=digest, retrieved_at=stamp)
    if args.apply_dev:
        result = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"],
                                input=transaction(plan), text=True, capture_output=True,
                                env=development_environment(), timeout=180)
        if result.returncode:
            raise RuntimeError("Development refresh rolled back; connection details suppressed")
    report.update(applied_to_development=args.apply_dev, retrieved_at=stamp, snapshot_sha256=digest,
                  source_member_rows=len(members), source_committee_rows=quality["input_counts"]["committee_memberships"])
    path = folder / "refresh_result.json"
    path.write_text(json.dumps(report, ensure_ascii=False))
    path.chmod(0o600)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
