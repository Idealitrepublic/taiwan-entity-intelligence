# Phase 3 — Graph 2.0

## 1. 影響範圍

在 Phase 1 Entity／Relationship／Evidence 模型上提供逐節點展開的 Knowledge Graph。既有公司統編聚合圖繼續保留，Entity 搜尋結果與可分享路由改用 Graph 2.0。

## 2. 修改檔案

- `src/entities/repository.py`：有界鄰居批次查詢。
- `src/entities/api.py`：Graph neighbor route 與 filter 驗證。
- `app.py`：`/entity/{id}`、`/graph/{id}` 頁面入口。
- `web/index.html`：Graph 2.0 state、lazy expansion、edge evidence、filter 與分層 layout。
- `tests/test_graph_v2.py`、既有 API／UI tests。
- `scripts/deployment_files.py`、README 與 Phase review 文件（如需）。

## 3. Database migration

- `20260909200000_graph_neighbors_rpc.sql`：新增 `SECURITY INVOKER`、RLS-aware 的 `graph_entity_neighbors` RPC。
- 本 Phase 不新增資料表、不複製 relationship。Phase 1 已有 source／target 複合索引；Phase 2 已補 relationship type index。
- RPC 一次回傳 root、相鄰 Entity、Relationship 與 primary Evidence，避免 Vercel 到 Supabase 的 N+1 往返；只授權 `anon`、`authenticated`、`service_role` 執行。

## 4. API changes

- `GET /api/v1/graph/{entity_id}?limit=12&after={relationship_id}&relationship_type={type}`
- 一次只取得指定 Node 的 1-hop，最多 25 edges；UI 預設 12。
- 批次取得相鄰 Entity 與 primary evidence，避免逐 edge N+1。
- 回傳 `has_more`／`next_cursor`；不存在、未發布或 evidence 已撤回的關係不回傳。

## 5. UI changes

- Node 點擊展開下一 hop；root depth 0，最多 depth 3。
- Edge 點擊顯示關係類型、日期、金額／比例、來源、原始連結與取得日期。
- 依 depth 固定由左到右排列，同層垂直等距；保留 pan／zoom 與選取動畫。
- relationship type filter；變更時清空舊 lazy state 並由 root 重新查詢。
- 最大 60 nodes、每次 12 edges，避免 graph explosion。
- `/graph/{id}` 可分享；`/entity/{id}` 載入相同 Entity profile 並進入 Graph 2.0。

## 6. Risks

- 圖中 cycle：以 Entity ID 去重，edge ID 去重；既有較淺 depth 不被覆蓋。
- 高度數節點：分頁與 12-edge 預設，UI 顯示尚有更多而不宣稱完整。
- 同名：Node identity 僅使用 UUID；名稱只作顯示。
- Evidence 競態撤回：repository 僅批次讀 active/published evidence；缺 primary evidence 的 edge 丟棄。
- Filter 造成舊圖混雜：filter 變更重建 state。
- 舊公司功能：8 碼查詢仍使用原聚合 graph，不替換或刪除。
