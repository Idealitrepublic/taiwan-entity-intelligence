# 上架候選版驗收紀錄 — 2026-11-05

## 結論與操作邊界

**尚未完成 Production Release。** 本輪為 `fix/launch-readiness` 候選修復，
基準 `e4c3f296a86cb76b8a7fb45f31e6072ef47db2d6`。只有實際觀測的項目標示 PASS；
Preview 部署結果另附驗收收據。未合併 main、未建立正式 release tag。

使用者另行允許恢復原正式 Supabase，供唯讀核對及加密備份；已恢復至
ACTIVE_HEALTHY。此授權不包含 migration、資料發布、環境變數變更、WAF 發布或正式部署。
未複製 Development Auth、Workspace、Watchlist 或任何測試帳號到 Production。

## 本輪修復

1. 私有流程：session 到期自動更新、同時請求共用一次更新、401 有限重試；登出、
   切換帳號及延後回應不能復活舊 session 或顯示前一帳號資料。PDF 使用相同認證管道。
2. 公開設定：僅接受 anon／publishable 類型憑證；拒絕 service-role、secret、使用者 JWT
   及不明 token。這是角色分類，簽章與 RLS 仍由 Supabase 驗證。
3. Rate limit：動態公司／Entity ID 不能分裂計數器規避限制；限制記憶體容量。
   此限制仍為單程序，不能替代分散式 WAF。
4. 公司報告：以已發布的精確統編對照串接政治關係、公司連結資產、Evidence 與 Graph；
   不再硬編碼為空。保留來源版本與取得時間，去除同一來源版本的重複表示；
   日期快照不冒稱即時資料，無法讀取的區塊不冒稱零筆。
5. 同步：Evidence、checkpoint、status、index 原子替換；單一寫入鎖避免同步／備份互撞。
   checkpoint 毀損時停止，不偷偷歸零重跑。
6. 維運：可重複執行 age 加密備份與全新本機 PostgreSQL 隔離還原；新增獨立、嚴格
   唯讀的 Production 備份命令，維持原 Development-only 防護。
7. CI：以目前 Python WSGI runtime 跑離線完整檢查。舊共享環境診斷改為手動確認，
   不再於 main／PR 自動呼叫舊正式 Edge Function。
8. 圖譜：展開已發布鄰接關係時放大目前分支，避免自動全圖縮小造成文字無法閱讀；
   保留手動縮小、全圖 Fit、拖曳、原路徑及 Evidence。手機清單顯示中英文類型。
9. Migration：僅將跨屆識別碼 migration 檔名改成 Development 已套用的版本號；
   SQL 位元組未改，未執行任何資料庫 migration。

## 實際驗證

| 項目 | 結果 | 方式與範圍 |
|---|---|---|
| Lint／語法 | PASS | Python Ruff、網頁 inline JavaScript 解析 |
| 自動測試 | PASS | 503 項 Python 測試及 JavaScript 回歸；含 session、PDF、rate-limit、來源寫入與報告整合 |
| SQL／RLS 回歸 | PASS | 181 項 PGlite 檢查，涵蓋 migration、重跑、約束、撤回與權限 |
| Build | PASS | 62 個 Python module、WSGI、部署資產、真實中文 PDF runtime |
| 司法同步 | PASS | 官方服務時段內執行；232/232 批完成；未估算未處理資料 |
| Data Health／OPS Health | PASS | 重新計算 High=0；已證明官方文件異常列 Medium |
| Development 加密備份 | PASS | pg_dump 直接串流 age，另備份相符 snapshot/checkpoint/Evidence；解密驗證 |
| 本機隔離還原 | PASS | 30 表、30 migrations、119 indexes、49 policies、204 constraints、34 functions、28 triggers 與所有 public 表筆數一致 |
| 還原後匿名權限 | PASS | 已發布 Entity 65,905、Relationship 1,391、Evidence 67,227 可讀；Workspace／收藏均 0 可見 |
| 本機公司搜尋／完整調查 | PASS | 中華電信、台積電、大魯閣統編；名稱、空結果及匿名私有路徑 |
| 本機路徑／Evidence | PASS | 聯上↔敦峰，1 中介吳思瑤；點人物延伸至 12 節點／13 線，保留來源與金額；直接／2 中介為真實空結果 |
| 真實 2 中介正例 | PARTIAL | 3 段路徑邏輯有回歸測試；目前已發布 DB 無可核對公司正例，不造關係填補 |
| 私有 Workspace／Report | PASS | 兩個既有獨立測試帳號；收藏報告有基本資料、關係、裁罰與來源；另一帳號報告 404 |
| 跨帳號寫入隔離 | PASS | Development 拋棄式 Workspace／Note；6 種跨帳號讀寫拒絕，owner CRUD 成功，探針已清除 |
| 瀏覽器 PDF 下載 | PASS | 實際下載 %PDF 檔；6 頁 Workspace 報告逐頁檢查，橫式、中英文、表格、URL 無溢出 |
| 全公司 PDF | PARTIAL | 中華 60 頁 PDF 結構／文字有效；未逐頁人工檢查全部 60 頁；另實測聯上報告含政治獻金 |
| Responsive | PASS | 1440／1280／1024／768／390px：圖譜容器存在、無頁面水平溢出、手機提供清單 |
| 真實外部受測者 | 未執行 | 不以內部測試代替議員／助理／記者的 Pilot |
| 新 Preview／雲端 CI | 待驗收 | 以推送候選 commit 後的實際結果為準 |
| Production 備份 | 阻塞 | 本機缺 `TEI_PROD_DATABASE_URL`，已請使用者只在本機安全設定；未重設密碼 |

