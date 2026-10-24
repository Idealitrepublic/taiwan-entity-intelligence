# T.E.I. v2 data sources

## 經濟部維護與離線快照 / MOEA maintenance and offline snapshots

經濟部商工行政資料開放平臺[公告](https://data.gcis.nat.gov.tw/ns/news/detail?oid=8D1E61CE-E802-404D-B0C8-317549F580C2)於臺灣時間 2026-10-23 19:00 至 2026-10-26 24:00 維護。`/api/status` 僅在官方公告時段回傳此訊息；網頁頂端顯示來源、時段及官方連結。即時請求失敗時，已發布且統編精確對應的 `MOEA/GCI` Identity Evidence 可作公司身分備援，頁面與圖譜顯示該筆 Evidence 的 `retrieved_at`。這不代表公司其他欄位或董監事也是同一時間的完整快照；未保存者顯示「暫不可用」，不得當成零筆。

[董監事資料集](https://data.gov.tw/dataset/96731)提供每月更新的官方 CSV，包含統編、公司名稱、職稱、姓名、所代表法人與持股數。`scripts/sync_moea_officers_dev.py` 可於來源恢復後下載、驗證欄位與八碼統編，先在 repo 外的 `0600` 暫存目錄處理，再以內容 SHA-256 作為不可覆寫物件名稱存入 **tei-development** 的私有 Supabase Storage `tei-raw/moea_officers/`；`source_files` 保留 SHA、來源 URL、下載及索引時間，`source_records` 保留逐列原文、統編和原始列號。上傳或索引失敗時不發布 `indexed` 快照。網站只以最新已完整索引快照、精確統編讀取來源範圍內的董監事觀測，不因同名建立跨公司人物 Entity 或正式 Relationship。舊快照保留以供追溯與回復。

正式執行前須確認 Development Storage 可用空間、Postgres 容量與官方檔案大小；Free 額度不足時停止，不自行升級。`TEI_DEV_DATABASE_URL` 與只在本機執行程序使用的 `TEI_DEV_STORAGE_TOKEN` 不可寫入 repo、Preview 或 Production；腳本會檢查 database URL 僅指向 `tei-development`。先不帶 `--apply` 驗證檔案，再於來源可用且容量核准後執行 `--apply --confirm-capacity`。不得在維護期間改用非官方鏡像或宣稱目前董監事已有快照。若需定期排程，須先由運維人員核定來源更新頻率、容量與失敗告警；目前尚未啟用自動排程。

Storage 物件需另行備份；[Supabase 資料庫備份不包含 Storage 物件](https://supabase.com/docs/guides/platform/backups)。Production 的資料與設定不因 Development 快照流程而變動。

## Existing labor-penalty source restoration (Product Consolidation P0)

The existing MOL datasets [109896](https://data.gov.tw/dataset/109896),
[109897](https://data.gov.tw/dataset/109897), and
[110908](https://data.gov.tw/dataset/110908) supply official penalty rows. The
resource URL is resolved from the nested data.gov.tw catalog response and each
CSV is checked for agency, disposition date/number, business name, and statute
columns before Development indexing. The indexed row preserves the official
raw payload, dataset URL, snapshot hash, and retrieval time. Reimport is
idempotent. A company-name match is a candidate source association; it is not
an exact legal-entity resolution or a published canonical Relationship when the
official row lacks a verified uniform number. The source generally supplies a
dataset or search entry rather than a permanent row URL; the UI distinguishes
these. The Development snapshot is external-only and does not imply a Storage
object was uploaded.

The Product Consolidation root audit adds a separate exact-identifier
materialization stage for these same sources. Explicit uniform-number fields or
a terminal, tab-separated source identifier must agree with MOEA's identifier
and official name. Only such verified records may create canonical Penalty
Entities, Company fact Evidence and `RELATED_TO_PENALTY`; name-only rows remain
indexed candidates. The 2026-10-06 snapshot contains one such materialized record
out of 80,122 indexed rows. That is not 100% canonical resolution coverage.

## DATA Phase 1 — Political Master Data

Primary provider: Legislative Yuan Open Data Service (`data.ly.gov.tw`).

| Dataset | Official ID | Grain | Fields used | Refresh |
|---|---:|---|---|---|
| Historical legislators | 16 | one legislator-term row | term, name, party, constituency, committee text, onboard/leave dates | daily 03:05 |
| Committee membership | 14 | one legislator/term/session/committee row | `lgno`, term, session, committee, co-chair flag | daily 02:45 |
| Current legislators | 9 | one current legislator row | current-state completeness cross-check only | daily 04:10 |

Official metadata and API documentation:

- Dataset 16: <https://data.ly.gov.tw/getds.action?id=16>
- Dataset 14: <https://data.ly.gov.tw/getds.action?id=14>
- Dataset 9: <https://data.ly.gov.tw/getds.action?id=9>
- API guide: <https://data.ly.gov.tw/gniKK/developer.action>
- Official legislator-number list: <https://data.ly.gov.tw/legislator.pdf>
- Legislative Yuan member directory: <https://www.ly.gov.tw/Pages/List.aspx?nodeid=109>

### Identity and provenance rules

- `lgno` is the only Phase 1 cross-row politician identifier. Exact `lgno` creates
  `tw:legislative_yuan:legislator_number`; it is never inferred from a name.
- Dataset 16 has no documented `lgno`. It may be joined to dataset 14 only within
  the same term and exact normalized name, and only when that pair maps to one
  unique `lgno`. Ambiguous or absent mappings remain `SOURCE_SCOPED`.
- Names, English names, party labels, photos, addresses, telephone numbers, and
  biographies are not identity keys. Contact details are not ingested.
- Every accepted member and committee observation creates immutable Evidence with
  dataset ID, source record ID, retrieval time, and official source URL.
- All bundle output is `draft`; publication remains a separate reviewed action.

### Quality gates

- Required member fields: term, name, constituency, onboard date.
- Required committee fields: term, session, `lgno`, name, committee.
- Reject malformed dates, out-of-range term/session values, identifier/name
  conflicts, and committee rows that cannot resolve to an exact `lgno` Entity.
- Report member acceptance, exact-identifier coverage, committee join coverage,
  ambiguous identifiers, and unmatched committee rows on every build.
- Split refreshes into dependency-complete, idempotent RPC batches within the
  200-row core and 1 MB transaction limits.
- A zero-row source response is not accepted as a successful full refresh without
  an explicit source-health decision.

## DATA Phase 2 — Political Contributions

Primary provider: Control Yuan Political Contribution Public Access Platform.

- Official platform: <https://ardata.cy.gov.tw/>
- 11th Legislative Yuan election dataset: <https://data.gov.tw/dataset/168061>
- 10th Legislative Yuan election dataset: <https://data.gov.tw/dataset/129495>

The official files contain filing/row identity, candidate or party, election,
transaction date, income/expense category, donor/payee, ID or uniform number,
amount, donation method, and correction metadata. The adapter allowlists only
the contribution fields needed by T.E.I.; addresses, telephone numbers, and
personal national IDs are never retained in Evidence.

### Identity, provenance, and quality rules

- A Company match requires an exact normalized eight-digit `tw:uniform_number`.
- A Politician match requires one exact official identifier supplied by the
  source-to-master crosswalk. Candidate names are audit text, never match keys.
- Evidence retains filing/row ID, candidate and donor source labels, election
  year, source URL, retrieval time, and both exact matching methods.
- Every build reports accepted/skipped rows, exact-match coverage, duplicate
  source records, conflicting duplicates, and bounded batch count. Zero rows or
  any conflicting source-record identity requires review before publication.
- Output is draft-only and split into dependency-complete batches of at most 200
  Relationships, 400 Evidence records, and 1 MB. A whole batch can be removed
  while draft; published corrections use superseding Evidence, never mutation.

## DATA Phase 3 — Asset Declarations

Primary provider: Control Yuan Sunshine Acts portal and Integrity Gazette.

- Asset declaration portal: <https://sunshine.cy.gov.tw/>
- Integrity Gazette index: <https://sunshine.cy.gov.tw/News.aspx?PageSize=200&n=17&page=1&sms=8861>
- Public Officials Property Declaration Act: <https://www.cy.gov.tw/law/LawContent.aspx?id=FL010649>
- Official form instructions: <https://multimedia.cy.gov.tw/law/LawContent.aspx?id=FL010661>

The portal publishes declarations as gazette/document records rather than one
stable bulk API. Extraction must therefore retain the issue, filing ID, line
number, source URL, declaration date, retrieval time, and correction version.
Only the thirteen T.E.I. asset categories are allowlisted. Personal identity,
address, contact, spouse, and minor-child fields are excluded from ingestion.

### Identity, versioning, and quality rules

- Politicians resolve only through an exact official identifier crosswalk.
- Companies resolve only through an exact normalized eight-digit uniform number;
  a company name remains source text and never forces a merge.
- A deterministic declaration key identifies the same filing line across
  corrections. Versions are append-only; a later version references the older,
  withdrawn version, and only one version may be published for a key.
- Every run reports row acceptance, all-category coverage, exact Company match
  rate, unresolved Companies, duplicates, and conflicting source records.
- Draft-only batches contain at most 200 declaration lines/Relationships, 400
  Evidence records, and 1 MB. Zero-row loads and source-record conflicts require
  review. Rollback removes the draft batch; published corrections are superseded.

## DATA Phase 4 — Cross-source entity resolution

Phase 4 introduces no new provider. It compares normalized observations from the
official sources above and other existing evidence-backed adapters.

- Exact Company and Politician identifiers have priority; conflicting or
  non-unique identifiers remain unresolved.
- Context signals—Company, role, overlapping dates, and independent source—must
  be traceable to immutable Evidence. Names are comparison signals, not keys.
- Candidates are private, service-role-only, bounded to 200 per ingestion call,
  and remain pending until reviewed. `MEDIUM`, `LOW`, and `UNRESOLVED` cannot be
  accepted or create formal Relationships.
- Quality checks use labeled representative pairs and report precision/recall at
  the `EXACT`/`HIGH` threshold. Rollback drops the additive ingestion function,
  constraints, indexes, and columns; it does not alter canonical Entities.

## DATA Phase 5 — Judiciary coverage

Primary provider: [Judicial Yuan JList/JDoc API specification](https://opendata.judicial.gov.tw/api/Newses/39/file).
JList exposes a seven-day change window, not a historical search. JDoc retrieves
one identified document. The public [court judgment page](https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=KLDM%2C111%2C%E8%A8%B4%2C328%2C20230428%2C1)
is the source URL used to cross-check known cases.

- Ingestion requires `JUDICIAL_USER` and `JUDICIAL_PASSWORD` in the manual sync
  job. Missing credentials or invalid API responses fail the run; an empty
  seven-day window is reported distinctly from a verified zero match.
- JID is the deduplication key. Document content hashes preserve corrections as
  separate Evidence versions; a later removal suppresses the index entry.
- Each record retains the official JID, normalized judgment date, source URL,
  retrieval time, content hash, and raw JDoc provenance. File-only documents
  without extracted text remain unindexed and are counted.
- Company-name occurrences are observational search matches, not an Entity
  identity decision or legal finding. Person names remain unresolved without
  stronger identifiers.
- The checked-in verified case set covers two older judgments mentioning
  御首服務事業有限公司 and one recent judgment mentioning 中華郵政股份有限公司.
  Run `python scripts/judicial_coverage.py --verify-official` to repeat the
  known-case comparison. Sample recall is not historical population recall.

## DATA Phase 6 — Cross-source quality benchmark

Run `python scripts/data_health.py --json reports/data_health.json --markdown docs/DATA_HEALTH.md`.
This read-only benchmark uses three fixed valid company identifiers and three
official known-case judicial JIDs. It measures coverage, freshness, errors,
duplicates and provenance across nine source families. Its sample coverage is
not population recall. Published-data presence for politician, contribution and
asset rows is separate from draft adapter test coverage; private resolution
candidates are intentionally unobservable to the anonymous role. Unindexed
`source_records.dataset` population counts are not used after timed-out queries.

The repository has normalizers for political master, contributions and asset
declarations, plus bounded Development ingestion scripts. There is still no
scheduled, reviewed national ingestion job. Adapter fixture coverage is not
live coverage.
The Integrity Gazette currently offers full electronic books only for recently
published issues; older issue listings alone cannot establish historical line
coverage. The absence of a reliable official candidate-to-`lgno` crosswalk
prevents automatic Company→Politician contribution edges from name-only files.

The reviewed Development sample uses Control Yuan Taipei donation row
`168061:taipei:incomes:886`, exact donor uniform number `29072066` checked
against MOEA, LY term-11 `lgno` `00007` and Taipei third-district term, with
an independent [CEC district record](https://web.cec.gov.tw/central/article/60070).
Gazette issue 319's vehicle line is checked against LY `lgno` `00082`, office,
term, and resignation/declaration date on the
[LY member page](https://www.ly.gov.tw/Pages/List.aspx?nodeid=46830).
Both are reviewed source chains, not source-issued `lgno` or automatic
name-only joins. Only one record of each type has been published in the
isolated Development DB; national coverage remains unknown.

### Phase 6 acceptance and source limitations

The [offline acceptance record](docs/DATA_PHASE_6_OFFLINE_ACCEPTANCE.md)
separates saved row-level Evidence from an earlier public sample and a
Development DB count snapshot. A fixture, adapter success, source listing, or
one published row is not population coverage. `reports/data_health.json` is a
sample-scoped, timestamped observation and must be refreshed after the final
judicial sync; the privileged Development DB audit has its own timestamp.

The Judicial Yuan API specification limits JList/JDoc service to 00:00–06:00
Asia/Taipei. JList is a seven-day change feed, not a historical corpus. A
stable HTTP 200 JDoc error may be classified as upstream unavailable only
after matching official error fingerprints on separate bounded runs with
retained JList metadata. It remains recheckable; a transport error, closed
service window, or pending retry is not evidence of permanent unavailability.
The fixed snapshot/checkpoint procedure and rollback boundary are documented
in the offline acceptance record. No conclusion about unprocessed JIDs is
permitted before all batches are attempted.

Procurement results use an OpenFun mirror of official PCC notices. Its
`source_url` or official search entry is not necessarily a stable row-level
primary Evidence URL, and the existing benchmark reports provenance as
incomplete. Labor penalty legacy matching may use a company name without an
official uniform number; a name-only hit is not an Entity identity decision.
Both require row-level official-source comparison before making a coverage or
identity claim.

The 2026-10-18 bounded procurement materializer checks the exact eight-digit
bidder code and winner role in both the mirrored summary and detailed notice,
requires a stable agency/case/notice locator and an already registry-verified
Company, and rejects unsuccessful-tender notices. Its output is always draft
until the matching official PCC row is independently reviewed. A mirror record
alone does not increase published procurement coverage. The Development donor
candidate queue likewise distinguishes official-source donor IDs from verified
company entities; conflicting labels and other organization forms are held for
manual resolution.

On 2026-10-18, the original [PCC award notice](https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetailHist?fkPmsMainHist=OTcxMTg4NjM=)
was independently opened for agency `3.80.41`, case `115034`, notice
`BDM-1-71265329`. Its award date, exact bidder ID `04690983`, winner flag,
company name, and TWD 450,000 amount agreed with the staged mirror. A distinct
published **Primary Source** Evidence version now links that official row to
the published Contract and `CONTRACT_WITH` relationship in Development. The
earlier OpenFun Evidence and edge remain draft; the official locator retains
the mirror URL to explain the ingestion path. This verifies one award, not
national procurement coverage. The MOEA exact-ID registry API was reachable
again and independently confirmed three donor-ID/name pairs, but no political
contribution was published from those candidates: their original filing rows
and politician crosswalks still require separate review.

## Civil organizations (Development historical roster)

The official [MOI nationwide people's associations roster](https://data.gov.tw/dataset/13603)
was downloaded from its government CSV endpoint on 2026-10-24. It has 23,209
data rows after the bilingual header. The CSV supplies a row sequence and
name, but no durable registration number or unified tax ID. Development
therefore publishes each row as a separate `CivilOrganization` observation
with `SOURCE_SCOPED` identity, snapshot SHA-256, source row/sequence, retrieval
time, official source URL and immutable Evidence. This does **not** establish
current registration, legal status, activity, or identity across snapshots.
The source contains chairperson/address columns; neither is ingested.

Additional official snapshots were downloaded 2026-10-24: the [MOI national
civil foundations roster](https://data.gov.tw/dataset/152434), 17 rows, and
all five subresources of the [MOL union federation roster](https://data.gov.tw/dataset/6278),
243 rows. All 260 rows are published in Development as separate source-scoped
`CivilOrganization` observations, each with its original CSV snapshot hash,
source row, retrieval time, URL and Evidence. No chairperson, contact details,
name-only merge, or cross-source relationship is imported. These are roster
observations, not a deduplicated count of currently operating organizations.
The [Taipei City](https://data.gov.tw/dataset/121714) and
[Tainan City](https://data.gov.tw/dataset/53472) association rosters add
4,176 and 3,505 source-scoped observations respectively; the latter retains
the original dissolution month when supplied, and does not imply an active
organization. The [MOI civic-foundation permit roster](https://data.gov.tw/dataset/173726)
adds 8 more. Across these nine roster resources the total is 31,158
published observations and Evidence links in Development, not a unique NGO
count. Hsinchu City's official CSV failed TLS certificate validation; no
insecure download was used.

The later 2026-10-25 official-source expansion supersedes that interim total:
**54,307 published CivilOrganization roster observations from 87 official
sources**, each with an Evidence link, now exist in `tei-development`. This
includes 68 further profiled government CSV datasets, Keelung's official ODS,
Yilan's county CSV and Tainan's social-welfare foundation JSON. Source scope,
row counts and inaccessible/live-only exceptions are documented in
[`docs/CIVIL_ORGANIZATION_COVERAGE.md`](docs/CIVIL_ORGANIZATION_COVERAGE.md) and
[`docs/CIVIL_ORGANIZATION_NATIONWIDE_GAP_REGISTER.md`](docs/CIVIL_ORGANIZATION_NATIONWIDE_GAP_REGISTER.md).
No cross-source name merge, contact/office-holder import or current-legal-status
claim follows from this expansion. The current Development database size leaves
limited Free-tier capacity for additional source rows.

The official [MOF nonprofit tax dataset](https://data.gov.tw/dataset/34147)
was also downloaded 2026-10-24. Its **99,788 rows** are published in the
Development `nonprofit_tax_observations` source table, not promoted to Entity
or Relationship. 99,787 rows have a syntactically valid eight-digit tax ID;
one invalid identifier is retained and flagged rather than discarded. The
dataset includes forms beyond associations and its tax record is not proof of
NGO legal form or current registration. Every row keeps its source snapshot
SHA-256, CSV line, retrieval time, public source URL and original tax fields.
Matching to a civil organization, company or person is prohibited until an
official registration record independently confirms identity. The UI warns
that all civil-organization search hits are source-scoped observations.

This is **not** a complete census of Taiwanese NGOs. National MOI/MOL source
coverage does not include all local-government associations, foundations under
other ministries, charities, religious groups, or every historical version.
The [MOI group finder](https://www.moi.gov.tw/group.htm) is a separate live
query surface, not a bulk snapshot with a verified nationwide denominator.
See [civil-organization coverage](docs/CIVIL_ORGANIZATION_COVERAGE.md) for the
source-by-source denominator, known gaps and repeatable checks. Retain all CSV
snapshots securely outside the repository; a hash alone cannot recreate
later-changed upstream bytes.
