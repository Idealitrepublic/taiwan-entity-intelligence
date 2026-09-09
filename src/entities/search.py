"""Validated public search input; names never imply entity identity resolution."""
from dataclasses import dataclass

from .models import ENTITY_TYPES


@dataclass(frozen=True)
class SearchRequest:
    term: str
    entity_type: str | None
    limit: int


def parse_search_request(query: dict) -> SearchRequest:
    term = query.get("q", [""])[0].strip()
    entity_type = query.get("entity_type", [None])[0] or None
    try:
        limit = int(query.get("limit", ["20"])[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid search limit") from exc
    if not 2 <= len(term) <= 100 or any(ord(character) < 32 for character in term):
        raise ValueError("Search term must contain 2 to 100 printable characters")
    if entity_type is not None and entity_type not in ENTITY_TYPES:
        raise ValueError("Unknown entity type")
    if not 1 <= limit <= 20:
        raise ValueError("Search limit must be between 1 and 20")
    return SearchRequest(term=term, entity_type=entity_type, limit=limit)
