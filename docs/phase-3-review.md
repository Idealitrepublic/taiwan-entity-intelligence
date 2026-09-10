# Phase 3 — Graph 2.0 Review

## Delivered

- Entity 搜尋結果進入可分享的 `/graph/{entity_id}`，`/entity/{entity_id}` 亦可直接載入。
- Node 逐點 lazy expansion；每次 12 edges、最多 60 nodes、最深 3 hops。
- Entity ID 與 Relationship ID 去重，cycle 不會重複建立節點或邊。
- 固定由左向右依 hop 分欄，同欄垂直等距；保留 pan、0.5–3× zoom 與點擊放大動畫。
- Edge 可點擊，顯示來源／目標、日期、金額／比例、confidence、primary evidence、來源紀錄、取得日期與原始連結。
- Relationship type filter 會清空舊 lazy state 並由 root 重新查詢。
- 舊有 8 碼統編調查、分類圖、董監事、裁判、標案、裁罰與 165 查核維持相容。

## Database and API verification

- Applied migration: `graph_neighbors_rpc`.
- `graph_entity_neighbors` 為 `SECURITY INVOKER`，使用既有 public read RLS，未使用或公開 service-role key。
- 匿名角色實際查詢台積電 Entity：10 rows、focus ID 全部正確、Evidence 全部為 active。
- `GET /api/v1/graph/{id}` 驗證 UUID、limit 1–25、cursor 與 relationship type allowlist。
- 每個 node expansion 只呼叫一次 Supabase RPC，不產生 edge-by-edge N+1。

## Verification

- `node scripts/check_web_syntax.cjs`: pass.
- `npm test`: 52 Python unit tests pass；44 PGlite/PostgreSQL checks pass.
- `npm run build`: pass；36 Python modules、WSGI entrypoint 與資產通過檢查。
- `npm run dev`: WSGI server 成功啟動；本機 loopback 無法由 cloud browser 存取，改以同一 commit 的 Vercel Preview 完成 UI 驗證。
- `npm run lint`: 待 GitHub CI 執行。當前容器缺少 pinned `ruff==0.12.12`，離線套件快取亦不存在；JavaScript syntax check 已獨立通過。

## Preview browser verification

- Vercel Preview `dpl_Cau5Yj9DeZFnqXy6J4sK7WYMQiyZ`: READY；build errors 0、最近一小時 runtime error clusters 0。
- `/graph/1c18c9d1-06dc-5bfd-93f1-b1494d905e98` 實際載入台積電 11 nodes／10 relationships。
- Node 點擊：選取動畫為 `node-pop`，computed transform 約 1.5×；1-hop node 可執行 lazy expansion。
- Edge 點擊：顯示 `DIRECTOR_OF` 的 source／target、confidence、MOEA/GCI primary evidence、source record 與可開啟原始連結。
- Filter：`RELATED_TO_PENALTY` 得 1 node／0 edge，切回 `DIRECTOR_OF` 得 11 nodes／10 edges，舊 state 未混入。
- Zoom：100% → 110%；pan 後 SVG transform 確實改變。
- Toolbar 改為兩列後所有可見按鈕高度至少 32px，中文／英文不再被擠成直排；應用程式來源的 console errors 0，error overlay 0。

## Supabase advisors

本 Phase 沒有新增 security／performance finding。既有專案仍有：

- `api_cache`、`source_runs` 啟用 RLS 但沒有 public policy（刻意保持 backend-only）。
- `pg_trgm`、`pg_net` 位於 `public` schema。
- 舊 `evidence` table 有重複日期 index。
- 多個新索引尚未累積 production usage，advisor 暫列 unused。

## Remaining release gates

- GitHub CI lint/build/test.
- PR review、merge、production smoke test。
