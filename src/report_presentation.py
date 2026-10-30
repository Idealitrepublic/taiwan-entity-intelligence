"""Human-readable projection of an unchanged, evidence-backed report.

JSON keeps every original field. HTML and PDF show concise facts and a source
register instead of recursively printing the same evidence and graph edges.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from zoneinfo import ZoneInfo

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
    "procurement_award": "政府決標 / Government award",
    "labor_penalty": "勞動裁罰 / Labor penalty",
    "mentioned_in_judgment": "裁判書名稱命中 / Name mentioned in judgment",
    "source_connected_company": "有來源連結的公司 / Source-connected company",
    "website": "公司網站 / Company website",
    "listed_in_anti_fraud": "165 網域命中 / 165 domain listing",
    "source_observation": "來源觀察 / Source observation",
    "identifier": "識別資訊 / Identifier", "note": "備註 / Note",
    "disposition": "處分文號 / Disposition", "amount": "金額 / Amount",
    "source_role": "起點角色 / From role", "target_role": "終點角色 / To role",
    "end_date": "結束日期 / End date", "currency": "幣別 / Currency",
    "contribution_type": "獻金類型 / Contribution type",
    "quantity": "數量 / Quantity", "company_name": "公司名稱 / Company name",
    "declaration_year": "申報年度 / Declaration year",
    "GovernmentOfficial": "政府官員 / Government official",
    "GovernmentAgency": "政府機關 / Government agency",
    "PoliticalParty": "政黨 / Political party", "Contract": "標案 / Contract",
    "Judgment": "裁判 / Judgment", "Penalty": "裁罰 / Penalty",
    "PoliticalContribution": "政治獻金 / Political contribution",
    "AssetDeclaration": "財產申報 / Asset declaration",
    "LegislativeBill": "法案 / Legislative bill", "LobbyingRecord": "遊說紀錄 / Lobbying record",
    "CivilOrganization": "民間團體 / Civil organization",
    "EXACT": "識別資料完全匹配 / Exact identifier match",
    "SOURCE_SCOPED": "僅限來源範圍的身分 / Source-scoped identity",
    "HIGH": "高信心 / High confidence", "MEDIUM": "中等信心 / Medium confidence",
    "LOW": "低信心 / Low confidence", "UNRESOLVED": "身分待核 / Unresolved identity",
    "DIRECTOR_OF": "擔任董事 / Director of", "OFFICER_OF": "擔任職務 / Officer of",
    "OWNER_OF": "所有權 / Owner of", "SHAREHOLDER_OF": "持有股份 / Shareholder of",
    "MEMBER_OF": "成員關係 / Member of", "EMPLOYED_BY": "受僱關係 / Employed by",
    "GOVERNMENT_POSITION": "政府職務 / Government position",
    "LEGISLATOR_OF": "立委任期 / Legislative term",
    "COMMITTEE_MEMBER": "委員會成員 / Committee member",
    "PROPOSED_BILL": "提案 / Proposed bill", "CO_SPONSORED_BILL": "共同提案 / Co-sponsored bill",
    "ASSET_OWNERSHIP": "資產持有 / Asset ownership",
    "BUSINESS_INVESTMENT": "事業投資 / Business investment",
    "SOURCE_CONNECTED_COMPANY": "有來源連結的公司 / Source-connected company",
    "REAL_ESTATE": "不動產 / Real estate", "CASH": "現金 / Cash",
    "DEPOSIT": "存款 / Deposit", "STOCK": "股票 / Stock", "BOND": "債券 / Bond",
    "FUND": "基金 / Fund", "SECURITY": "有價證券 / Security",
    "CLAIM": "債權 / Claim", "DEBT": "債務 / Debt", "INSURANCE": "保險 / Insurance",
    "VEHICLE": "車輛 / Vehicle", "OTHER": "其他資產 / Other assets",
    "ENTITY_REPORT": "實體報告 / Entity report",
    "WORKSPACE": "工作區報告 / Workspace report", "LIVE_COMPANY": "公司調查報告 / Company report",
    "董事長": "董事長 / Chair", "副董事長": "副董事長 / Vice chair",
    "董事": "董事 / Director", "獨立董事": "獨立董事 / Independent director",
    "監察人": "監察人 / Supervisor", "經理人": "經理人 / Manager",
    "總經理": "總經理 / General manager", "代表人": "代表人 / Representative",
    "法人代表": "法人代表 / Corporate representative",
}

PROFILE_FIELDS = {"id", "display_name", "canonical_name", "entity_type", "public_identifier",
                  "source_id", "identity_status", "evidence"}
RELATION_FIELDS = {"id", "relationship_type", "source_entity_id", "target_entity_id",
                   "start_date", "observed_at", "amount", "currency", "primary_evidence_id", "status"}


def format_date(value):
    """Preserve date precision; convert only explicitly zoned timestamps to Taiwan time."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        separated = re.fullmatch(r"(\d{3,4})[/.\-](\d{1,2})[/.\-](\d{1,2})", text)
        if separated:
            year, month, day = map(int, separated.groups())
            return date(year + 1911 if len(separated[1]) == 3 else year, month, day).isoformat()
        if re.fullmatch(r"\d{7}", text):
            return date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:])).isoformat()
        if re.fullmatch(r"\d{8}", text):
            return datetime.strptime(text, "%Y%m%d").date().isoformat()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text).isoformat()
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if moment.tzinfo is not None:
            return moment.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S (UTC+08:00)")
        return moment.strftime("%Y-%m-%d %H:%M:%S") + "（時區未註明 / Timezone unspecified）"
    except ValueError:
        return text


