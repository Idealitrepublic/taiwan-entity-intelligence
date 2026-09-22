"""Traceable, conservative cross-source Entity resolution.

Names generate review candidates but never resolve identity alone. The engine
does not merge Entities: it emits draft/pending decisions with matching Evidence.
"""
from dataclasses import asdict, dataclass
from datetime import date
import re
import unicodedata

from .models import Entity, stable_id, uuid_string

CONFIDENCE_LEVELS = ("EXACT", "HIGH", "MEDIUM", "LOW", "UNRESOLVED")
ENGINE_VERSION = "tei-resolution-v1"
PUBLISHABLE_CONFIDENCE = {"EXACT", "HIGH"}


@dataclass(frozen=True)
class Resolution:
    entity_id: str | None
    confidence: str
    reason: str


@dataclass(frozen=True)
class ResolutionCandidate:
    id: str
    source_entity_id: str
    candidate_entity_id: str | None
    confidence: str
    score: str
    reason: str
    signals: dict
    evidence_id: str
    matching_evidence_ids: tuple[str, ...]
    engine_version: str = ENGINE_VERSION
    status: str = "pending"

    def __post_init__(self):
        uuid_string(self.id)
        uuid_string(self.source_entity_id)
        if self.candidate_entity_id:
            uuid_string(self.candidate_entity_id)
        for evidence_id in self.matching_evidence_ids:
            uuid_string(evidence_id)
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError("Invalid resolution confidence")
        if not 0 <= float(self.score) <= 1:
            raise ValueError("Resolution score must be between zero and one")
        if self.status != "pending" or not self.reason.strip() or not self.signals:
            raise ValueError("Resolution candidates must be traceable pending decisions")
        if self.evidence_id not in self.matching_evidence_ids:
            raise ValueError("Primary matching Evidence must be retained")

    def to_dict(self):
        item = asdict(self)
        item["matching_evidence_ids"] = list(self.matching_evidence_ids)
        return item


