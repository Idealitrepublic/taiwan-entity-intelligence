from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from src.entities.models import CONFIDENCES, timestamp, uuid_string

RELATIONSHIP_TYPES = (
    "DIRECTOR_OF", "OFFICER_OF", "OWNER_OF", "SHAREHOLDER_OF",
    "POLITICAL_CONTRIBUTION_TO", "CONTRACT_WITH", "MEMBER_OF", "EMPLOYED_BY",
    "GOVERNMENT_POSITION", "LEGISLATOR_OF", "COMMITTEE_MEMBER", "PROPOSED_BILL",
    "CO_SPONSORED_BILL", "ASSET_OWNERSHIP", "BUSINESS_INVESTMENT",
    "RELATED_TO_JUDGMENT", "RELATED_TO_PENALTY",
)


@dataclass(frozen=True)
class Relationship:
    id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    primary_evidence_id: str
    observed_at: str
    confidence: str = "UNRESOLVED"
    status: str = "draft"
    start_date: str | None = None
    end_date: str | None = None
    date_precision: str = "unknown"
    amount: str | None = None
    currency: str | None = None
    percentage: str | None = None
    quantity: str | None = None
    quantity_unit: str | None = None
    source_role: str | None = None

    def __post_init__(self):
        for value in (self.id, self.source_entity_id, self.target_entity_id, self.primary_evidence_id):
            uuid_string(value)
        timestamp(self.observed_at)
        if self.source_entity_id == self.target_entity_id:
            raise ValueError("Self relationships are not supported in Phase 1")
        if self.relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError("Unsupported relationship type")
        if self.confidence not in CONFIDENCES or self.status not in ("draft", "published", "retracted"):
            raise ValueError("Invalid relationship confidence or status")
        if self.status == "published" and self.confidence not in ("EXACT", "HIGH"):
            raise ValueError("Unresolved or low-confidence relationships cannot be published")
        if self.date_precision not in ("day", "month", "year", "unknown"):
            raise ValueError("Invalid date precision")
        start = date.fromisoformat(self.start_date) if self.start_date else None
        end = date.fromisoformat(self.end_date) if self.end_date else None
        if start and end and end < start:
            raise ValueError("Relationship end precedes start")
        if self.date_precision != "unknown" and not (start or end):
            raise ValueError("Known date precision requires a date")
        for key in ("amount", "quantity", "percentage"):
            value = getattr(self, key)
            if value is not None and (not Decimal(value).is_finite() or Decimal(value) < 0):
                raise ValueError("Amounts and holdings must be finite and nonnegative")
        if self.percentage is not None and Decimal(self.percentage) > 100:
            raise ValueError("Percentage must be between zero and 100")
        if (self.amount is None) != (self.currency is None):
            raise ValueError("Amount and currency must be provided together")
        if self.currency is not None and (len(self.currency) != 3 or not self.currency.isupper()):
            raise ValueError("Currency must be a three-letter code")
        if (self.quantity is None) != (self.quantity_unit is None):
            raise ValueError("Quantity and its unit must be provided together")

    def to_dict(self):
        return asdict(self)