def format_number(value):
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        return text
    try:
        number = Decimal(text.replace(",", ""))
        return format(number, ",f") if number.is_finite() else text
    except InvalidOperation:
        return text


def format_money(value, currency=None):
    amount = format_number(value)
    if amount is None:
        return None
    if not re.fullmatch(r"[+-]?[\d,]+(?:\.\d+)?", amount):
        return amount
    unit = {"TWD": "NT$", "USD": "US$", "EUR": "EUR", "JPY": "JPY"}.get(currency, currency)
    return f"{unit} {amount}" if unit else f"{amount}（幣別未註明 / Currency unspecified）"


def unique_records(rows):
    """Remove only identical records; distinct provenance or amounts remain separate."""
    result, seen = [], set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        fingerprint = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
        if fingerprint not in seen:
            seen.add(fingerprint)
            result.append(row)
    return result


def format_locator(value):
    if not isinstance(value, (dict, list)):
        text = _text(value)
        if text and not re.match(r"^https?://", text):
            text = re.sub(r"Business_Accounting_NO=(\d{8})", r"統一編號 / Company ID: \1", text)
            text = re.sub(r"(?:^|;)row=(\d+)", r"；來源列 / Source row: \1", text)
        return text
    if isinstance(value, list):
        return "；".join(format_locator(item) or "—" for item in value)
    labels = {"dataset": "資料集 / Dataset", "record": "紀錄 / Record",
              "row": "列 / Row", "row_number": "列號 / Row number",
              "uniform_number": "統一編號 / Company ID", "company_name": "公司 / Company",
              "source_record_id": "來源編號 / Source record", "page": "頁碼 / Page",
              "disposition_number": "處分文號 / Disposition number",
              "disposition_date": "處分日期 / Disposition date",
              "issuing_authority": "處分機關 / Issuing authority",
              "reported_name": "公告名稱 / Published name", "jid": "裁判識別 / Judgment ID",
              "case_number": "案號 / Case number", "law": "法規 / Law",
              "authority": "主管機關 / Authority", "violation": "公告事實 / Published facts",
              "match_method": "比對方式 / Match method", "review_method": "核對方式 / Review method",
              "source_amount": "公告金額 / Published amount", "source_company_label": "公告公司名稱 / Published company name",
              "title": "公告標題 / Notice title", "agency": "採購機關 / Procuring agency",
              "amount": "金額 / Amount", "winner": "得標標記 / Award marker",
              "unit_id": "機關代碼 / Agency ID", "award_date": "決標日期 / Award date",
              "job_number": "標案案號 / Contract number", "mirror_url": "結構化介接 / Structured mirror URL",
              "bidder_name": "投標廠商 / Bidder", "notice_date": "公告日期 / Notice date",
              "notice_filename": "公告識別 / Notice reference", "bidder_uniform_number": "廠商統編 / Bidder company ID",
              "candidate_name": "申報對象 / Candidate", "election": "選舉 / Election",
              "term_number": "屆別 / Term", "constituency": "選區 / Constituency",
              "csv_row": "來源列 / Source row", "pdf_page": "來源頁 / Source page",
              "archive_member": "原件檔名 / Archive member", "row_serial": "紀錄序號 / Record serial",
              "contribution_year": "獻金年度 / Contribution year", "return_status": "返還註記 / Return notation"}
    meanings = {"explicit_uniform_number_verified_moea": "公告統編與公司登記核對 / Published company ID verified with registry",
                "official_row_compared_with_exact_bidder_id_and_award_role": "公告列、統編及得標角色核對 / Official notice, company ID and award role verified",
                "exact_uniform_number": "統編精確匹配 / Exact company ID",
                "exact_official_identifier": "官方識別精確匹配 / Exact official identifier",
                "not_marked_returned_in_source": "來源未標示返還 / Not marked as returned in source",
                "reviewed_crosswalk": "經核對身分對照 / Reviewed identity crosswalk"}
    readable = {key: meanings.get(item, item) if isinstance(item, str) else item
                for key, item in value.items()}
    return "\n".join(f"{labels.get(key, '來源欄位 / ' + str(key).replace('_', ' '))}: "
                     f"{format_date(item) if key == 'disposition_date' else format_locator(item) or '—'}"
                     for key, item in readable.items() if key != "source_file_id")


