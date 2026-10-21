"""Human-readable projection of an unchanged, evidence-backed report.

JSON keeps every original field. HTML and PDF show concise facts and a source
register instead of recursively printing the same evidence and graph edges.
"""

from src.reports import SECTION_TITLES


LABELS = {
    "ENTITY": "實體 / Entity", "RELATIONSHIP": "關係 / Relationship",
    "EVIDENCE": "證據 / Evidence", "GRAPH": "關係圖 / Graph",
    "SOURCE": "來源 / Source", "NOTE": "筆記 / Note",
    "Company": "公司 / Company", "Politician": "政治人物 / Politician",
    "Person": "人物 / Person", "CONTRACT_WITH": "政府標案 / Government contract",
    "RELATED_TO_PENALTY": "相關裁罰 / Penalty", "RELATED_TO_JUDGMENT": "相關裁判 / Judgment",
    "POLITICAL_CONTRIBUTION_TO": "政治獻金 / Political contribution",
    "CORPORATE_DIRECTOR_LINK": "法人董監事代表 / Corporate director link",
    "identifier": "識別資訊 / Identifier", "note": "備註 / Note",
    "disposition": "處分文號 / Disposition", "amount": "金額 / Amount",
    "source_role": "起點角色 / From role", "target_role": "終點角色 / To role",
    "end_date": "結束日期 / End date", "currency": "幣別 / Currency",
    "contribution_type": "獻金類型 / Contribution type",
    "quantity": "數量 / Quantity", "company_name": "公司名稱 / Company name",
    "declaration_year": "申報年度 / Declaration year",
}

PROFILE_FIELDS = {"id", "display_name", "canonical_name", "entity_type", "public_identifier",
                  "source_id", "identity_status", "evidence"}
RELATION_FIELDS = {"id", "relationship_type", "source_entity_id", "target_entity_id",
                   "start_date", "observed_at", "amount", "primary_evidence_id", "status"}


def _additional_facts(row, excluded):
    """Show only human-labelled facts, never opaque IDs or database internals."""
    return [_fact(LABELS[key], value)
            for key, value in row.items()
            if key not in excluded and key in LABELS
            and isinstance(value, (str, int, float, bool))]