所有「本機」驗證只指 Development 設定，不代表 Production 已具同等資料或 schema。

## 真實資料範圍

本次司法窗口 5,786 JList ID 全部處理：5,096 入庫、690 筆官方 JDoc 文件不可用，
pending=0、ingestion failure=0、upstream unavailable=11.93%。Evidence 檔完整性驗證通過。
這是該快照的處理率，不是全臺歷史裁判覆蓋率；上一窗口保存，未刪除歷史快照。

Development：463 公司、121 政治人物、31 政府官員、4 政黨、12 政府機關、
65,248 民間團體、2 標案、9 裁判、1 裁罰、14 遊說實體已發布；另有
230 筆政治獻金關係、63 筆財產申報、1,391 條已發布關係、67,227 筆有效已發布證據。
公司／人物舊表 `companies/people/evidence` 為零不代表 canonical Entity/Evidence 為零。
即時公司 API 與來源索引的董監事、裁罰、裁判、標案，不全部等於已發布 canonical Entity。

目前沒有資產申報的 company_entity_id 可精確連到已發布公司；報告整合以測試正例驗證，
不得用公司名稱猜配。勞動等部分來源的完整母體分母未知，仍標示 Unknown。

Development 約 475,442,323 bytes，距本案 480,000,000 bytes 匯入停損線僅約 4.56MB。
尚未新增大量資料或自行升級方案。來源原件、全量索引及本機備份不等於雲端均已發布。

Production 唯讀盤點：3 家已發布公司、34 人物、34 條關係、37 筆有效證據、
270,011 筆 source_records、0 筆資產、0 Auth users／Workspace／收藏，public 表均啟用 RLS。
與 Development 不同的筆數不是刪除證據；Production 仍是舊版資料狀態。
Production migration 為 19 筆，Development 為 30 筆。尚未套用相差的 11 筆。

## 上架阻塞與剩餘風險

### High／需解除後才能正式發布

1. Production 最新完整加密備份尚待本機正式連線設定與實際完成。
2. Production 的 11 筆 migration 差異、資料發布範圍與匿名讀取需經備份、dry-run、
   驗收及明確授權；不可直接複製 Development 整庫或測試帳號。
3. WAF 實際有 1 條 `/api/` 600 requests/60s/IP 的 rate rule，但 Action 為 **Log**。
   不是 0 規則，也不是正式阻擋。Hobby 僅 1 條 rate-limit rule；應以既有規則設計
   Preview 驗證與正式發布方案，不自行增加付費資源或宣稱防護完成。
4. 新 Preview 最終驗收及使用者核准尚未完成。只有核准後才可進 main／正式部署。

### Medium／Low 與產品限制

- 690 筆官方文件不可用、裁判歷史索引不完整；所有未知覆蓋率須如實告知。
- 公司有精確統編仍不代表裁罰或司法同名候選已完成身分確認。
- Supabase Free 會因低使用量自動暫停；正式可用性與容量方案尚待成本決策，未自動升級。
- 本機還原驗證應用 schema／RLS／資料；未涵蓋 Supabase 平台服務、原 ACL／ownership、
  Storage 檔案、Edge Functions、平台 Auth 設定或異地備份保管。
- 單程序限流不是多實例全域限流；目前 WAF Log 只能觀察。
- 取樣與功能回歸不能替代真實受測者、長時間負載測試或全資料母體完整性聲明。

## 下一個正式發布關卡

先完成本機正式連線設定與加密備份，再交付已驗證 Preview 與待發布 migration／資料／WAF
明細供使用者驗收。只有新的明確正式發布授權後，才執行 Production dry-run／套用、
main release/tag、Production 部署及可回滾 smoke。此文件不構成上述操作授權。