def source_locator_text(row):
    """Prefer official citations over opaque ingestion IDs, which remain in JSON."""
    locator = row.get("source_locator")
    has_official = isinstance(locator, dict) and any(locator.get(key) for key in
                    ("disposition_number", "jid", "case_number", "uniform_number"))
    if has_official:
        return format_locator({key: value for key, value in locator.items()
                               if key != "source_record_id"})
    parts = [f"來源編號 / Source record: {row['source_record_id']}" if row.get("source_record_id") else None,
             format_locator(locator)]
    return "\n".join(dict.fromkeys(part for part in parts if part)) or None


def _additional_facts(row, excluded):
    """Show only human-labelled facts, never opaque IDs or database internals."""
    return [_fact(LABELS[key], format_date(value) if key == "end_date" else
                  format_context(value) if key in ('source_role', 'target_role') else
                  format_number(value) if key == "quantity" else value)
            for key, value in row.items()
            if key not in excluded and key in LABELS
            and isinstance(value, (str, int, float, bool))]


def format_context(value):
    """Translate known official context codes without changing source JSON."""
    names = {'term':'屆別 / Term', 'session':'會期 / Session', 'co_chair':'召集委員 / Convener'}

    def replace(match):
        key, item = match[1], match[2].strip()
        if key == 'co_chair':
            item = {'Y':'是 / Yes', 'N':'否 / No'}.get(item, item)
        return f'{names[key]}：{item}'

    return re.sub(r'\b(term|session|co_chair):\s*([^;]+)', replace, str(value or ''))


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
            _fact("取得時間 / Retrieved at", format_date(evidence.get("retrieved_at"))))