def _text(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "是 / Yes" if value else "否 / No"
    return str(value)


def _fact(label, value):
    text = _text(value)
    return (label, text) if text is not None else None


def _item(title, *facts):
    return {"title": str(title or "—"), "facts": [fact for fact in facts if fact]}


def _evidence_facts(evidence):
    evidence = evidence or {}
    return (_fact("證據 / Evidence", evidence.get("title") or evidence.get("id")),
            _fact("來源 / Source", evidence.get("source_name") or evidence.get("source")),
            _fact("原始連結 / Source URL", evidence.get("source_url")),
            _fact("取得時間 / Retrieved at", evidence.get("retrieved_at")))


def _records(key, values):
    if key == "relationship_graph":
        graph = values or {}
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        return [_item("圖譜範圍 / Graph scope",
                      _fact("節點 / Nodes", len(nodes)), _fact("連線 / Edges", len(edges)),
                      _fact("截斷 / Truncated", bool(graph.get("truncated"))))]
    if key in ("key_relationships", "political_relationships", "government_contracts",
               "judgments", "penalties"):
        values = sorted((row for row in values or [] if isinstance(row, dict)),
                        key=lambda row: str((row.get("relationship") or row).get("start_date")
                                                     or (row.get("relationship") or row).get("observed_at") or ""),
                        reverse=True)
    elif key == "asset_records":
        values = sorted((row for row in values or [] if isinstance(row, dict)),
                        key=lambda row: str(row.get("declaration_year") or ""), reverse=True)
    result = []
    for row in values or []:
        if not isinstance(row, dict):
            continue
        if key == "entity_profiles":
            evidence = (row.get("evidence") or [])
            result.append(_item(row.get("display_name") or row.get("canonical_name") or row.get("id"),
                                _fact("類型 / Type", LABELS.get(row.get("entity_type"), row.get("entity_type"))),
                                _fact("官方識別 / Official ID", row.get("public_identifier") or row.get("source_id")),
                                _fact("識別狀態 / Identity", row.get("identity_status")),
                                _fact("身分證據數 / Identity evidence", len(evidence)),
                                *_additional_facts(row, PROFILE_FIELDS)))
        elif key == "company_registry":
            result.append(_item(row.get("name") or row.get("uniform_number"),
                                _fact("資料狀態 / Data status", "即時官方查詢 / Live official lookup"
                                      if row.get("data_status") == "live_official_exact_id"
                                      else "已儲存登記資料 / Stored registry record"),
                                _fact("統一編號 / Company ID", row.get("uniform_number")),
                                _fact("登記狀態 / Registry status", row.get("status")),
                                _fact("代表人 / Representative", row.get("representative_name")),
                                _fact("地址 / Address", row.get("address")),
                                _fact("資本額 / Capital", row.get("capital_amount")),
                                _fact("設立日期 / Established", row.get("established_date")),
                                _fact("來源 / Source", row.get("source")),
                                _fact("原始連結 / Source URL", row.get("source_url")),
                                _fact("取得時間 / Retrieved at", row.get("fetched_at"))))
        elif key in ("key_relationships", "political_relationships", "government_contracts",
                     "judgments", "penalties"):
            relation = row.get("relationship") or row
            evidence = row.get("evidence") or {}
            source = row.get("source_entity") or {}
            target = row.get("target_entity") or {}
            kind = relation.get("relationship_type")
            result.append(_item(LABELS.get(kind, kind or "公開關係 / Public relationship"),
                                _fact("起點 / From", source.get("display_name") or source.get("id")),
                                _fact("終點 / To", target.get("display_name") or target.get("id")),
                                _fact("日期 / Date", relation.get("start_date") or relation.get("observed_at")),
                                _fact("金額 / Amount", relation.get("amount")),
                                *_additional_facts(relation, RELATION_FIELDS),
                                *_evidence_facts(evidence)))
        elif key == "asset_records":
            result.append(_item(row.get("asset_name") or row.get("asset_type") or row.get("id"),
                                _fact("申報年度 / Declaration year", row.get("declaration_year")),
                                _fact("類型 / Type", row.get("asset_type")),
                                _fact("金額 / Amount", row.get("amount")),
                                _fact("數量 / Quantity", row.get("quantity")),
                                _fact("公司 / Company", row.get("company_name")),
                                *_evidence_facts(row.get("evidence"))))
        elif key == "workspace_items":
            result.append(_item(row.get("title") or LABELS.get(row.get("item_type"), row.get("item_type")),
                                _fact("收藏類型 / Saved type", LABELS.get(row.get("item_type"), row.get("item_type"))),
                                _fact("筆記 / Note", row.get("note_text")),
                                _fact("來源連結 / Source URL", row.get("source_url")),
                                _fact("收藏時間 / Saved at", row.get("created_at"))))
        elif key in ("sources", "saved_evidence"):
            result.append(_item(row.get("title") or row.get("source_name") or row.get("source") or row.get("id"),
                                _fact("提供者 / Provider", row.get("source_name") or row.get("source")),
                                _fact("來源紀錄 / Source record", row.get("source_record_id")),
                                _fact("原始連結 / Source URL", row.get("source_url")),
                                _fact("取得時間 / Retrieved at", row.get("retrieved_at"))))
    return result


def present_report(report):
    """Return display-only sections; never change the source report or its JSON API."""
    order = list(SECTION_TITLES)
    if report.get("report_type") == "WORKSPACE":
        order += [("saved_evidence", "已收藏證據 / Saved evidence"),
                  ("workspace_items", "調查筆記與收藏 / Notes & saved items")]
    sections, empty = [], []
    for key, title in order:
        items = _records(key, report.get(key))
        if items and (key == "relationship_graph" and (report.get(key) or {}).get("nodes")
                      or key != "relationship_graph"):
            sections.append({"key": key, "title": title, "items": items})
        else:
            empty.append(title)
    coverage = report.get("coverage") or {}
    warnings = []
    if any(value for key, value in coverage.items() if key.endswith("_truncated")):
        warnings.append("部分紀錄達顯示上限；本報告並非完整來源清單。 / Some records reached display limits.")
    unavailable = coverage.get("unavailable_saved_references") or []
    if unavailable:
        warnings.append(f"{len(unavailable)} 個收藏參照目前無法公開取得。 / Saved references unavailable.")
    if report.get("report_type") == "WORKSPACE" and not report.get("entity_profiles"):
        warnings.append("此工作區未收藏可公開的公司或人物實體；單獨收藏來源不會自動生成公司資料或關係圖。 / Save a published Entity or Graph to include its profile and evidenced links; a source bookmark alone does not identify a company.")
    return {"sections": sections, "empty": empty, "warnings": warnings,
            "summary": {"實體 / Entities": len(report.get("entity_profiles") or []),
                        "關係 / Relationships": len(report.get("key_relationships") or []),
                        "證據來源 / Sources": len(report.get("sources") or [])}}