def _text(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def _values(observation, key):
    value = observation.get(key) or []
    return value if isinstance(value, (list, tuple, set)) else [value]


def _identifier_pairs(observation):
    pairs = set()
    for item in _values(observation, "identifiers"):
        if not isinstance(item, dict) or item.get("confidence", "EXACT") != "EXACT":
            continue
        namespace, value = _text(item.get("namespace")), _text(item.get("value"))
        if namespace and value:
            pairs.add((namespace, value))
    return pairs


def _time_overlap(source, candidate):
    if not (source.get("start_date") or source.get("end_date")):
        return False
    if not (candidate.get("start_date") or candidate.get("end_date")):
        return False
    def interval(item):
        start = date.fromisoformat(item["start_date"]) if item.get("start_date") else date.min
        end = date.fromisoformat(item["end_date"]) if item.get("end_date") else date.max
        return start, end
    try:
        source_start, source_end = interval(source)
        candidate_start, candidate_end = interval(candidate)
    except (TypeError, ValueError):
        return False
    return max(source_start, candidate_start) <= min(source_end, candidate_end)


def resolve_identifier(namespace: str, value: str, identifiers: list[dict]) -> Resolution:
    matches = {row["entity_id"] for row in identifiers
               if row["namespace"] == namespace and row["value"] == value
               and row.get("confidence") == "EXACT"}
    if len(matches) == 1:
        return Resolution(matches.pop(), "EXACT", "namespaced_identifier")
    return Resolution(None, "UNRESOLVED",
                      "conflicting_identifiers" if matches else "no_exact_identifier")


def resolve_entity_candidates(source: dict, candidates: list[dict]):
    """Score bounded candidate observations without mutating canonical Entities."""
    source_id = uuid_string(source["entity_id"])
    primary_evidence = uuid_string(source["evidence_id"])
    source_identifiers = _identifier_pairs(source)
    exact_counts = {}
    for candidate in candidates:
        for identifier in source_identifiers & _identifier_pairs(candidate):
            exact_counts[identifier] = exact_counts.get(identifier, 0) + 1

    results = []
    for candidate in candidates:
        candidate_id = uuid_string(candidate["entity_id"])
        if candidate_id == source_id:
            continue
        evidence_ids = tuple(dict.fromkeys(
            [primary_evidence, *[uuid_string(value) for value in
                                 _values(candidate, "evidence_ids") if value]]))
        shared_identifiers = source_identifiers & _identifier_pairs(candidate)
        conflicting_namespaces = {
            left[0] for left in source_identifiers for right in _identifier_pairs(candidate)
            if left[0] == right[0] and left[1] != right[1]}
        signals = {
            "entity_type_match": source.get("entity_type") == candidate.get("entity_type"),
            "normalized_name_match": bool(_text(source.get("name"))) and
                                     _text(source.get("name")) == _text(candidate.get("name")),
            "shared_exact_identifiers": [
                {"namespace": namespace, "value": value}
                for namespace, value in sorted(shared_identifiers)],
            "conflicting_identifier_namespaces": sorted(conflicting_namespaces),
            "shared_company_ids": sorted(set(_values(source, "company_entity_ids")) &
                                         set(_values(candidate, "company_entity_ids"))),
            "shared_roles": sorted({_text(value) for value in _values(source, "roles") if _text(value)} &
                                   {_text(value) for value in _values(candidate, "roles") if _text(value)}),
            "time_overlap": _time_overlap(source, candidate),
            "independent_sources": bool(_text(source.get("source")) and
                                        _text(candidate.get("source")) and
                                        _text(source.get("source")) != _text(candidate.get("source"))),
        }
        ambiguous_exact = any(exact_counts[item] > 1 for item in shared_identifiers)
        if not signals["entity_type_match"] or conflicting_namespaces or ambiguous_exact:
            score, confidence = 0.0, "UNRESOLVED"
            reason = ("entity_type_mismatch" if not signals["entity_type_match"] else
                      "conflicting_official_identifiers" if conflicting_namespaces else
                      "ambiguous_official_identifier")
        elif shared_identifiers:
            score, confidence, reason = 1.0, "EXACT", "shared_exact_official_identifier"
        else:
            score = 0.05
            score += 0.20 if signals["normalized_name_match"] else 0
            score += 0.25 if signals["shared_company_ids"] else 0
            score += 0.20 if signals["shared_roles"] else 0
            score += 0.15 if signals["time_overlap"] else 0
            score += 0.10 if signals["independent_sources"] else 0
            confidence = ("HIGH" if score >= 0.75 else "MEDIUM" if score >= 0.50
                          else "LOW" if score >= 0.25 else "UNRESOLVED")
            reason = "multi_signal_context" if confidence != "UNRESOLVED" else "insufficient_signals"
        result_id = stable_id("resolution_candidate", ENGINE_VERSION,
                              f"{source_id}:{candidate_id}:{primary_evidence}")
        results.append(ResolutionCandidate(
            id=result_id, source_entity_id=source_id, candidate_entity_id=candidate_id,
            confidence=confidence, score=f"{score:.2f}", reason=reason,
            signals=signals, evidence_id=primary_evidence,
            matching_evidence_ids=evidence_ids))
    return results


def relationship_confidence_allowed(confidence):
    return confidence in PUBLISHABLE_CONFIDENCE


def resolution_quality(labeled_results):
    """Return precision/recall for the auto-eligible EXACT/HIGH threshold."""
    true_positive = false_positive = false_negative = true_negative = 0
    for item in labeled_results:
        predicted = item["confidence"] in PUBLISHABLE_CONFIDENCE
        actual = bool(item["is_match"])
        if predicted and actual:
            true_positive += 1
        elif predicted:
            false_positive += 1
        elif actual:
            false_negative += 1
        else:
            true_negative += 1
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    return {"sample_size": len(labeled_results), "true_positive": true_positive,
            "false_positive": false_positive, "false_negative": false_negative,
            "true_negative": true_negative, "precision": precision, "recall": recall}


def company_entity(uniform: str, name: str) -> Entity:
    if not re.fullmatch(r"[0-9]{8}", uniform):
        raise ValueError("Company uniform number must contain 8 digits")
    return Entity(stable_id("entity", "tw:uniform_number", uniform), "Company", name,
                  name, "tw:uniform_number", uniform, "EXACT")


def person_observation(company_id: str, record_id: str, name: str) -> Entity:
    """Two rows with the same name remain separate, including within one company."""
    scoped = f"{company_id}:{record_id}"
    return Entity(stable_id("entity", "legacy:company_people", scoped), "Person", name,
                  name, "legacy:company_people", scoped, "SOURCE_SCOPED")