def _records(key, values, detail_sections=None):
    if key == "relationship_graph":
        graph = values or {}
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        return [_item("圖譜範圍 / Graph scope",
                      _fact("節點 / Nodes", len(nodes)), _fact("連線 / Edges", len(edges)),
                      _fact("截斷 / Truncated", bool(graph.get("truncated"))))]
    if key == "anti_fraud_checks":
        return [_item(row.get("domain"),
                      _fact("狀態 / Status", "已索引比對 / Indexed check" if row.get("status") == "ok"
                            else "索引不可用 / Index unavailable"),
                      _fact("網域命中 / Domain matches", row.get("matched")),
                      _fact("原始連結 / Source URL", row.get("source_url")),
                      _fact("索引時間 / Indexed at", format_date(row.get("retrieved_at"))))
                for row in values or [] if isinstance(row, dict)]
    if key in ("key_relationships", "political_relationships", "government_contracts",
               "judgments", "penalties"):
        values = sorted((row for row in values or [] if isinstance(row, dict)),
                        key=lambda row: format_date((row.get("relationship") or row).get("start_date")
                                                     or (row.get("relationship") or row).get("observed_at")) or "",
                        reverse=True)
    elif key == "asset_records":
        values = sorted((row for row in values or [] if isinstance(row, dict)),
                        key=lambda row: str(row.get("declaration_year") or ""), reverse=True)
    result = []
    for row in unique_records(values):
        if not isinstance(row, dict):
            continue
        if key == "entity_profiles":
            evidence = (row.get("evidence") or [])
            result.append(_item(row.get("display_name") or row.get("canonical_name") or row.get("id"),
                                _fact("類型 / Type", LABELS.get(row.get("entity_type"), row.get("entity_type"))),
                                _fact("官方識別 / Official ID", row.get("public_identifier") or row.get("source_id")),
                                _fact("識別狀態 / Identity", LABELS.get(row.get("identity_status"), row.get("identity_status"))),
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
                                _fact("資本額 / Capital", format_money(row.get("capital_amount"), "TWD")),
                                _fact("設立日期 / Established", format_date(row.get("established_date"))),
                                _fact("來源 / Source", row.get("source")),
                                _fact("原始連結 / Source URL", row.get("source_url")),
                                _fact("取得時間 / Retrieved at", format_date(row.get("fetched_at")))))
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
                                _fact("日期 / Date", format_date(relation.get("start_date") or relation.get("observed_at"))),
                                _fact("金額 / Amount", format_money(relation.get("amount"), relation.get("currency"))),
                                *_additional_facts(relation, RELATION_FIELDS),
                                *_evidence_facts(evidence)))
            detail = (detail_sections or {}).get(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str))
            if key == "key_relationships" and detail:
                # A short overview points to the full categorized record. Its
                # Evidence stays in that detail section and in the source register.
                result[-1]["facts"] = [fact for fact in result[-1]["facts"]
                                       if fact[0] in ("起點 / From", "終點 / To", "日期 / Date", "金額 / Amount")]
                result[-1]["facts"].append(("詳細資料 / Details", detail))
        elif key == "asset_records":
            result.append(_item(row.get("asset_name") or row.get("asset_type") or row.get("id"),
                                _fact("申報年度 / Declaration year", row.get("declaration_year")),
                                _fact("類型 / Type", LABELS.get(row.get("asset_type"), row.get("asset_type"))),
                                _fact("金額 / Amount", format_money(row.get("amount"), row.get("currency"))),
                                _fact("數量 / Quantity", format_number(row.get("quantity"))),
                                _fact("公司 / Company", row.get("company_name")),
                                *_evidence_facts(row.get("evidence"))))
        elif key == "workspace_items":
            result.append(_item(row.get("title") or LABELS.get(row.get("item_type"), row.get("item_type")),
                                _fact("收藏類型 / Saved type", LABELS.get(row.get("item_type"), row.get("item_type"))),
                                _fact("筆記 / Note", row.get("note_text")),
                                _fact("來源連結 / Source URL", row.get("source_url")),
                                _fact("收藏時間 / Saved at", format_date(row.get("created_at")))))
        elif key in ("sources", "saved_evidence"):
            result.append(_item(row.get("title") or row.get("source_name") or row.get("source") or row.get("id"),
                                _fact("提供者 / Provider", row.get("source_name") or row.get("source")),
                                _fact("來源定位 / Source locator", source_locator_text(row)),
                                _fact("原始連結 / Source URL", row.get("source_url")),
                                _fact("取得時間 / Retrieved at", format_date(row.get("retrieved_at")))))
    return result


def present_report(report):
    """Return display-only sections; never change the source report or its JSON API."""
    order = list(SECTION_TITLES)
    if report.get("report_type") == "LIVE_COMPANY":
        order.insert(2, ("anti_fraud_checks", "165 網域比對 / Official Domain Check"))
    if report.get("report_type") == "WORKSPACE":
        order += [("saved_evidence", "已收藏證據 / Saved evidence"),
                  ("workspace_items", "調查筆記與收藏 / Notes & saved items")]
    sections, empty = [], []
    detail_sections = {
        json.dumps(row, sort_keys=True, ensure_ascii=False, default=str): title
        for key, title in order if key in ("political_relationships", "government_contracts", "judgments", "penalties")
        for row in report.get(key) or [] if isinstance(row, dict)}
    for key, title in order:
        items = _records(key, report.get(key), detail_sections)
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
    if coverage.get("source_partial"):
        warnings.append("部分即時來源暫時無法取得，以下不是完整查詢結果。 / Some live sources were unavailable; this is not a complete query.")
    if report.get("report_type") == "WORKSPACE" and not report.get("entity_profiles"):
        warnings.append("此工作區未收藏可公開的公司或人物實體；單獨收藏來源不會自動生成公司資料或關係圖。 / Save a published Entity or Graph to include its profile and evidenced links; a source bookmark alone does not identify a company.")
    relationship_count = len(unique_records([
        row for key in ("key_relationships", "political_relationships", "government_contracts",
                        "judgments", "penalties") for row in report.get(key) or []]))
    relationship_label = ("關係紀錄（含候選） / Links & observations"
                          if report.get("report_type") == "LIVE_COMPANY" else "關係 / Relationships")
    return {"sections": sections, "empty": empty, "warnings": warnings,
            "generated_at": format_date(report.get("generated_at")),
            "report_type": LABELS.get(report.get("report_type"), report.get("report_type")),
            "summary": {"實體 / Entities": len(unique_records(report.get("entity_profiles"))),
                        relationship_label: relationship_count,
                        "證據來源 / Sources": len(unique_records(report.get("sources")))}}
