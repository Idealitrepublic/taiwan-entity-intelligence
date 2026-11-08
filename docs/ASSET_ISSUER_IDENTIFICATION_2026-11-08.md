# 12 筆財產申報公司識別覆核（2026-11-08）

**識別資料查核已執行；不等於 12 筆正式持股連結已完成。**
範圍限廉政專刊 319 期、黃珊珊 2026-02-01 申報中既有 12 列。
本輪在 tei-development 新增 21 份 Evidence（9 份登記識別＋12 份逐列覆核），沒有新建公司、改動原申報、填入公司 FK 或發布股權線；Production 未修改。

## 逐筆中文清單

| 筆次 | 原申報對象 | 官方法人／識別碼 | 角色 | 覆核狀態 |
|---|---|---|---|---|
| 1 | 聯嘉投控 | [聯嘉光電投資控股股份有限公司](https://findbiz.nat.gov.tw/fts/company/60654582)／臺灣統編 `60654582` | 股票發行人；股別未確認 | 官方登記識別已核對；原申報連結未核准 |
| 2 | 國泰人壽保險股份有限公司 | [國泰人壽保險股份有限公司](https://findbiz.nat.gov.tw/fts/company/03374707)／臺灣統編 `03374707` | 保險提供者；不是持股 | 官方登記識別已核對；原申報連結未核准 |
| 3 | NVIDIA Corp | [NVIDIA CORP](https://www.sec.gov/Archives/edgar/data/1045810/000104581025000023/0001045810-25-000023-index-headers.html)／美國 SEC CIK `0001045810` | 股票發行人；股別未確認 | 官方登記識別已核對；原申報連結未核准 |
| 4 | 富邦人壽保險股份有限公司 | [富邦人壽保險股份有限公司](https://findbiz.nat.gov.tw/fts/company/27935073)／臺灣統編 `27935073` | 保險提供者；不是持股 | 官方登記識別已核對；原申報連結未核准 |
| 5 | Palantir Technologies | [Palantir Technologies Inc.](https://www.sec.gov/Archives/edgar/data/1321655/000132165526000011/R1.htm)／美國 SEC CIK `0001321655` | 股票發行人；股別未確認 | 官方登記識別已核對；原申報連結未核准 |
| 6 | Berkshire Hathaway Inc | [BERKSHIRE HATHAWAY INC](https://www.sec.gov/Archives/edgar/data/1067983/000119312526083899/0001193125-26-083899-index-headers.html)／美國 SEC CIK `0001067983` | 股票發行人；股別未確認 | 官方登記識別已核對；原申報連結未核准 |
| 7 | 南山人壽保險股份有限公司 | [南山人壽保險股份有限公司](https://findbiz.nat.gov.tw/fts/company/11456006)／臺灣統編 `11456006` | 保險提供者；不是持股 | 官方登記識別已核對；原申報連結未核准 |
| 8 | 富邦人壽保險股份有限公司 | [富邦人壽保險股份有限公司](https://findbiz.nat.gov.tw/fts/company/27935073)／臺灣統編 `27935073` | 保險提供者；不是持股 | 官方登記識別已核對；原申報連結未核准 |
| 9 | Tesla Inc | [Tesla, Inc.](https://www.sec.gov/Archives/edgar/data/1318605/000195004725000663/0001950047-25-000663-index-headers.html)／美國 SEC CIK `0001318605` | 股票發行人；股別未確認 | 官方登記識別已核對；原申報連結未核准 |
| 10 | 國泰人壽保險股份有限公司 | [國泰人壽保險股份有限公司](https://findbiz.nat.gov.tw/fts/company/03374707)／臺灣統編 `03374707` | 保險提供者；不是持股 | 官方登記識別已核對；原申報連結未核准 |
| 11 | Figma Inc | [Figma, Inc.](https://www.sec.gov/Archives/edgar/data/1579878/999999999525002410/xslEFFECTX01/primary_doc.xml)／美國 SEC CIK `0001579878` | 股票發行人；股別未確認 | 官方登記識別已核對；原申報連結未核准 |
| 12 | 富邦人壽保險股份有限公司 | [富邦人壽保險股份有限公司](https://findbiz.nat.gov.tw/fts/company/27935073)／臺灣統編 `27935073` | 保險提供者；不是持股 | 官方登記識別已核對；原申報連結未核准 |

## 為何沒有直接填入公司 FK

原件股票列只提供公司名稱、股數及價額，保單列提供保險公司與商品名稱，沒有統編、CIK、證券代碼或股別。
本輪識別是以指定原件列／角色對照官方登記資料的人工來源覆核，信心標為 HIGH；不是來源直接帶 ID 的 EXACT 配對。
聯嘉投控另核對證交所 2025-08-15 上市公告，避免錯接原聯嘉光電（6288）。
富邦人壽的「安泰」保單名稱不改寫成保單品牌同名公司；官方登記顯示現法人統編 27935073 及更名前名稱。
美股不接臺灣子公司；Berkshire、Figma、Palantir 等發行人識別不代表已知道 A/B/C 股別，不用股價回推股別。
保單不是保險公司股份，不得建立 ASSET_OWNERSHIP 或 BUSINESS_INVESTMENT。
既有資產發布約束仍要求原件統編精確配對，未為讓數字變成非零而放寬。**company_entity_id 目前仍 0，正式持有關係仍是未完成項目。**

## 官方資料與 provenance

- 四家臺灣公司：本輪已直接下載經濟部官方統編 JSON，核對公司全名、統編與 SHA-256，快照在 repo 外私有目錄。
- 五家美國公司：SEC 原站申報頁／生效通知／XBRL cover 已核對公司名稱及 CIK；直接 bulk submissions API 返回 403。證據明記以官方頁面欄位經網頁工具覆核，沒有宣稱 bulk API 可用、下載了原始 JSON 或捏造原檔 SHA。
- 每份逐列覆核保留 asset_declaration_id、原 Evidence ID、原 PDF SHA、官方登記 Evidence ID、官方 URL、取得時間、角色、匹配方法、HIGH 與未發布股權標記。
- 原始財產 Evidence、金額、數量、公司名稱、任期識別及取得時間均未覆寫；新增覆核取得時間不當成原申報資料更新。
- 沒有建立全域公司名稱別名或自動模糊合併；聯嘉簡稱依據只用於這組人工覆核。

## 操作、驗收及回復

已先完成 tei-development 的 age 加密備份、解密封存驗證，再以容量保護與單一交易新增身份 Evidence。
原資產 63 筆、原公開 Relationship 1,391 條不變；Evidence 由 67,227 增為 67,248。
重現（預設唯讀 dry-run；所有 connection 值只在已忽略且 0600 的 .env.local）：

```sh
.venv/bin/python scripts/review_asset_issuers_dev.py <repo外私有快照目錄> --filing-pdf <已核對原件PDF>
```

寫入必須另給 --apply-dev 與 --backup-directory，僅接受 24 小時內已驗證的 Development 加密備份。
若需撤回：只按該批 receipt 的 21 個 Evidence ID、指定 source_name 將 publication_status 設為 withdrawn；保留原檔與 entity_evidence 履歷，不刪除或還原整庫，不更動原 63 筆資產。
完整逐筆機器可讀明細：reports/asset_issuer_identification_2026-11-08.json。
本輪是身分覆核，不宣稱全國資產 coverage、特定證券股別或目前實際持股已獲外部確認。

## 最終驗收結果

- 8 項新針對性回歸測試通過；完整 526 項 Python tests、既有 JavaScript suites、181 項 PGlite DB checks、lint 與完整 build 通過。
- Development 實際 apply 及第二次重跑均成功；公開的身分覆核仍 12、登記 Evidence 仍 9，沒有重複。
- 匿名 anon 實際讀取全部 21 份 Evidence 成功，12 個來源資產 ID 唯一；6 筆保單 role 均為 insurance_provider。
- 原公開資產仍 63、公司 FK 仍 0、既有公開 Relationship 仍 1,391；非把未核准關係偽裝成完成。
- 加密備份已驗證；本輪未進行新一次隔離還原，也未宣稱 Supabase 平台級還原完成。
- 未改 UI、API、schema／RLS 或 Production；本輪只交付逐筆識別證據與操作驗證。
- Preview 分支驗收入口：https://taiwan-entity-intelligence-git-fix-764717-coldlight871029-9944.vercel.app/
  部署狀態及實際 source commit 另由 Vercel 回應核對。
