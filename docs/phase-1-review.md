# Phase 1 審查與啟用說明

## 交付狀態

已實作 Entity、Relationship、Evidence 的基礎模型，保留既有公司查詢。
分支：`feature/entity-model`；既有正式站基準：`280689f`。
Phase 1 已合併至 `main`（PR #1），正式 Supabase migration、受控回填與 Vercel Production 均已完成並驗證。

本階段驗收範圍為資料模型、證據約束、讀取 API 及受控回填。
Global Search、Graph 2.0、Path Finder 與政治資料接入仍依後續 Phase 順序執行。

## 新資料模型

12 張新增表：`entity_types`、`entities`、`entity_identifiers`、`entity_aliases`、
`evidence_records`、`entity_sources`、`entity_evidence`、`relationship_types`、
`relationships`、`relationship_evidence`、`resolution_candidates`、`legacy_entity_map`。

- Internal UUID 不取決於名稱；公司使用 namespaced 統編，人物使用穩定職務來源列 ID。
- 公司改名不改 ID；同名人物不跨來源合併。
- 政治人物／政府官員類型預留，但本階段不聲稱已取得人物官方識別資料。
- 每條關係都有非空的 primary evidence FK，可另附多筆支持／反證／背景證據。
- 正式發布需 EXACT/HIGH、已發布端點及 active/published 的 primary evidence。
- 來源證據內容不可覆寫；修正建立新版本。舊證據撤回時，依賴它的正式關係自動撤回。
- 主要證據撤回後不會自動挑選另一筆次要證據替代；需要人工核對。
- 保存 observed_at、retrieved_at、有效起訖日及日期精度；未知生效日期保持 null。
- 登記股數保留 quantity/shares，不推導持股比例、受益所有權或違法結論。
- 高信心的「來源記載職務」不等於跨公司自然人身分已確認。人物仍標 SOURCE_SCOPED。
- 公司／人物的原始敏感欄位不複製到新表。公開來源 ID 必須是紀錄定位碼，不得填入身分證字號。

Migration：`supabase/migrations/20260909100626_entity_relationship_evidence.sql`。
檔名由 Supabase CLI `migration new` 建立，已在隔離 PostgreSQL 引擎實際執行。

## API

| Route | 行為 |
|---|---|
| GET `/api/v1/entities/{uuid}` | 已公開實體、屬性證據 |
| GET `/api/v1/entities/{uuid}/relationships` | 有界單跳關係列表 |
| GET `/api/v1/relationships/{uuid}` | 關係與主要／附加證據 |
| GET `/api/v1/evidence/{uuid}` | 已公開且有效的證據 |

列表使用 `limit`（1–50，預設 25）、`after` UUID cursor、`relationship_type`。
回傳 `has_more`／`next_cursor`，不把分頁筆數當成完整統計。
證據列表最多回傳 50 個附加來源並標示 evidence_has_more；完整證據分頁留待證據介面階段。
無效參數 400；未公開或不存在 404；未啟用／資料庫不可用 503；寫入方法 405。

正式 migration 已驗證後，API 預設啟用；`TEI_ENTITY_API_ENABLED=0` 是緊急關閉開關。
新資料庫讀取只用 anon key，無 service-role fallback。
`tei_ingest_bundle` 為 service-role 專用、SECURITY INVOKER、1 MB 有界交易寫入 RPC。
匿名／一般登入角色只有已公開資料的 SELECT 權限；識別碼、來源對照、比對候選為後端專用。

RLS/grants 的設計參考官方文件：
https://supabase.com/docs/guides/api/securing-your-api

## 回填結果與限制

唯讀匯出目前 3 家公司及 34 筆人物職務，經允許欄位轉換得到：

| 類別 | 數量 |
|---|---:|
| 實體 | 37 |
| 公司識別碼 | 3 |
| 證據 | 37 |
| 關係 | 34 |
| 舊資料對照 | 37 |
| 未映射／無效來源列 | 0 |

回填先輸出為 draft，核對後已在同一交易中發布至正式資料庫；`.build/` 暫存資料未提交 Git。
程序預設 dry-run，明確 `--apply` 才會寫入明確指定的 Supabase 目的地。
新來源不在本階段自動匯入；裁罰、裁判、標案仍走原流程，未大量搬入新模型。
監察人等未定義對應的角色會被報告為 skipped，不錯誤標記為董事。
原始資料日期缺失時會報告並跳過，不拿執行時間偽造歷史來源日期。
重複匯入保留現有資料與撤回狀態；名稱修正／身分合併需另行審查，不在重試中覆蓋。

