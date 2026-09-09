"""Stable source identities and explicitly versioned, redacted evidence."""
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit
from uuid import UUID, uuid5

ENTITY_TYPES = (
    "Company", "Person", "Politician", "GovernmentOfficial", "GovernmentAgency",
    "PoliticalParty", "Contract", "Judgment", "Penalty", "PoliticalContribution",
    "AssetDeclaration", "LegislativeBill", "LobbyingRecord",
)
CONFIDENCES = ("EXACT", "HIGH", "MEDIUM", "LOW", "UNRESOLVED")
SOURCE_CLASSES = (
    "Primary Source", "Government Open Data", "Official Registry", "Court Record",
    "Derived Data",
)
NAMESPACE = UUID("086f0610-46cc-5a57-9478-807bcf07a01b")


def stable_id(kind: str, namespace: str, source_id: str) -> str:
    """Use a source-issued ID or durable scoped observation ID, NEVER a name."""
    if not all(isinstance(v, str) and v.strip() for v in (kind, namespace, source_id)):
        raise ValueError("Identifiers require a kind, namespace and source record ID")
    return str(uuid5(NAMESPACE, json.dumps([kind, namespace, source_id], ensure_ascii=False)))


def uuid_string(value: str) -> str:
    return str(UUID(value))


def web_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Source URL must be an HTTP(S) URL without credentials")
    return value


def timestamp(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A source timestamp is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Source timestamps must include a timezone")
    return parsed.isoformat()


@dataclass(frozen=True)
class Entity:
    id: str
    entity_type: str
    canonical_name: str
    display_name: str
    source: str
    source_id: str
    identity_status: str = "SOURCE_SCOPED"
    publication_status: str = "draft"

    def __post_init__(self):
        uuid_string(self.id)
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError("Unsupported entity type")
        if not all(v.strip() for v in (self.canonical_name, self.display_name, self.source, self.source_id)):
            raise ValueError("Entity names and provenance are required")
        if self.identity_status not in ("EXACT", "SOURCE_SCOPED", "UNRESOLVED"):
            raise ValueError("Invalid identity status")
        if self.publication_status not in ("draft", "published", "withdrawn"):
            raise ValueError("Invalid publication status")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Evidence:
    id: str
    source_name: str
    source_record_id: str
    source_class: str
    source_url: str | None
    source_locator: dict
    title: str
    summary: str
    observed_at: str
    retrieved_at: str
    content_hash: str
    publication_status: str = "draft"
    status: str = "active"

    def __post_init__(self):
        uuid_string(self.id)
        web_url(self.source_url)
        timestamp(self.observed_at)
        timestamp(self.retrieved_at)
        if self.source_class not in SOURCE_CLASSES:
            raise ValueError("Invalid source class")
        if not self.source_name.strip() or not self.source_record_id.strip() or not self.title.strip():
            raise ValueError("Evidence must identify its source record")
        if not self.source_url and not self.source_locator:
            raise ValueError("Evidence must have a source URL or reproducible locator")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise ValueError("Evidence requires a SHA-256 content hash")
        if self.publication_status not in ("draft", "published", "withdrawn"):
            raise ValueError("Invalid evidence publication status")
        if self.status not in ("active", "superseded", "retracted"):
            raise ValueError("Invalid evidence status")

    def to_dict(self):
        return asdict(self)


def evidence_from_projection(*, source_name, source_record_id, source_class,
                             source_url, source_locator, title, summary,
                             observed_at, retrieved_at, publication_status="draft"):
    """Only call with allowlisted public fields; this function never accepts raw payloads.

    Retrieval time is excluded from version identity so retries are idempotent.
    Changed facts / source locators create a new evidence version.
    """
    projection = dict(source_name=source_name, source_record_id=source_record_id,
                      source_class=source_class, source_url=web_url(source_url),
                      source_locator=source_locator, title=title, summary=summary)
    digest = sha256(json.dumps(projection, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":")).encode()).hexdigest()
    return Evidence(id=stable_id("evidence", source_name, f"{source_record_id}:{digest}"),
                    **projection, observed_at=timestamp(observed_at),
                    retrieved_at=timestamp(retrieved_at), content_hash=digest,
                    publication_status=publication_status)
