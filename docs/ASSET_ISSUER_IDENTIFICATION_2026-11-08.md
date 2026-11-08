# 12 筆財產申報公司識別覆核（2026-11-08）

**初次識別覆核結果（後續已由文末修正紀錄更新）：**當時只新增識別 Evidence，尚未建立申報列 FK／持股 Relationship。
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

## 持股連結阻塞修正（2026-11-08，已完成）

**根因**：Phase 7 的 DB validator 只認原始申報 Evidence locator 中的
`company_match_method=exact_uniform_number` 與八碼臺灣統編。這 12 列原件只有名稱，
美國發行人使用 SEC CIK；前一輪新增的身分 Evidence 沒有 FK 欄位可掛到申報列，
所以即使已有官方登記與逐列覆核，6 筆股票仍無法發布公司 FK／Relationship。

修正加入 nullable `company_identity_evidence_id`：原財產 Evidence 和原始欄位保持不變；
僅以行內核准 Evidence→逐列覆核→官方登記 Evidence→公司精確 identifier 的鏈路
允許 `HIGH` 身分配對。6 筆股票可建立 HIGH 發行人層級 `ASSET_OWNERSHIP`，不推測股別，
也不宣稱已重新驗證目前持有；6 筆保險只標記保險提供者，沒有持股／投資線。
Evidence 失效會撤回資產與相關關係。原始名稱不會做全域 alias 或模糊合併。

修正已套用至 **tei-development**（migration `20261108070814`）。執行前已建立並驗證
age 加密備份；核准對照預演通過後，以單一交易建立／精確重用 9 家發行人 Entity，
逐列連結 12 筆申報，為 6 筆股票建立 `HIGH` 信心 `ASSET_OWNERSHIP`，6 筆保險僅連到保險提供者。
申報金額、數量、日期、原 Evidence 與來源內容不變；沒有將保單改成持股，也不推斷股票類別或當前仍持有。

### 修復驗收

- Development：63 筆已發布資產；12/12 目標列可見公司連結；其中 6 筆股票有 6 條持股關係，6 筆保險沒有持股關係。總已發布 Relationship 為 1,397（新增 6 條）。
- 12 筆均有 active/published 的身分核准 Evidence；精確官方識別碼存在；缺失證據或識別碼的連結為 0。
- 實際以 PostgreSQL `anon` role 驗證 RLS：公開讀取 12 筆連結資產、6 條持股線、12 份核准 Evidence 與 24 個人物／公司 Evidence 關聯。
- 資料庫大小約 475.7 MB，仍低於本次執行工具設定的 480 MB 保護上限。
- 30 個 targeted Python tests、189 個 PGlite migration／RLS checks 通過；完整 528 個 Python tests、所有 package.json UI/JS 測試、lint、build check 通過。
- 本機沒有 `npm` 命令；使用專案指定的 Python build checker 與已安裝 Node runtime 執行 package.json 所列測試。
- Production 未修改。Commit `c7186f5952a2d335ef914dedaae704b8fb5859c6` 的 Vercel Preview 為 READY：<https://taiwan-entity-intelligence-njq6nhhyq-coldlight871029-9944.vercel.app/>；Deployment build 成功，該部署目前沒有 runtime error log。