## 驗證

- `npm run lint`：Python Ruff 與 HTML 內嵌 JavaScript 語法檢查通過。
- `npm run build`：35 個 Python 模組、WSGI 首頁與部署資產檢查通過。
- `npm test`：40 項單元測試＋29 項真實 PostgreSQL 引擎檢查通過。
- 本機 HTTP → 新 API → PostgreSQL → 實體／關係／證據：4 個端點全部 200，分頁上限正常。
- PostgreSQL 使用 PGlite 隔離引擎；HTTP 測試使用明確的本機查詢 adapter，不假裝是雲端 PostgREST。
- Vercel Preview build：READY（Python），部署 ID `dpl_2MawrEBX5vyQGLiGSzDht2KHDGSt`。
- Preview 瀏覽器：中華電信查詢成功，公司／董監事及三類紀錄列表呈現；縮放 100% → 110%，標案列表可切換。
- 第一版 Preview 新 API 回傳 503/not_enabled：符合當時正式 migration 尚未套用的設計。
- 瀏覽器錯誤紀錄來自擴充套件及先前 Vercel 登入頁，未觀察到本次 T.E.I. 頁面自身的 JavaScript error。

`npm test` 使用既有 unittest suite（16 項）加本次 24 項，並執行 PostgreSQL 檢查。
舊版直接連接多個政府網站的 4 項 pytest 測試獨立保留為 `npm run test:live`。
本次曾啟動該外部連線測試，但因網路核准取消未完成，不列為已通過。
不以本次驗證宣稱所有政府原始連結均可直接定位或所有來源當日完整同步。

## 本機重現

```sh
python -m pip install -r requirements-dev.txt
npm ci --ignore-scripts
npm run lint
npm run build
npm test
npm run dev
```

Python WSGI 才是正式 runtime；npm 只提供開發驗證命令，不代表專案改為 Next.js。

取得允許欄位的舊資料 snapshot 後：

```sh
python scripts/backfill_entity_model.py --input snapshot.json --output draft-bundle.json
node tests/entity_http_flow.cjs draft-bundle.json
```

此 HTTP 測試只在記憶體的隔離資料庫發布樣本，結束後消失。

## 部署與回復順序

1. 審查 migration、回填結果及公開欄位。
2. 在指定開發 Supabase 套用 migration，驗證實際 PostgREST／RLS 與 advisors。
3. 匯入 draft，核對來源；僅將核對過的 entity、evidence、relationship 在同一交易中發布。
4. 設定該開發資料庫對應 URL／anon key，Preview 啟用 `TEI_ENTITY_API_ENABLED=1`，驗證新 API。
5. Review 通過後才 Merge，正式資料庫套用 additive migration，再發布正式網站。
6. 回復時先關閉 `TEI_ENTITY_API_ENABLED`，保留新資料表與證據供檢查；不刪舊表或批次資料。

目前未建立付費 Supabase branch；migration 因此直接在既有專案依 additive、先測試後發布流程執行。
現有舊表的公開 raw 欄位、舊人物姓名合併及裁罰分類問題不在此階段偷偷重寫；新模型不沿用這些連接。

## Git 差異與自動審查限制

遠端 `main` 為 `f2c5cf5`，正式站／本機基準 `280689f` 包含 5 個先前尚未推送的提交。
Phase 1 的純變更範圍以 `280689f..feature/entity-model` 審查。

已核對並經使用者授權推送至公開 repository：
`Idealitrepublic/taiwan-entity-intelligence`。PR #1 的所有 CI 與 Vercel 狀態通過後，以 squash merge 合併；Production commit 為 `bbc78c2`。

## 現有雲端 advisor

正式資料庫唯讀 advisor 仍有既有項目；本次未修改舊 schema：

- `pg_trgm`／`pg_net` 位於 public：
  [官方修正說明](https://supabase.com/docs/guides/database/database-linter?lint=0014_extension_in_public)。
- `api_cache`／`source_runs` 啟用 RLS 但無 policy：
  [官方說明](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)。
  若僅供後端使用，無公開 policy 可為預期設計。

新 migration 的 RLS 與 grants 已在隔離 PostgreSQL及正式 Supabase 驗證；Phase 1 新表沒有 advisor 警示。
