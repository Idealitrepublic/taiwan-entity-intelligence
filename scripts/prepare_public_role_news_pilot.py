"""Prepare five reviewed public-office news observations, never inferred edges."""
import json
from pathlib import Path

from scripts.audit_public_news_people import cabinet_events, match_event, verify_inputs
from src.entities.models import evidence_from_projection

SOURCE = "公開職務新聞核對 / Reviewed public-office news"


def prepare(directory):
    directory = Path(directory)
    sources = verify_inputs(directory)
    news = sources["cna-cabinet-2025.html"]
    official = sources["ey-cabinet-2025.html"]
    if news["source_url"] != "https://www.cna.com.tw/news/aipl/202508275002.aspx":
        raise ValueError("Unreviewed news source")
    if official["source_url"] != "https://www.ey.gov.tw/Page/9277F759E41CCD91/d7afb1b5-10cb-470f-94ff-bd3c37e49dfe":
        raise ValueError("Unreviewed official source")
    roster = json.loads((directory / "development-roster.json").read_text())
    events = cabinet_events((directory / "cna-cabinet-2025.html").read_text(),
                            (directory / "ey-cabinet-2025.html").read_text())
    bundle = {"entities": [], "identifiers": [], "relationships": [],
              "relationship_evidence": [], "evidence": [], "entity_evidence": []}
    for event in events:
        candidates = match_event(event, roster, [])
        if len(candidates) != 1:
            continue
        entity_id = candidates[0]
        row = evidence_from_projection(
            source_name=SOURCE, source_record_id=f"cabinet-announcement:2025-08-27:{entity_id}",
            source_class="Derived Data", source_url=news["source_url"],
            title=f"新聞報導／官方公告：{event['name']}｜{event['agency']}{event['role']}",
            summary=(f"事件參與角色：{event['agency']}{event['role']}擬任人選。"
                     "2025-08-27人事公告及新聞相互核對；公告日不是任期生效日，"
                     "此記錄不表示目前職務、罪責或與其他被提及人士存在關係。"),
            source_locator={"observation_kind": "public_office_appointment_announcement",
                            "news_source_url": news["source_url"],
                            "official_source_url": official["source_url"],
                            "news_snapshot_sha256": news["sha256"],
                            "official_snapshot_sha256": official["sha256"],
                            "event_date": event["date"], "effective_date": None,
                            "entity_id": entity_id, "agency": event["agency"], "role": event["role"],
                            "matching_basis": "reviewed_full_name_agency_role_official_announcement",
                            "co_mentions_are_relationships": False, "publication_scope": "development_pilot"},
            observed_at="2025-08-27T00:00:00+08:00",
            retrieved_at=max(news["retrieved_at"], official["retrieved_at"]),
            publication_status="published")
        bundle["evidence"].append(row.to_dict())
        bundle["entity_evidence"].append({"entity_id": entity_id, "evidence_id": row.id,
                                          "fact_type": "public_office_news_observation"})
    if len(bundle["evidence"]) != 5:
        raise ValueError("Reviewed pilot cohort changed; stop before publication")
    return bundle
