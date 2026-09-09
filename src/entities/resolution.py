"""Identity resolution deliberately excludes name matching."""
from dataclasses import dataclass
import re
from .models import Entity, stable_id


@dataclass(frozen=True)
class Resolution:
    entity_id: str | None
    confidence: str
    reason: str


def resolve_identifier(namespace: str, value: str, identifiers: list[dict]) -> Resolution:
    matches = {r["entity_id"] for r in identifiers
               if r["namespace"] == namespace and r["value"] == value
               and r.get("confidence") == "EXACT"}
    if len(matches) == 1:
        return Resolution(matches.pop(), "EXACT", "namespaced_identifier")
    return Resolution(None, "UNRESOLVED", "conflicting_identifiers" if matches else "no_exact_identifier")


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
