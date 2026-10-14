"""Read-only, bounded paths between official company IDs and shared public records.

These observations are not published Entity/Relationship rows. In particular,
co-occurrence in a court document or contracting with the same agency does not
establish a corporate affiliation between the companies.
"""
from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from src.company import get_company
from src.entities.models import stable_id
from src.sources.judicial_index import judgment_url, load_index
from src.sources.procurement import lookup_awards


class CompanyRegistryUnavailable(RuntimeError):
    """The official registry did not answer, so identities cannot be verified."""


def _name(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).casefold()


def _date(value):
    raw = str(value or "")
    try:
        return datetime.strptime(raw, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def _company(uniform, row):
    if not isinstance(row, dict):
        return None
    if str(row.get("Business_Accounting_NO") or "").strip() != uniform:
        return None
    name = str(row.get("Company_Name") or "").strip()
    if not name:
        return None
    return {"id": stable_id("entity", "tw:uniform_number", uniform),
            "entity_type": "Company", "canonical_name": name,
            "display_name": name, "public_identifier": uniform,
            "identity_status": "EXACT", "is_live_fallback": True,
            "source": "經濟部公司登記即時查詢 / MOEA live registry"}


def _segment(company, shared, relationship_type, evidence, *, reverse=False, date=None):
    relationship = {
        "id": stable_id("relationship", relationship_type,
                        f"{company['public_identifier']}:{evidence['source_record_id']}:{shared['id']}"),
        "source_entity_id": company["id"], "target_entity_id": shared["id"],
        "relationship_type": relationship_type,
        "primary_evidence_id": evidence["id"], "start_date": date,
        "confidence": "EXACT", "observation_only": True,
    }
    return {"from_entity": shared if reverse else company,
            "to_entity": company if reverse else shared,
            "traversal_direction": "reverse" if reverse else "forward",
            "relationship": relationship, "evidence": evidence}


def _award_evidence(row, retrieved_at):
    record_id = str(row["id"])
    return {"id": stable_id("evidence", "pcc:notice", record_id),
            "source_name": "政府電子採購網公告（OpenFun 結構化介接）",
            "source_class": "Derived Data", "source_record_id": record_id,
            "title": str(row.get("title") or "政府採購決標公告"),
            "summary": f"得標廠商統編 {row['uniform_number']}；機關代碼 {row.get('unit_id') or '未提供'}；案號 {row.get('job_number') or '未提供'}。",
            "source_url": row.get("source_url"),
            "original_source_url": row.get("official_search_url"),
            "retrieved_at": retrieved_at,
            "provenance": {"match_method": "exact_bidder_uniform_number_and_winner_role",
                           "source_api": "OpenFun PCC structured mirror",
                           "unit_id": row.get("unit_id"),
                           "job_number": row.get("job_number")}}


def _judgment_evidence(row):
    jid = str(row["jid"])
    return {"id": stable_id("evidence", "judicial:jid", jid),
            "source_name": "司法院 JList/JDoc", "source_class": "Court Record",
            "source_record_id": jid, "title": row.get("title") or "司法院裁判書",
            "summary": str(row.get("summary") or "")[:700],
            "source_url": row.get("source_url") or judgment_url(jid),
            "retrieved_at": row.get("retrieved_at"),
            "provenance": {"match_method": "exact_official_company_name_in_same_jid",
                           "source": row.get("provenance") or "official_jdoc_api"}}


def _shared_award(source, target, source_awards, target_awards, retrieved_at):
    left = [row for row in source_awards.get("records", [])
            if row.get("award_role") == "winner" and row.get("uniform_number") == source["public_identifier"]
            and row.get("id") and row.get("source_url")]
    right = [row for row in target_awards.get("records", [])
             if row.get("award_role") == "winner" and row.get("uniform_number") == target["public_identifier"]
             and row.get("id") and row.get("source_url")]
    # Same notice is stronger than merely sharing a public contracting agency.
    by_notice = {row["id"]: row for row in right}
    shared_notices = [(a, by_notice[a["id"]]) for a in left if a["id"] in by_notice]
    if shared_notices:
        a, b = max(shared_notices, key=lambda pair: str(pair[0].get("date") or ""))
        shared = {"id": stable_id("entity", "pcc:notice", str(a["id"])),
                  "entity_type": "Contract", "display_name": a.get("title") or "共同得標公告",
                  "observation_only": True}
        kind = "AWARDED_CONTRACT"
        interpretation = "兩家公司以統編出現在同一得標公告；不代表彼此有股權或交易關係。 / Both appear as winners in one notice; no corporate affiliation is implied."
    else:
        by_agency = {}
        for row in right:
            if row.get("unit_id") and row.get("agency"):
                by_agency.setdefault(str(row["unit_id"]), []).append(row)
        pairs = [(a, b) for a in left if a.get("unit_id") and a.get("agency")
                 for b in by_agency.get(str(a["unit_id"]), [])]
        if not pairs:
            return None
        a, b = max(pairs, key=lambda pair: (min(str(pair[0].get("date") or ""),
                                                str(pair[1].get("date") or "")),
                                            str(pair[0].get("unit_id"))))
        shared = {"id": stable_id("entity", "pcc:unit_id", str(a["unit_id"])),
                  "entity_type": "GovernmentAgency",
                  "display_name": a.get("agency") or b.get("agency") or str(a["unit_id"]),
                  "public_identifier": str(a["unit_id"]), "observation_only": True}
        kind = "CONTRACT_WITH"
        interpretation = "兩家公司各自曾向同一機關得標；不代表兩家公司彼此有股權或直接交易關係。 / Each won a contract from the same agency; no direct company-to-company relationship is implied."
    return {"segments": [
        _segment(source, shared, kind, _award_evidence(a, retrieved_at), date=_date(a.get("date"))),
        _segment(target, shared, kind, _award_evidence(b, retrieved_at),
                 reverse=True, date=_date(b.get("date")))],
        "shared_node_type": shared["entity_type"], "interpretation": interpretation}


def _shared_judgment(source, target, index):
    source_name, target_name = _name(source["display_name"]), _name(target["display_name"])
    if source_name == target_name:
        return None  # A shared name alone cannot identify two distinct companies.
    matches = []
    for row in index.get("records") or []:
        if not isinstance(row, dict) or not row.get("jid"):
            continue
        names = {_name(name) for name in row.get("companies") or []}
        if source_name in names and target_name in names:
            matches.append(row)
    if not matches:
        return None
    row = max(matches, key=lambda item: str(item.get("date") or ""))
    shared = {"id": stable_id("entity", "judicial:jid", str(row["jid"])),
              "entity_type": "Judgment", "display_name": row.get("title") or "同一裁判書",
              "observation_only": True}
    evidence = _judgment_evidence(row)
    return {"segments": [
        _segment(source, shared, "RELATED_TO_JUDGMENT", evidence, date=row.get("date")),
        _segment(target, shared, "RELATED_TO_JUDGMENT", evidence,
                 reverse=True, date=row.get("date"))],
        "shared_node_type": "Judgment",
        "interpretation": "兩個完整公司名稱出現在同一裁判書；不代表兩家公司互為當事人、敗訴或具有企業關係。 / Both names occur in one judgment; roles and affiliation are not inferred."}


def live_company_path(source_uniform, target_uniform, *, max_depth=3,
                      company_lookup=None, award_lookup=None, index_loader=None):
    """Compare two exact MOEA IDs; return only evidenced shared-record paths."""
    if not all(re.fullmatch(r"[0-9]{8}", str(u or "")) for u in (source_uniform, target_uniform)):
        raise ValueError("Both company IDs must contain eight digits")
    if source_uniform == target_uniform or max_depth not in (1, 2, 3):
        raise ValueError("Company IDs must differ and range must be 1–3")
    company_lookup = company_lookup or get_company
    award_lookup = award_lookup or lookup_awards
    index_loader = index_loader or load_index
    retrieved_at = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=4) as pool:
        company_jobs = [pool.submit(company_lookup, uniform, timeout=12)
                        for uniform in (source_uniform, target_uniform)]
        award_jobs = ([pool.submit(award_lookup, uniform, limit=100, timeout=8)
                       for uniform in (source_uniform, target_uniform)]
                      if max_depth >= 2 else [])
        try:
            companies = [_company(uniform, job.result()) for uniform, job in
                         zip((source_uniform, target_uniform), company_jobs)]
        except Exception as exc:
            raise CompanyRegistryUnavailable("Official company registry unavailable") from exc
        awards = []
        for job in award_jobs:
            try:
                awards.append(job.result())
            except Exception:
                awards.append({"status": "partial", "records": [], "limited": True})
    if None in companies:
        return None
    source, target = companies
    index = index_loader() if max_depth >= 2 else {"records": [], "generated_at": None}
    shared = None
    if max_depth >= 2:
        if all(result.get("status") == "ok" for result in awards):
            shared = _shared_award(source, target, *awards, retrieved_at)
        if shared is None:
            shared = _shared_judgment(source, target, index)
    limited = any(result.get("status") != "ok" or result.get("limited") for result in awards)
    coverage = ("直接關係僅使用已發布索引；未入庫公司無可驗證的直接邊。 / Direct links require published relationships."
                if max_depth == 1 else
                "採購僅查可取得的第一頁得標公告；司法為部分 JList/JDoc 索引。未找到不代表兩家公司沒有關係。 / Procurement uses available first-page awards; the court index is partial. No match is not proof of no relationship.")
    return {"found": shared is not None, "depth": 2 if shared else None,
            "source_entity": source, "target_entity": target,
            "max_depth": max_depth, "segments": shared["segments"] if shared else [],
            "shared_node_type": shared.get("shared_node_type") if shared else None,
            "interpretation": shared.get("interpretation") if shared else None,
            "coverage_note": coverage, "truncated": limited,
            "shared_node_complete": False, "backend": "live_verified_shared_records",
            "sources": {"company_registry": "ok", "procurement_source": [r.get("status") for r in awards],
                        "judicial_index_generated_at": index.get("generated_at")}}
