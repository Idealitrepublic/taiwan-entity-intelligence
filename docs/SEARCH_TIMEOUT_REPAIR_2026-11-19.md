# 搜尋逾時修復驗收

狀態：**R2-04 CLOSED（本次驗證範圍）**。
修復 commit：`8bc3ed91886d617cb3d2b7c5fcdc026eb122cbad`，分支 `fix/search-timeout`。
只對 `tei-development`（`canqjiokrtcxkwblhmml`）套用下列 migration，未部署 Production、未修改其環境變數，也沒有更新 Entity／Relationship／Evidence 資料列。

## 根因與修復

1. 舊搜尋的相關 RLS EXISTS 對 131,828 筆搜尋詞逐筆回查 Entity；exact／prefix／contains 三個重疊分支重複掃描。匿名「聯上開發」曾實測 5,269.498 ms、1,060,473 次 shared buffer hits，超過 Data API 的三秒時限。改為目前角色可見的已發布 Entity ID 集合（hashed subplan），一次掃描計算分數，保留所有 restrictive policies。
2. 統編 limit=1 的內部公司核對也走完整名稱／關係計畫，另重現 4,135.021 ms。現在直接讀唯一公開統編索引；不存在才走原排名搜尋。沒有以空結果取代故障，也不改同名匹配原則。
3. 原來的 LATERAL 即使執行時不需公司關係脈絡，仍將複雜 Relationship／Evidence RLS 放進整個搜尋計畫。現在先完成排名，最多取 20 筆，再以獨立 invoker statement 按需要讀取原本的最新關係標籤。具有公開統編的公司結果不會計畫或讀取關係表；其他型別仍保留原脈絡。
4. 首頁每個冷實例／55 秒週期還會啟動 11 組 exact counts、四個 worker。相同時段記錄 source_records／entity_evidence／evidence_records 的統計逾時，這個負載會與搜尋爭用資源。已將 exact 重算移出公共請求；首頁只回傳有日期的驗證統計與一個兩秒、limit=1 的連線 probe，單一程序內共用且有 55 秒 cooldown。

函式仍為 SECURITY INVOKER，參數、NFKC、literal wildcard escaping、identifier／exact／prefix／contains 排序、UUID tie break 與 20 筆上限不變。沒有任意切掉排名候選、移除 RLS、加入 SECURITY DEFINER、擴大公開寫入權限、使用 service-role 讀取或升級付費。函式局部保留 jit=off，沒有更動全域 JIT、角色 timeout 或 plan_cache_mode；診斷時的時間差不能獨立歸因於 JIT。

三筆新增 migration 的本機檔名與 Development history 一致：

- `20261119032245_public_search_timeout_repair.sql`
- `20261119033610_public_search_identifier_fast_path.sql`
- `20261119035549_public_search_lazy_context.sql`

