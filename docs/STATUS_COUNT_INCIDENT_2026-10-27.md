# 資料庫統計偶發 500：根因與修復

日期：2026-10-27。範圍：本機、`tei-development` 與非正式分支 Preview。Production 未修改。

## 根因證據

`/api/status` 為每次冷啟動讀取多項精確統計。`entity_evidence` 的公開讀取政策要求其實體已發布、Evidence 已發布且有效。既有表沒有涵蓋這些發布條件及 ID 的索引，因此計數須先掃描兩個包含大量欄位的父資料表，再過濾證據連結。

- 匿名角色的既有 `statement_timeout` 為 **3 秒**，一般登入角色為 8 秒。
- PostgreSQL 日誌在檢查時段有 26 筆包含 `entity_evidence` 查詢的 `57014` 錯誤。此統計不是所有錯誤都只由本頁造成的證明。
- 實際公開 REST 查詢重現 **HTTP 500**，回應碼 `57014`，訊息為 `canceling statement due to statement timeout`；單次網路往返約 4,748ms。
- 為量測而在單一唯讀診斷交易內暫設 15 秒上限，匿名 `EXPLAIN ANALYZE count(*)` 完成時間為 **7,096ms**，讀取／命中 11,475 個共享頁。此暫時設定未改變角色或 API 的 3 秒上限。
- 同一資料表管理角色計數約 580ms；公開政策計數回 66,621，而全狀態連結有 66,625。這表示查詢有權限檢查成本，並非權限全被拒絕或資料消失。

效能排查參考：[Supabase RLS 效能文件](https://supabase.com/docs/guides/database/postgres/row-level-security-performance)。未關閉 RLS、未新增權限提升函式，也未使用 service-role API key 進行公開請求。

## 修復內容

Development 已套用 migration `20261027150311_public_evidence_count_covering_indexes.sql`：

1. `entities_published_type_id_idx`：只涵蓋已發布實體的類型與 ID。
2. `evidence_records_public_active_id_idx`：只涵蓋已發布且有效 Evidence 的 ID。
3. 更新這兩個表的 planner 統計資料。

這兩個索引讓原有 RLS 子查詢改走 **Index Only Scan**。沒有更改資料列、資料模型、公開條件、角色權限或角色逾時設定。

應用程式另合併同一程序內同時進來的統計更新請求，共用成功快取，並將單次查詢併發數由 8 降至 4。慢速失敗的一輪查詢不會再啟動無上限的逐項重試。計數只投影識別欄位；精確計數、未知值、單項失敗提示及安全錯誤記錄保留，不以估算或假數值代替。

## 修復後實查

- 在原有 **3 秒**限制內，匿名相同計數完成時間約 **1,055ms**，共享頁由 11,475 降至 1,421；兩個父表均使用新索引。
- 六次公開 REST 驗證（3 次依序、3 次同時）全部 HTTP 206、精確總數均為 **66,621**。網路往返分別為 1,741／532／706／452／726／429ms。HTTP 206 是這項分頁讀取的正常成功回應。
- 匿名 SQL 同時取得公開 Evidence **66,622**、公司 **462**，與修復前核對數一致。
- 本機瀏覽器實測為 LIVE，來源檔案 4、公司 462、人物 121、證據連結 66,621、Evidence 66,622、來源列 166,766 均可顯示；該視窗未見 console error／warn。
- 181 項 PGlite 檢查包含 migration 重跑、公開／草稿／撤回及 RLS 隔離；新增程序內併發回歸測試，確認兩個同時請求只做一組 11 項計數。
- 364 項 Python tests、既有前端回歸、lint 與 59 模組完整 build 通過；另驗證大範圍來源逾時不會觸發逐項無限制重試。
- Security advisors 的項目與修復前一致：2 項未設 policy 的封閉表提示、2 項 extension schema 警告、1 項密碼外洩防護設定警告；本次索引未新增權限暴露。既有項目仍需依上線計畫處理。

這是有限樣本驗證，沒有承諾所有未來負載下都不會出現來源故障；若資料量或同時使用者增長，仍須重新測量。Data Health 與司法 freshness 門檻分開處理。

## 回復與正式環境

必要時只移除這兩個新索引即可回復索引配置；不應刪除任何資料或更動 RLS。移除會使原來的慢計數風險回來。新增 migration 只套用 Development，正式環境多出一筆待評估的 migration，未自動升版。

本機 migration 由官方 CLI 建立，再依 Development migration ledger 的實際版本對齊檔名；未修改任何先前已套用的 migration。
