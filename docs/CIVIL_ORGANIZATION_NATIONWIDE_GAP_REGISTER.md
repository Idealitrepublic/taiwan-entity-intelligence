# Civil-organization nationwide gap register (2026-10-24)

This is a **source inventory, not a completeness claim**. The unit of the
existing Development import is an official roster observation, not a unique,
currently registered organization. The government open-data catalog snapshot
used for discovery is the official [dataset export](https://data.gov.tw/datasets/export/csv?type=dataset&order=pubdate&qs=&uid=)
retrieved 2026-10-24. Its source rows are retained outside Git. Catalog
metadata and row counts do not prove that a downloadable file is current or
complete; every candidate below still needs file/header, scope, license,
freshness, row-count, and Evidence checks before publication.

## Local-government people's organizations

| Jurisdiction | Official discovery lead | Development status |
|---|---|---|
| 臺北市 | [121714](https://data.gov.tw/dataset/121714) | 4,176 source-scoped observations published |
| 新北市 | [124618](https://data.gov.tw/dataset/124618) covers community associations only | 470 subset observations published; no general local roster |
| 桃園市 | [147530](https://data.gov.tw/dataset/147530) is withdrawn; [32265](https://data.gov.tw/dataset/32265) covers community associations only | No general local roster published |
| 臺中市 | [159897](https://data.gov.tw/dataset/159897) and other category-specific city rosters | 594 academic-cultural observations published; other categories missing |
| 臺南市 | [53472](https://data.gov.tw/dataset/53472) | 3,505 source-scoped observations published |
| 高雄市 | [128181](https://data.gov.tw/dataset/128181) and other category-specific city rosters | 1,747 charity observations published; other categories missing |
| 基隆市 | [165174](https://data.gov.tw/dataset/165174) (ODS) | Not published |
| 新竹市 | [129137](https://data.gov.tw/dataset/129137) | Not published; official CSV TLS chain failed validation; do not bypass |
| 嘉義市 | [165216](https://data.gov.tw/dataset/165216) | Not published |
| 新竹縣 | [109320](https://data.gov.tw/dataset/109320) | Not published |
| 苗栗縣 | [174251](https://data.gov.tw/dataset/174251) covers community associations only | No general local roster published |
| 彰化縣 | [107985](https://data.gov.tw/dataset/107985) | Not published; source scope/row count to verify |
| 南投縣 | [129917](https://data.gov.tw/dataset/129917) | Not published |
| 雲林縣 | [114352](https://data.gov.tw/dataset/114352) covers community associations only | No general local roster published |
| 嘉義縣 | [133902](https://data.gov.tw/dataset/133902) | Not published |
| 屏東縣 | [142753](https://data.gov.tw/dataset/142753) | 3,440 source-scoped observations published |
| 宜蘭縣 | No general roster identified in the catalog snapshot | Source discovery required |
| 花蓮縣 | [159507](https://data.gov.tw/dataset/159507) covers community associations only | No general local roster published |
| 臺東縣 | [165816](https://data.gov.tw/dataset/165816) is a year-specific community-association roster | No general local roster published |
| 澎湖縣 | [113361](https://data.gov.tw/dataset/113361) covers community associations only | No general local roster published |
| 金門縣 | [174365](https://data.gov.tw/dataset/174365) covers community associations only | No general local roster published |
| 連江縣 | [146417](https://data.gov.tw/dataset/146417) (ODS) | Not published |

The Interior Ministry says its [live "find a group" service](https://www.moi.gov.tw/News_Content.aspx?n=15255&s=263489)
is the source for current nationwide status. It also directs checks of local
organizations to county/city governments; see its
[public guidance](https://www.moi.gov.tw/News_toggle3.aspx?n=8361&sms=9015&_CSN=1633&page=2&PageSize=30).
The 23,209 nationwide records already imported are a historical open-data
snapshot, not a substitute for that live status service.

## Sectoral foundations and other organizations

Development contains 25 Interior Ministry foundation-roster observations,
15 Labor Ministry foundation-roster observations, 765 Education Ministry
foundation-roster observations, and 243 Labor Ministry union-roster observations.
The 99,788 Finance Ministry
nonprofit tax-unit rows are **tax-source observations only**. They are not
verified legal-form records and must not be automatically promoted to
CivilOrganization entities or merged by name. Official catalog leads for
additional competent authorities include [Agriculture Ministry 102156](https://data.gov.tw/dataset/102156),
[Sports Ministry 41892](https://data.gov.tw/dataset/41892), and
[Science and Technology Council 7612](https://data.gov.tw/dataset/7612).
This list is **not** an exhaustive enumeration of competent authorities;
additional central and local sectoral registries require discovery and
reconciliation. The term "all agencies" has no defensible denominator yet.

## Release gate for a nationwide-complete claim

Do not declare complete until the jurisdiction/authority denominator is
documented; each official source has a verified accessible snapshot or a
clearly recorded unavailable/withdrawn exception; downloaded row counts and
Development rows/Evidence reconcile; source dates and current-vs-historical
status are visible; duplicates, changes, and legal identifiers have been
reviewed; and public search/profile access is tested. Missing official data
must remain a coverage gap, never fabricated or inferred by name.