設計參考：[Supabase RLS 效能與 join 建議](https://supabase.com/docs/guides/database/postgres/row-level-security#minimize-joins)、[PostgreSQL CTE materialization](https://www.postgresql.org/docs/current/queries-with.html#QUERIES-WITH-CTE-MATERIALIZATION)。

## 沒有略過的中間失敗

| 時點（UTC） | 實際結果與後續 |
|---|---|
| 03:29:38 | 第一筆 SQL 修復後，typed limit=1 統編仍有資料庫 500；新增統編 fast path。 |
| 03:38:56 | 兩筆 SQL 修復後，首頁冷啟動的兩筆名稱搜尋仍有資料庫 500，並有統計重算逾時；移出公共統計負載。 |
| 03:47:44 | 統計隔離後仍有兩筆名稱搜尋在冷計畫階段被取消；分離按需關係脈絡。 |
| 03:55:50–03:58:00 | lazy-context 修復後重測連續公司搜尋、人物及再次公司查詢 PASS，搜尋 RPC 500 為 0。 |

這些中間版本的 UI 曾因既有 retry 而回 200，因此沒有僅憑瀏覽器 PASS 就提前結案。第一個計時工具也曾把整批查詢放進同一個三秒 DO 而被取消；已改為每個查詢獨立 statement，沒有調高實際單次預算。完整逐次量測保留於同名 JSON。

## 最終驗收

- 從乾淨的最終 commit 匯出執行：**555 Python tests、328 隔離 PostgreSQL checks、全部 JavaScript、lint、build 全數通過**。未將使用者原有的備份修改混入 commit。
- 舊／新 RPC 在匿名及 authenticated 下，22 組參數的完整有序回應一致。涵蓋同名人物、別名、排序、literal `%`／`_`／反斜線、全形統編、型別與 limit=1／20、空結果、草稿殘留投影及撤下資料。
- 重複套用 migration 通過；公開寫入、私有 identifier 仍被拒絕。隔離 DB 撤銷名稱投影 SELECT 時，單筆 exact 統編仍成功；撤銷 Relationship SELECT 時，有統編的公司名稱搜尋仍成功，人物脈絡查詢則確實被拒。這些測試證明實際走分離路徑，不只檢查 SQL 字串。
- 五項首頁負載回歸通過：20 次冷／重複請求不觸發計數、20 次併行請求只用一個 probe、probe 成功保留統計日期、probe 失敗保留數值並限速／去除機密錯誤、其他 DB 不沿用筆數或捏造零。原計數重試測試仍驗證 off-request 計數器。
- 最終 Development 的 16 次匿名／authenticated 查詢，各自維持三秒時限，全數完成。這輪第一筆名稱查詢 1,558.189 ms，其餘名稱／型別案例 101.474–783.493 ms；已知單筆統編 0.898–5.793 ms。這是資料庫 execution time，不是完整網頁延遲。

## Preview

[已驗證 Preview](https://taiwan-entity-intelligence-kw6g8ycom-coldlight871029-9944.vercel.app/)，`dpl_sEkE7f8LQJX21C7n8LM3MgTe6UvZ`，READY。

實際以正常使用量驗證冷啟動、反序連續名稱搜尋、20 次公司／人物／廣泛詞／全半形統編／空結果／typed limit=1 搜尋，**全部 HTTP 200**。選取聯上開發、載入兩公司範例、快速切換 1／2 中介範圍、右側選公司與實際 PDF 下載均 PASS。切換測試不等於驗收所有兩中介資料的覆蓋率。

- 該次 pageerror=0、API 5xx=0；Vercel error/fatal 與 status_count_unavailable 均無紀錄。
- 04:01:40–04:04:06 UTC 的 Supabase PostgREST 日誌，搜尋 RPC 500／503 為 0；沒有以重試恢復掩蓋本次驗收錯誤。
- 統計保留 472 家公司，標示 cached 與原驗證時間 `2026-11-18T14:41:25.082197+00:00`；probe 成功不會把取得日期改成現在。
- `tei-company-22659295.pdf` 實際下載，128,837 bytes、13 頁，parser 可讀且公司名稱／統編一致；本輪未另宣稱所有頁面已人工排版驗收。
- 最終 20 次搜尋的端到端時間為 407–11,260 ms，包含網路、Vercel 與既有經濟部 fallback。單筆 typed 統編四次為 407–465 ms。資料庫變快不代表所有官方即時補查已變快。

## 復原與限制

原精確計數器 `_refresh_database_status` 保留為明確 off-request 驗收用途。資料或公開政策改變後，應用既有公開角色計數流程重新驗證、更新 `src/public_database_counts.json` 並驗證 Preview；不可只改時間假裝更新。沒有快照的其他 DB 顯示未知，不繼承 Development 的數字。

若需回復，只對 Development 新增回復 migration：恢復舊的 published_search_terms EXISTS policy，以及 `20260915173315_phase_2_global_entity_search.sql` 中 **search_entities function definition** 與原授權。不要整份重跑 Phase 2（其前段會重建搜尋投影），不要刪 migration history、reset DB 或覆寫資料。回復舊查詢或重新開啟首頁計數 fanout 會帶回原風險。Production 發布另依既有核准流程，本次未執行。

固定資料量與正常使用量驗證不等於容量壓力測試或永久零故障保證。首輪曾有 company-related API 因官方公司登記查詢失敗回 503，後續恢復；這個 API 不呼叫 search_entities。官方來源可用性、補查延遲，以及統計須維護更新的限制仍保留。Development advisor 的既有 public extensions／密碼外洩保護／內部無公開 policy 提示，本輪未變更。
