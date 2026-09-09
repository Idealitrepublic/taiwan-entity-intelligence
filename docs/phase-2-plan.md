# Phase 2 — Global Entity Search

## 1. 影響範圍

將首頁的公司統編入口升級為 Entity 搜尋入口，同時保留既有 8 碼公司調查。搜尋只回傳 Phase 1 已發布的 Entity，不會以姓名合併人物。

## 2. 修改檔案

- `supabase/migrations/20260909191509_global_entity_search.sql`
- `src/entities/search.py`
- `src/entities/repository.py`
- `src/entities/api.py`
- `web/index.html`
- `tests/test_entity_search.py`
- `tests/entity_schema.test.mjs`
- build、deployment 與 Phase 2 review 文件

## 3. Database migration

- 新增 RLS 保護的公開搜尋詞與公司統編投影；private identifier registry 仍不可讀。
- 已發布名稱的 prefix 索引；Supabase 有 `pg_trgm` 時建立 contains 索引，PGlite 沒有 extension 時安全略過。
- 新增 bounded、`SECURITY INVOKER` 的 `search_entities` RPC。函式只輸出公開 Entity 欄位、公司統編及已發布關係摘要。

## 4. API changes

- `GET /api/v1/search?q=...&entity_type=...&limit=...`
- 名稱查詢 2–100 個可列印字元，最多 20 筆。
- entity type 必須在 Phase 1 allowlist。

## 5. UI changes

- 搜尋公司名稱、統編、人物、政治人物與政府機關。
- 類型篩選及依 Entity type 分組結果。
- 同名人物保留為獨立結果，並顯示來源關係脈絡。
- 點公司結果沿用完整舊公司調查；點其他實體顯示其已發布 profile 與證據。

## 6. Risks

- 現有 Entity 回填範圍有限，介面必須標明為「已索引公開實體」，不可宣稱完整全國名錄。
- 姓名不是唯一識別碼；任何同名結果都不可自動合併。
- contains 搜尋可能昂貴，因此限制長度與筆數，並在 production 使用 trigram partial indexes。
- 搜尋 RPC 使用呼叫者權限；投影同步 trigger 位於 private schema 且不可由匿名端執行。
