"""Stable public contract for the Entity / Relationship / Evidence read model."""

API_VERSION = "1"

# Keep provenance and lifecycle fields private unless they are deliberately
# included here. These projections are shared by every public Entity API read.
ENTITY_FIELDS = (
    "id",
    "entity_type",
    "canonical_name",
    "display_name",
    "identity_status",
    "created_at",
    "updated_at",
)
EVIDENCE_FIELDS = (
    "id",
    "source_name",
    "source_record_id",
    "source_class",
    "source_url",
    "source_locator",
    "title",
    "summary",
    "observed_at",
    "retrieved_at",
    "content_hash",
    "status",
    "created_at",
    "updated_at",
)
RELATIONSHIP_FIELDS = (
    "id",
    "source_entity_id",
    "target_entity_id",
    "relationship_type",
    "primary_evidence_id",
    "start_date",
    "end_date",
    "date_precision",
    "observed_at",
    "amount",
    "currency",
    "percentage",
    "quantity",
    "quantity_unit",
    "source_role",
    "confidence",
    "status",
    "created_at",
    "updated_at",
)
POLITICIAN_TERM_FIELDS = (
    "id",
    "politician_entity_id",
    "term_number",
    "constituency",
    "constituency_type",
    "party_entity_id",
    "start_date",
    "end_date",
    "primary_evidence_id",
    "created_at",
    "updated_at",
)
ASSET_DECLARATION_FIELDS = (
    "id",
    "politician_id",
    "declaration_year",
    "asset_type",
    "asset_name",
    "amount",
    "currency",
    "quantity",
    "quantity_unit",
    "company_name",
    "company_entity_id",
    "relationship_id",
    "primary_evidence_id",
    "created_at",
    "updated_at",
)


def select_list(fields: tuple[str, ...]) -> str:
    """Return the PostgREST select expression for an allowlisted projection."""
    return ",".join(fields)


def response(data):
    """Preserve the version-1 envelope for every public model endpoint."""
    return {"api_version": API_VERSION, "data": data}
