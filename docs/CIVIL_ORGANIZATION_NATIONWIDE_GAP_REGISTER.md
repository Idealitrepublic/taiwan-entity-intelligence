# 全臺民間團體官方來源與缺口清單 — 2026-10-25

本清單記錄已取得的官方來源與未解決缺口；「已發布」指 Development 的來源紀錄，不代表該縣市所有現存團體均已收錄。完整原檔與可驗證識別資訊不足時，不以名稱推定同一團體。

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
| 新竹市 | [Official 12 social-group category pages](https://society.hccg.gov.tw/ch/home.jsp?id=161&parentpath=0,3,34), 1,023 source rows | All 12 website categories reconciled to displayed totals; category dates range from 111-12-20 to 115-10-16. [Open-data CSV 129137](https://data.gov.tw/dataset/129137) still fails TLS validation; cooperatives and other legal forms are outside these social-group pages |
| 嘉義市 | Community associations 52394; charity foundations 145146 | [General social-group roster 165216](https://data.gov.tw/dataset/165216) redirects to a third-party document, not accepted as a verified immutable download |
| 新竹縣 | [115年10月5日人民團體名冊](https://social.hsinchu.gov.tw/News.aspx?n=218&sms=8679)，十四類共2,181筆；另有舊版名冊109320的70筆、社區發展協會109324與基金會資料 | 新舊來源可能重疊；來源紀錄不可直接當作不同團體總數，也不推定現行狀態 |
| 苗栗縣 | Community associations 174251; [official society ODS](https://sas.miaoli.gov.tw/roster_society), 2,388 rows | Source category/date retained; legal status not independently certified |
| 彰化縣 | Community associations 107897; [official society ODS dated 2026-10-16](https://www.chcg.gov.tw/DTO/social/07other/other01_con.aspx?cate_id=5105&data_id=20273&topsn=716), 2,375 rows | Roster contains historical dissolution/name annotations; current active status not inferred. Catalog file 107985 has only three rows and remains excluded |
| 南投縣 | None | [County open-data roster resource](https://data.nantou.gov.tw/dataset/05ec1e11-5b3e-4416-a2fb-4b3d59fddc60/resource/dbbc5897-0181-4aac-aeee-eb7726b160c2/preview) appears to be a 2020 snapshot, but live file requests return HTTP 403/empty response. [Current county download page](https://welfare.nantou.gov.tw/1486/2048) displays zero files. County [September 2026 release](https://www.nantou.gov.tw/big5/news_content.php?cid=75&dptid=376480000&id=168888) reports 1,671 groups plus 280 community associations, but provides counts rather than a named roster. No authorization bypass or fabricated rows |
| 雲林縣 | [Official 2026-07-13 people-group XLSX](https://social.yunlin.gov.tw/News_Content.aspx?n=746&s=578203), 1,881 source rows; social-welfare foundation roster 161037 | XLSX contains a repeated official sequence number and one blank sequence, so XLSX sheet/row is the immutable locator. Five names have a `休會` prefix; current active status not inferred. [Community association file 114352](https://data.gov.tw/dataset/114352) remains unavailable |
| 嘉義縣 | [General people-group roster 133902](https://data.gov.tw/dataset/133902); community associations 133900 | Current status unverified |
| 屏東縣 | [General people-group roster 142753](https://data.gov.tw/dataset/142753); education/social-welfare foundations | Current status unverified |
| 宜蘭縣 | [Official 2026-09-30 county roster](https://sntroot.e-land.gov.tw/cp.aspx?n=10437), 1,619 rows | Older open-data catalog listing 46186 was absent from the exported catalog; the county file is a dated snapshot, not a live certificate |
| 花蓮縣 | Community associations 159507 | [County's general group list](https://sa.hl.gov.tw/Detail_sp/1805d7aa256b425a8ea1d106ca9d2b74) links to a live third-party query service, not a verified bulk snapshot |
| 臺東縣 | Community associations 165816 | Dataset explicitly covers 109年度; no current general roster validated |
| 澎湖縣 | [十二類官方人民團體名冊](https://data.gov.tw/dataset/166901)，有效名稱共595筆；另有社區發展協會113361 | 原檔共607列，其中12列無團體名稱；各類資料日期不同，環保類僅1筆，不能宣稱涵蓋現行全部團體 |
| 金門縣 | Community associations 174365; [official social-group XLSX](https://social.kinmen.gov.tw/Content_List.aspx?n=5953401623861323), 498 rows | This is the county's social-group category, not proof that every local legal form is covered |
| 連江縣 | None | [Official people-group ODS 146417](https://data.gov.tw/dataset/146417) download yielded a tiny HTML response, not an ODS file |

已查找全部22縣市，但不表示其團體資料已全部收錄；南投縣與連江縣仍無可用的地方名冊快照。查核現行登記狀態，仍須以[內政部團體查詢](https://www.moi.gov.tw/group.htm)及各地方主管機關為準。Development 既有23,209筆內政部全國名冊是歷史開放資料快照。

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
