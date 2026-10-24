# Nationwide civil-organization source and exception register — 2026-10-25

This is a **bounded discovery inventory**, not a claim that every currently
registered Taiwanese association, NGO or foundation is in T.E.I. The unit of
the Development import is one official roster observation. The 2026-10-24
[government catalog export](https://data.gov.tw/datasets/export/csv?type=dataset&order=pubdate&qs=&uid=)
was supplemented with county government pages because the export omitted at
least Yilan's current roster. Full source URLs, schemas, counts and scopes are
in [`src/civil_roster_manifest.json`](../src/civil_roster_manifest.json) and
[`CIVIL_ORGANIZATION_COVERAGE.md`](CIVIL_ORGANIZATION_COVERAGE.md).

## 22 local jurisdictions

| Jurisdiction | Published official source observations in Development | Remaining exception / scope limit |
|---|---|---|
| 臺北市 | [General people-group roster 121714](https://data.gov.tw/dataset/121714); education, culture and social-welfare foundation rosters | Different competent authorities remain separate; current status unverified |
| 新北市 | [Community associations 124618](https://data.gov.tw/dataset/124618); charity, education and culture foundations | No downloadable general people-group roster verified; [official social bureau portal](https://social.ntpc.gov.tw/) is a live service |
| 桃園市 | [Community associations 32265](https://data.gov.tw/dataset/32265); religious foundations 26480 | General roster 147530 withdrawn; [official group lookup](https://sab.tycg.gov.tw/News_Content.aspx?n=7341&s=684701) is live only |
| 臺中市 | 15 separate [people-group category files](https://data.gov.tw/dataset/159897), community associations 91949 and sectoral foundations | Category sources overlap; cooperatives/credit unions deliberately excluded as different forms; not one exhaustive roster |
| 臺南市 | [General people-group roster 53472](https://data.gov.tw/dataset/53472); culture, economic and social-welfare foundation files | Local foundation sources overlap; dissolution/status retained as raw source fields, not current legal finding |
| 高雄市 | 13 separate [people-group category files](https://data.gov.tw/dataset/128181); charity, culture and religious foundation files | Category source overlap and completeness unverified |
| 基隆市 | [General ODS people-group roster 165174](https://data.gov.tw/dataset/165174), 823 source rows | Original ODS retained by hash; snapshot freshness/current legal status not certified |
| 新竹市 | None | [Official people-group CSV 129137](https://data.gov.tw/dataset/129137) and district community CSVs failed TLS certificate verification; no bypass or unverified copy |
| 嘉義市 | Community associations 52394; charity foundations 145146 | [General social-group roster 165216](https://data.gov.tw/dataset/165216) redirects to a third-party document, not accepted as a verified immutable download |
| 新竹縣 | [General people-group roster 109320](https://data.gov.tw/dataset/109320); community associations 109324; culture/religious foundation files | General CSV has only 70 rows; source scope and currency must not be extrapolated |
| 苗栗縣 | Community associations 174251 | [Official society lookup](https://sas.miaoli.gov.tw/roster_society) is live HTML; no bulk snapshot validated |
| 彰化縣 | Community associations 107897 | Catalog file 107985 contains only three rows with fields unlike a general roster; excluded |
| 南投縣 | None | [General roster 129917](https://data.gov.tw/dataset/129917) and [community associations 94910](https://data.gov.tw/dataset/94910) returned HTTP 403, including direct county file; no authorization bypass |
| 雲林縣 | Social-welfare foundation roster 161037 only | [Community association file 114352](https://data.gov.tw/dataset/114352) failed download; county's [public sheet](https://social.yunlin.gov.tw/News_Content.aspx?n=737&s=455347) uses abbreviated names and is not a verified full-name snapshot |
| 嘉義縣 | [General people-group roster 133902](https://data.gov.tw/dataset/133902); community associations 133900 | Current status unverified |
| 屏東縣 | [General people-group roster 142753](https://data.gov.tw/dataset/142753); education/social-welfare foundations | Current status unverified |
| 宜蘭縣 | [Official 2026-09-30 county roster](https://sntroot.e-land.gov.tw/cp.aspx?n=10437), 1,619 rows | Older open-data catalog listing 46186 was absent from the exported catalog; the county file is a dated snapshot, not a live certificate |
| 花蓮縣 | Community associations 159507 | [County's general group list](https://sa.hl.gov.tw/Detail_sp/1805d7aa256b425a8ea1d106ca9d2b74) links to a live third-party query service, not a verified bulk snapshot |
| 臺東縣 | Community associations 165816 | Dataset explicitly covers 109年度; no current general roster validated |
| 澎湖縣 | Community associations 113361 | No general local roster validated |
| 金門縣 | Community associations 174365 | No general local roster validated |
| 連江縣 | None | [Official people-group ODS 146417](https://data.gov.tw/dataset/146417) download yielded a tiny HTML response, not an ODS file |

Every jurisdiction was researched; this does **not** mean its full legal-entity
population is covered. In particular, four jurisdictions have no usable
people-group snapshot (新竹市、南投縣、雲林縣、連江縣), although 雲林縣 has one
foundation roster. The [Interior Ministry's live group lookup](https://www.moi.gov.tw/group.htm)
and each local competent authority remain the definitive places to check
current standing. The 23,209 national MOI records already in Development are
a historical open-data snapshot.

## Central and sectoral authorities

Development now includes roster observations from the Interior, Labor,
Education, Agriculture, Sports and Mainland Affairs ministries; local
education, culture, social-welfare, religion and economic authorities;
government-funded foundation subsets; and five Labor Ministry union lists.
The manifest records exactly which official dataset covers each source.
The [Culture Ministry's dataset 94846](https://data.gov.tw/dataset/94846)
currently returns one *attachment index row*, not the foundation roster
itself; that index is not mispublished as an organization. The [Science and
Technology Council listing 7612](https://data.gov.tw/dataset/7612) contains
webpage titles/links rather than a checked legal roster. Sectoral authority
coverage has no defensible exhaustive denominator; legal form and current
status cannot be inferred from tax listings or matching names.

## Release gate and next refresh

The accepted completion criterion for this source-acquisition pass is:
accessible, verified official roster snapshots in Development with one Evidence
link per row, and **explicit exceptions** for unavailable/unpublished/live-only
sources. That criterion is met for the sources enumerated here; it is not the
stronger claim of 100% of organizations or authorities. Further source
discovery, live-register export permission, renewal, source versioning,
deduplication by a verified identifier and status reconciliation remain open.
Never fabricate missing records or merge by name. Before any Production use,
recheck source currency, license and database headroom, and obtain release
approval through the normal Preview gate.
