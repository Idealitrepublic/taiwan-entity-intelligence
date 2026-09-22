"""Draft-only Legislative Yuan political master-data projection.

People are consolidated across source rows only by the Legislative Yuan's
``lgno``.  A name can help join two rows inside the same official dataset and
term only when that mapping is unique; it is never an identity key by itself.
"""
from datetime import date
from hashlib import sha256
import json
import re
import unicodedata

from src.entities.models import Entity, evidence_from_projection, stable_id, timestamp
from src.relationships.models import Relationship

SOURCE_NAME = "立法院開放資料服務平台"
MEMBER_DATASET_URL = "https://data.ly.gov.tw/getds.action?id=16"
COMMITTEE_DATASET_URL = "https://data.ly.gov.tw/getds.action?id=14"
LEGISLATURE_URL = "https://www.ly.gov.tw/"
LEGISLATOR_NUMBER_NAMESPACE = "tw:legislative_yuan:legislator_number"


def _text(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _integer(value, *, minimum=1, maximum=99):
    normalized = _text(value)
    if not normalized.isdigit():
        raise ValueError("integer field is required")
    number = int(normalized)
    if not minimum <= number <= maximum:
        raise ValueError("integer field is outside the allowed range")
    return number


def _source_date(value, *, required=False):
    normalized = _text(value).replace("/", "-")
    if not normalized:
        if required:
            raise ValueError("source date is required")
        return None
    return date.fromisoformat(normalized).isoformat()


def _legislator_number(value):
    normalized = _text(value)
    if not re.fullmatch(r"[0-9]{4,8}", normalized):
        raise ValueError("invalid Legislative Yuan legislator number")
    return normalized


def _constituency_type(value):
    normalized = _text(value)
    if "不分區" in normalized or "僑居國外" in normalized:
        return "proportional"
    if "原住民" in normalized:
        return "indigenous"
    if "選舉區" in normalized:
        return "district"
    return "unknown"


def _record_fingerprint(*values):
    payload = json.dumps([_text(value) for value in values], ensure_ascii=False,
                         separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()[:24]


def _entity_value(entity, key):
    return entity.get(key) if isinstance(entity, dict) else getattr(entity, key)


def _empty_bundle():
    return {"entities": [], "identifiers": [], "evidence": [],
            "entity_evidence": [], "relationships": [],
            "relationship_evidence": [], "legacy_map": [],
            "politician_terms": []}


def _dedupe(bundle):
    for key in ("entities", "evidence", "relationships", "politician_terms"):
        bundle[key] = list({item["id"]: item for item in bundle[key]}.values())
    bundle["identifiers"] = list({(item["namespace"], item["value"]): item
                                  for item in bundle["identifiers"]}.values())
    bundle["entity_evidence"] = list({
        (item["entity_id"], item["evidence_id"], item["fact_type"]): item
        for item in bundle["entity_evidence"]}.values())
    bundle["relationship_evidence"] = list({
        (item["relationship_id"], item["evidence_id"]): item
        for item in bundle["relationship_evidence"]}.values())


def _evidence_group(bundle, evidence_id):
    relationships = [item for item in bundle["relationships"]
                     if item["primary_evidence_id"] == evidence_id]
    relationship_ids = {item["id"] for item in relationships}
    terms = [item for item in bundle["politician_terms"]
             if item["primary_evidence_id"] == evidence_id]
    entity_evidence = [item for item in bundle["entity_evidence"]
                       if item["evidence_id"] == evidence_id]
    entity_ids = {item["entity_id"] for item in entity_evidence}
    for item in relationships:
        entity_ids.update((item["source_entity_id"], item["target_entity_id"]))
    for item in terms:
        entity_ids.add(item["politician_entity_id"])
        if item.get("party_entity_id"):
            entity_ids.add(item["party_entity_id"])
    return {
        "entities": [item for item in bundle["entities"] if item["id"] in entity_ids],
        "identifiers": [item for item in bundle["identifiers"]
                        if item["entity_id"] in entity_ids],
        "evidence": [item for item in bundle["evidence"] if item["id"] == evidence_id],
        "entity_evidence": entity_evidence,
        "relationships": relationships,
        "relationship_evidence": [item for item in bundle["relationship_evidence"]
                                  if item["relationship_id"] in relationship_ids],
        "legacy_map": [],
        "politician_terms": terms,
    }


def _merge_group(batch, group):
    merged = {key: [*batch[key], *group[key]] for key in batch}
    _dedupe(merged)
    return merged


def political_master_batches(bundle, *, max_bytes=900_000):
    """Split a complete projection into dependency-complete RPC-safe batches."""
    if not 1 <= max_bytes <= 1_000_000:
        raise ValueError("Batch byte limit must be between 1 and 1,000,000")
    batches = []
    current = _empty_bundle()
    for evidence in bundle["evidence"]:
        group = _evidence_group(bundle, evidence["id"])
        candidate = _merge_group(current, group)
        oversized = (
            len(candidate["entities"]) > 200
            or len(candidate["relationships"]) > 200
            or len(candidate["evidence"]) > 400
            or len(candidate["politician_terms"]) > 200
            or len(json.dumps(candidate, ensure_ascii=False).encode()) > max_bytes
        )
        if oversized and current["evidence"]:
            batches.append(current)
            current = _merge_group(_empty_bundle(), group)
        else:
            current = candidate
        if (len(current["entities"]) > 200 or len(current["relationships"]) > 200
                or len(current["evidence"]) > 400
                or len(current["politician_terms"]) > 200
                or len(json.dumps(current, ensure_ascii=False).encode()) > max_bytes):
            raise ValueError("One political master source group exceeds ingestion limits")
    if current["evidence"]:
        batches.append(current)
    return batches


def build_political_master_batches(member_rows, committee_rows, *, retrieved_at,
                                   max_bytes=900_000):
    bundle, report = build_political_master_bundle(
        member_rows, committee_rows, retrieved_at=retrieved_at)
    batches = political_master_batches(bundle, max_bytes=max_bytes)
    report["batch_count"] = len(batches)
    report["batch_counts"] = [{key: len(value) for key, value in batch.items()}
                              for batch in batches]
    return batches, report


def build_political_master_bundle(member_rows, committee_rows, *, retrieved_at):
    """Build a bounded, reviewable ingestion bundle from official LY rows."""
    retrieved = timestamp(retrieved_at)
    bundle = _empty_bundle()
    report = {
        "publication_status": "draft",
        "matching_strategy": "exact_lgno_or_source_scoped_record",
        "quality_issues": [],
        "skipped": [],
        "input_counts": {"members": len(member_rows), "committee_memberships": len(committee_rows)},
    }

    committee_numbers = {}
    valid_committee_rows = []
    for index, row in enumerate(committee_rows):
        try:
            term = _integer(row.get("term"))
            session = _integer(row.get("sessionPeriod"), maximum=20)
            number = _legislator_number(row.get("lgno"))
            name = _text(row.get("name"))
            committee = _text(row.get("committee"))
            if not name or not committee:
                raise ValueError("committee row requires name and committee")
        except (TypeError, ValueError):
            report["skipped"].append({"dataset": 14, "row": index,
                                      "reason": "invalid_committee_fields"})
            continue
        key = (term, name.casefold())
        committee_numbers.setdefault(key, set()).add(number)
        valid_committee_rows.append((row, term, session, number, name, committee))

    politician_by_number = {}
    politician_by_term_name = {}
    entity_names = {}
    legislature = Entity(
        id=stable_id("entity", "ly:government-agency", "legislative-yuan"),
        entity_type="GovernmentAgency", canonical_name="立法院", display_name="立法院",
        source=SOURCE_NAME, source_id="government-agency:legislative-yuan",
        identity_status="EXACT")
    bundle["entities"].append(legislature.to_dict())

    for index, row in enumerate(member_rows):
        try:
            term = _integer(row.get("term"))
            name = _text(row.get("name"))
            constituency = _text(row.get("areaName"))
            start_date = _source_date(row.get("onboardDate"), required=True)
            end_date = _source_date(row.get("leaveDate"))
            if not name or not constituency:
                raise ValueError("member row requires name and constituency")
            if end_date and end_date < start_date:
                raise ValueError("leave date precedes onboard date")
        except (TypeError, ValueError):
            report["skipped"].append({"dataset": 16, "row": index,
                                      "reason": "invalid_member_fields"})
            continue

        number_set = committee_numbers.get((term, name.casefold()), set())
        number = next(iter(number_set)) if len(number_set) == 1 else None
        if len(number_set) > 1:
            report["quality_issues"].append({
                "severity": "high", "type": "ambiguous_legislator_number",
                "term": term, "name": name, "values": sorted(number_set)})
        if number:
            source_record_id = f"member:{term}:{number}"
            entity_id = stable_id("entity", LEGISLATOR_NUMBER_NAMESPACE, number)
            identity_status = "EXACT"
        else:
            fingerprint = _record_fingerprint(term, name, start_date, constituency)
            source_record_id = f"member:{term}:source-scoped:{fingerprint}"
            entity_id = stable_id("entity", "ly:member-record", source_record_id)
            identity_status = "SOURCE_SCOPED"
            report["quality_issues"].append({
                "severity": "medium", "type": "missing_legislator_number",
                "term": term, "name": name, "source_record_id": source_record_id})

        previous_name = entity_names.setdefault(entity_id, name)
        if previous_name != name:
            report["quality_issues"].append({
                "severity": "high", "type": "identifier_name_conflict",
                "legislator_number": number, "names": sorted({previous_name, name})})
            report["skipped"].append({"dataset": 16, "row": index,
                                      "reason": "identifier_name_conflict"})
            continue

        politician = Entity(
            id=entity_id, entity_type="Politician", canonical_name=name,
            display_name=name, source=SOURCE_NAME,
            source_id=(f"legislator:{number}" if number else source_record_id),
            identity_status=identity_status)
        politician_by_term_name[(term, name.casefold())] = politician
        if number:
            politician_by_number[number] = politician
            bundle["identifiers"].append({
                "entity_id": politician.id, "namespace": LEGISLATOR_NUMBER_NAMESPACE,
                "value": number})

        party_name = _text(row.get("party"))
        party = None
        if party_name:
            party_key = party_name.casefold()
            party = Entity(
                id=stable_id("entity", "ly:political-party-label", party_key),
                entity_type="PoliticalParty", canonical_name=party_name,
                display_name=party_name, source=SOURCE_NAME,
                source_id=f"political-party-label:{party_key}",
                identity_status="SOURCE_SCOPED")
            bundle["entities"].append(party.to_dict())

        observed = f"{start_date}T00:00:00+00:00"
        member_evidence = evidence_from_projection(
            source_name=SOURCE_NAME, source_record_id=source_record_id,
            source_class="Government Open Data", source_url=MEMBER_DATASET_URL,
            source_locator={"dataset_id": 16, "term": term,
                            "legislator_number": number,
                            "source_record_id": source_record_id},
            title=f"第{term}屆立法委員：{name}",
            summary=(f"{name}；{party_name or '黨籍未提供'}；{constituency}；"
                     f"到職 {start_date}" + (f"；離職 {end_date}" if end_date else "")),
            observed_at=observed, retrieved_at=retrieved)
        bundle["entities"].append(politician.to_dict())
        bundle["evidence"].append(member_evidence.to_dict())
        bundle["entity_evidence"].append({
            "entity_id": politician.id, "evidence_id": member_evidence.id,
            "fact_type": "political_master_profile"})

        term_record = {
            "id": stable_id("politician-term", SOURCE_NAME, source_record_id),
            "politician_entity_id": politician.id, "term_number": term,
            "constituency": constituency,
            "constituency_type": _constituency_type(constituency),
            "party_entity_id": party.id if party else None,
            "legislator_number": number, "start_date": start_date,
            "end_date": end_date, "primary_evidence_id": member_evidence.id,
            "source_name": SOURCE_NAME, "source_record_id": source_record_id,
            "publication_status": "draft",
        }
        bundle["politician_terms"].append(term_record)

        targets = [(legislature, "LEGISLATOR_OF", f"term:{term}")]
        if party:
            targets.append((party, "MEMBER_OF", f"term:{term}"))
        for target, relationship_type, source_role in targets:
            relationship = Relationship(
                id=stable_id("relationship", "ly:political-master",
                             f"{source_record_id}:{relationship_type}:{target.id}"),
                source_entity_id=politician.id, target_entity_id=target.id,
                relationship_type=relationship_type,
                primary_evidence_id=member_evidence.id, observed_at=observed,
                confidence="EXACT", start_date=start_date, end_date=end_date,
                date_precision="day", source_role=source_role)
            bundle["relationships"].append(relationship.to_dict())
            bundle["relationship_evidence"].append({
                "relationship_id": relationship.id, "evidence_id": member_evidence.id,
                "support_type": "supports"})

    for index, (row, term, session, number, name, committee_name) in enumerate(valid_committee_rows):
        politician = politician_by_number.get(number)
        if politician is None:
            candidate = politician_by_term_name.get((term, name.casefold()))
            if candidate and _entity_value(candidate, "identity_status") == "EXACT":
                politician = candidate
        if politician is None:
            report["skipped"].append({
                "dataset": 14, "row": index, "reason": "unmatched_committee_member",
                "legislator_number": number})
            continue
        committee_key = committee_name.casefold()
        committee = Entity(
            id=stable_id("entity", "ly:committee-label", committee_key),
            entity_type="GovernmentAgency", canonical_name=committee_name,
            display_name=committee_name, source=SOURCE_NAME,
            source_id=f"committee-label:{committee_key}",
            identity_status="SOURCE_SCOPED")
        record_id = f"committee:{term}:{session}:{number}:{_record_fingerprint(committee_name)}"
        evidence = evidence_from_projection(
            source_name=SOURCE_NAME, source_record_id=record_id,
            source_class="Government Open Data", source_url=COMMITTEE_DATASET_URL,
            source_locator={"dataset_id": 14, "term": term, "session_period": session,
                            "legislator_number": number, "committee": committee_name,
                            "source_record_id": record_id},
            title=f"第{term}屆第{session}會期委員會：{name}",
            summary=(f"{name}；{committee_name}；第{term}屆第{session}會期；"
                     f"召集委員：{'是' if _text(row.get('isCoChairman')).upper() == 'Y' else '否'}"),
            observed_at=retrieved, retrieved_at=retrieved)
        relationship = Relationship(
            id=stable_id("relationship", "ly:committee-membership", record_id),
            source_entity_id=politician.id, target_entity_id=committee.id,
            relationship_type="COMMITTEE_MEMBER", primary_evidence_id=evidence.id,
            observed_at=retrieved, confidence="EXACT",
            source_role=(f"term:{term};session:{session};co_chair:"
                         f"{'Y' if _text(row.get('isCoChairman')).upper() == 'Y' else 'N'}"))
        bundle["entities"].append(committee.to_dict())
        bundle["evidence"].append(evidence.to_dict())
        bundle["entity_evidence"].append({
            "entity_id": committee.id, "evidence_id": evidence.id,
            "fact_type": "committee_membership_roster"})
        bundle["relationships"].append(relationship.to_dict())
        bundle["relationship_evidence"].append({
            "relationship_id": relationship.id, "evidence_id": evidence.id,
            "support_type": "supports"})

    _dedupe(bundle)
    report["counts"] = {key: len(value) for key, value in bundle.items()}
    report["quality"] = {
        "member_acceptance_rate": (report["counts"]["politician_terms"] / len(member_rows)
                                   if member_rows else 1.0),
        "exact_identifier_rate": (sum(
            item.get("legislator_number") is not None
            for item in bundle["politician_terms"]) /
                                  report["counts"]["politician_terms"]
                                  if report["counts"]["politician_terms"] else 0.0),
        "committee_relationship_rate": (sum(
            item["relationship_type"] == "COMMITTEE_MEMBER"
            for item in bundle["relationships"]) / len(committee_rows)
            if committee_rows else 1.0),
    }
    return bundle, report
