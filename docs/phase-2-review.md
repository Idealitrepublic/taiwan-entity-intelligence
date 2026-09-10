# Phase 2 審查與驗證

## 交付結果

Phase 2 在 `feature/global-search` 實作全實體搜尋，PR #2 以 Phase 1 production commit `bbc78c2` 為基準。既有 8 碼統編調查保留；名稱搜尋改走已發布 Entity 索引。

## Search contract

`GET /api/v1/search?q=...&entity_type=...&limit=...`

- `q`：2–100 個可列印字元。
- `entity_type`：Phase 1 allowlist，可省略。
- `limit`：1–20，預設 20。
- 回傳獨立 `entity_id`、entity type、名稱、公開公司統編、已發布關係脈絡與 match type。
- match type：`identifier_exact`、`name_exact`、`name_prefix`、`name_contains`。
- 同名人物不去重為單一自然人；每筆來源觀測保留自己的 Entity ID。

## Database 與安全

- Migration：
  - `20260909191509_global_entity_search.sql`
  - `20260909193500_global_entity_search_security.sql`
  - `20260909194000_relationship_type_fk_index.sql`
- `entity_search_terms` 只存公開名稱／別名；`entity_public_identifiers` 只允許 8 碼 `tw:uniform_number`。
- 兩表均開啟 RLS；匿名角色只能讀取對應已發布 Entity 的投影，不能寫入。
- `entity_identifiers` 仍無 anon/authenticated SELECT。
- 搜尋 RPC 為 `SECURITY INVOKER`、固定空 `search_path`、固定輸出欄位、literal LIKE escaping 與 20 筆上限。
- 初版 `SECURITY DEFINER` advisor 警示已在進入 Preview 前修正；再次執行 security advisor 後，Phase 2 無新增警示。
- `relationships.relationship_type` FK 已補 covering index；performance advisor 不再回報 unindexed FK。

既有 advisor 項目未在本 Phase 擴張處理：`pg_trgm`／`pg_net` 位於 public、兩個後端表無公開 policy、舊 evidence duplicate index。移動既有 extension 或刪舊 index 可能影響舊流程，應另案處理。

## UI

- 搜尋框支援公司名稱、統編、人物、政治人物、政府機關、政黨、標案與裁判類型。
- 結果依 entity type 分組，顯示 match type、關係脈絡及 Entity ID 短碼。
- 點公司結果執行既有完整公司調查；其他實體顯示 profile、identity status 與來源證據。
- 明示目前只涵蓋已索引、已發布 Entity，並明示同名不代表同一人。
- desktop 與 mobile 均有搜尋欄與結果層尺寸規則；所有新增文字為中文＋英文。

## 驗證

- `npm run lint`：通過，包含 Ruff 與內嵌 JavaScript parse。
- `npm run build`：36 個 Python 模組、WSGI entrypoint 與部署資產通過。
- `npm test`：45 項 unittest＋39 項真實 PostgreSQL（PGlite）檢查通過。
- `npm run dev`：Python WSGI 實際啟動；完成後正常停止。
- 本機 WSGI dispatch 經正式 Supabase/PostgREST 驗證：
  - `台灣積體電路` → Company／`name_prefix`
  - `魏哲家`＋Person → Person／`name_exact`
  - `22099131`＋Company → Company／`identifier_exact`
- Vercel Preview `dpl_FfUFnLAqyNJwUsLSCt79smdSCjjU`：READY。
- Preview API 公司名稱搜尋回傳 200；其餘查詢由本機 WSGI→正式 PostgREST 與 SQL/RLS 雙重驗證。
- GitHub：T.E.I. tests、live smoke tests、Entity model checks、Vercel 全數成功。
- PR #2 已合併；Production commit `ca06f90`、deployment `dpl_CLRPeVVozfjKkaTPGaJ9ctpewGg6` 均 READY。
- Production：首頁、公司名稱搜尋、人物＋類型、公司統編均回傳 200；一字查詢正確回傳 400。

## 已知限制與回復

- 目前 Entity 層只有 Phase 1 已回填／發布的資料；搜尋無結果不代表政府資料不存在。
- 8 碼公司即時查詢涵蓋範圍可能大於 Entity 索引，因此保留 legacy fallback。
- 搜尋只呈現公開資料關聯，不做違法、利益衝突或同一人判定。
- 回復 UI/API 時可回滾 Vercel commit；資料庫 migration 為 additive。若需停用新 API，可設定 `TEI_ENTITY_API_ENABLED=0`。搜尋投影表可保留，不影響舊公司 API。
