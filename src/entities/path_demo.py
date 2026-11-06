"""Fictional company paths served separately from public entity data."""

from .models import stable_id
from .repository import EntityRepository


def _node(key, name, kind):
    return {"id": stable_id("entity", "demo:company_path", key),
            "display_name": name, "entity_type": kind, "demo_only": True}


_COMPANY_A = _node("a", "示範公司甲", "Company")
_COMPANY_B = _node("b", "示範公司乙", "Company")
_PERSON = _node("person", "示範民意代表", "Politician")
_AGENCY = _node("agency", "示範機關", "GovernmentAgency")


def _record(source, target, kind):
    key = f"{source['id']}:{target['id']}"
    proof = {"id": stable_id("evidence", "demo:company_path", key),
             "source_name": "示範資料 / Demo data", "title": "虛構示範關係 / Fictional link"}
    return {"source_entity": source, "target_entity": target, "primary_evidence": proof,
            "relationship": {"id": stable_id("relationship", "demo:company_path", key),
                             "source_entity_id": source["id"], "target_entity_id": target["id"],
                             "relationship_type": kind, "primary_evidence_id": proof["id"]}}


_A_LINK = _record(_COMPANY_A, _PERSON, "POLITICAL_CONTRIBUTION_TO")
_B_LINK = _record(_COMPANY_B, _PERSON, "POLITICAL_CONTRIBUTION_TO")
_B_AWARD = _record(_COMPANY_B, _AGENCY, "CONTRACT_WITH")
_MIDDLE = _record(_PERSON, _AGENCY, "COMMITTEE_MEMBER")


def _demo_transport(resource, params):
    if resource == "rpc/graph_entity_neighbors":
        if params["focus_id"] == _COMPANY_A["id"]:
            return [{"focus_entity": _COMPANY_A, **_A_LINK}]
        if params["focus_id"] == _COMPANY_B["id"]:
            return [{"focus_entity": _COMPANY_B, **row} for row in (_B_LINK, _B_AWARD)]
    if resource == "relationships":
        return [{**_MIDDLE["relationship"], "primary_evidence": _MIDDLE["primary_evidence"]}]
    raise ValueError("Unexpected demo data request")


def company_path_demo(depth):
    repository = EntityRepository(transport=_demo_transport)
    result = repository.company_path_at_depth(_COMPANY_A["id"], _COMPANY_B["id"], depth=depth)
    return {**result, "demo_only": True, "backend": "company_path_demo",
            "coverage_note": "此範例使用虛構資料。切換中介數後按「查找路徑」即可比較。 / Fictional demo. Change the range and select Find to compare."}
