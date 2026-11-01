"""Reviewed case-level court announcements, never personal criminal dossiers.

This small catalog describes historical announcements, not a complete judgment
index, individual findings of guilt, or the present legal status of any party.
Originals and acquisition manifests stay outside Git. No names become identities.
"""
from datetime import date
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path

from src.entities.models import Entity, evidence_from_projection, stable_id, timestamp


SOURCE = "最高法院裁判結果公告 / Supreme Court case announcements"
CATALOG = {
    "667383": {
        "file": "chen-case.html", "url_suffix": "667383-d90bf-1.html",
        "date": "2022-06-29", "dockets": ["110年度台上字第3984號"],
        "lower_court": "108年度金上重訴字第5號",
        "proof": "本院於民國111年6月29日以110年度台上字第3984號判決 從程序上駁回",
        "result": "從程序上駁回上訴；法院公告全案確定 / Appeals procedurally dismissed; finality announced",
    },
    "688053": {
        "file": "wei-case.html", "url_suffix": "688053-1d44f-1.html",
        "date": "2022-07-29", "dockets": ["110年度台上字第2443號", "110年度台上字第2463號"],
        "lower_court": "108年度重矚上更一字第17、18號",
        "proof": "本院於民國111年7月29日以110年度台上字第2443、2463號判決駁回上訴。全案確定。",
        "result": "駁回上訴；法院公告全案確定 / Appeals dismissed; finality announced",
    },
    "1216430": {
        "file": "fu-case.html", "url_suffix": "1216430-79a4a-1.html",
        "date": "2024-12-11", "dockets": ["113年度台上字第4710號"],
        "lower_court": "112年度金上重訴字第56號",
        "proof": "本院於民國113年12月11日以113年度台上字第4710號判決，上訴駁回，而全案確定。",
        "result": "上訴駁回；法院公告全案確定 / Appeals dismissed; finality announced",
    },
}
LIMITATION = (
    "本筆為法院公告的歷史案件結果，並非判決全文或個人犯罪檔案；"
    "不表示所有當事人均有罪，不建立人物或企業連結，亦未確認後續再審變動。 / "
    "Historical case announcement, not full judgment text or a personal criminal profile. "
    "No finding is assigned to every party, no person/company links are inferred, "
    "and subsequent review outcomes have not been comprehensively verified."
)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def _normalize(value):
    return "".join(value.split())


def reviewed_bundle(directory: Path, *, as_of: date, publication_status="draft"):
    """Fail closed before any write if even the final source is inconsistent.

    Exactly three reviewed announcement groups are supported. The two-docket
    notice remains one source observation; it is not split into invented JIDs.
    No raw HTML, party names, contact fields or raw attachment text are exported.
    """
    if publication_status not in ("draft", "published"):
        raise ValueError("Invalid publication status")
    if not isinstance(as_of, date):
        raise ValueError("An explicit review date is required")
    try:
        start = as_of.replace(year=as_of.year - 5)
    except ValueError:  # Leap-day review: calendar-year window, not 1825 days.
        start = as_of.replace(year=as_of.year - 5, day=28)
    acquisition = json.loads((directory / "acquisition.json").read_text())
    if not isinstance(acquisition, list) or len(acquisition) > 20:
        raise ValueError("Invalid acquisition manifest")
    files = {}
    for record in acquisition:
        if record["file"] in files:
            raise ValueError("Duplicate acquisition file")
        files[record["file"]] = record
    bundle = {"entities": [], "evidence": [], "entity_evidence": []}
    for record_id, fact in CATALOG.items():
        finality = date.fromisoformat(fact["date"])
        if not start <= finality <= as_of:
            raise ValueError("Announcement finality date is outside the reviewed five-year window")
        original = directory / fact["file"]
        raw = original.read_bytes()
        acquired = files.get(fact["file"], {})
        url = "https://www.judicial.gov.tw/tw/cp-1888-" + fact["url_suffix"]
        if (not raw or len(raw) > 2_000_000 or acquired.get("source_url") != url
                or acquired.get("sha256") != sha256(raw).hexdigest()
                or acquired.get("bytes") != len(raw)):
            raise ValueError("Official source URL, size or snapshot hash mismatch")
        retrieved = timestamp(acquired["retrieved_at"])
        if date.fromisoformat(retrieved[:10]) < finality or date.fromisoformat(retrieved[:10]) > as_of:
            raise ValueError("Acquisition timestamp contradicts review or finality date")
        parser = _Text()
        parser.feed(raw.decode("utf-8"))
        text = _normalize(" ".join(parser.parts))
        if not all(_normalize(proof) in text for proof in
                   (fact["proof"], fact["lower_court"], "全案確定")):
            raise ValueError("Official finality, date or lower-court proof is missing")
        source_id = "judicial-news:" + record_id
        title = "最高法院 " + "、".join(fact["dockets"]) + "｜裁判結果公告 / Case announcement"
        entity = Entity(stable_id("entity", SOURCE, source_id), "Judgment", title, title,
                        SOURCE, source_id, "SOURCE_SCOPED", publication_status)
        locator = {
            "record_kind": "court_case_announcement_not_judgment_text",
            "official_record_id": record_id, "court": "最高法院",
            "docket_numbers": fact["dockets"], "lower_court_docket": fact["lower_court"],
            "finality_announced_on": fact["date"], "date_precision": "day",
            "case_result": fact["result"], "scope": "historical_case_notice_only",
            "snapshot_sha256": acquired["sha256"], "finality_proof": fact["proof"],
            "reviewed_as_of": as_of.isoformat(),
            "cross_check": "official_notice_docket_date_result_and_lower_court_reference",
            "independent_source_corroboration": False,
            "subsequent_review_status": "not_comprehensively_verified",
            "party_identity_matching": "not_performed", "coverage": "three_selected_notices_only",
        }
        evidence = evidence_from_projection(
            source_name=SOURCE, source_record_id=source_id, source_class="Court Record",
            source_url=url, source_locator=locator, title=title,
            summary=fact["result"] + "。 " + LIMITATION,
            observed_at=fact["date"] + "T00:00:00+08:00", retrieved_at=retrieved,
            publication_status=publication_status)
        bundle["entities"].append(entity.to_dict())
        bundle["evidence"].append(evidence.to_dict())
        bundle["entity_evidence"].append({"entity_id": entity.id, "evidence_id": evidence.id,
                                          "fact_type": "historical_court_finality_announcement"})
    return bundle
