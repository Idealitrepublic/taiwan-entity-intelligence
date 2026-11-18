# 2026-11-18 六項全面檢查修復驗收

基準：`ca15c8f`。範圍：本機與 Development Preview；不修改 Production、資料、migration、RLS 或環境設定。未刪除任何歷史來源資料。

## 修復內容與本機驗收

| 使用者需求 | 結果 | 證據與界線 |
|---|---|---|
| 統計逾時與「—」 | PASS | 舊版每個精確計數允許 8 秒、11 個查詢以 4 工作者分波執行，再有失敗重試；前端 25 秒截止，故冷啟動可能超過前端期限。新版每查詢 3 秒，已核對筆數立即呈現、背景單次更新、失敗保留原值與逐項核對時間，不把失敗當 0。不使用 PostgreSQL planner 估算（實測偏差過大，已淘汰）。本機連續請求 0.007／0.001 秒，這是快取回應速度，並非掃描資料庫的速度。|
| 放大圖譜畫布 | PASS | 桌面放大模式保底高度由 1000 改為 1120px，保留 toolbar／來源說明所需空間。原本失敗的 SVG >700px 門檻原樣通過，未放寬測試。|
| 移除 165 | PASS | 公開公司回應、圖譜、查詢欄、報告不再查詢／呈現 165；原網域檢查入口回 410。保留公司官網與其來源連結。歷史快照存檔未刪除。|
| PDF 日期、術語與標案欄位 | PASS | 雙語 PDF 使用資料取得日期、符合、紀錄角色等標籤；日期保留西元／民國及原日期精度、時區。補齊案號（保留前導 0）、預算、總決標金額、招標／決標方式、決標日期與來源定位。僅有來源提供才顯示。為避免外部來源阻塞下載，精確公告明細先補前 8 筆，其餘公告仍保留且標明明細範圍。完整 provenance 在報告 JSON 保留，不在 PDF 反覆傾倒原始明細陣列。|
| 真正按鈕下載 | PASS（本機＋Preview） | 找到公開下載按鈕先開啟檔案選擇器而等待、未發出 API 請求的問題；公開報告改走瀏覽器下載，保留可點擊的儲存重試連結。真實 Development 聯上開發按鈕→API 200→有效 `.pdf` 檔，無 pageerror。Preview 已另以真實按鈕完成下載，不以本機代替。|
| 其他實體共用圖譜操作 | PASS（本機＋Preview） | 公司、一般人物、政治人物、官員、機關、團體、政黨、標案共用展開／收合／縮放／Evidence／右側實體選取；保留各類原有概況，防止舊選取非同步覆蓋及收合後失效 panel。非台灣公司識別不送經濟部統編查詢。來源範圍的人員觀察不冒充正式人物實體，也不自動合併同名。|

## 精確統計快照

`src/public_database_counts.json` 僅包含公開可見精確聚合，嚴格核對 Development URL，禁止套用到其他資料庫。
以 `anon` 角色、現行 RLS、唯讀 `COUNT(*)` 核對：2026-11-18 22:41（臺灣時間）。
公司 472、人物與政治人物 152、實體 65,890、實體證據連結 66,904、證據 67,134、關係 1,389。
舊表 companies／people／evidence 為 0；公開可讀來源檔案／索引為 0，受公開範圍 RLS 限制，不等於管理端原始來源不存在。

回應清楚區分 `connected`（當次實際連線）與 `snapshot_available`；快照不宣稱現在已成功連線。
刷新結果逐項保存 `metric_checked_at` 與 `stale_metrics`；顯示的總核對時間使用最舊的有效時間，滑鼠停在統計列可看該項時間。
Vercel 執行個體可能休眠／更換，背景刷新屬 best-effort；跨冷啟動以有日期的已核對快照兜底。若資料或公開政策變更，須重新核對並更新對應快照，不能把舊快照稱即時數據。

## 可重跑驗收

- `npm run lint`、`npm test`、`npm run build`：使用實際 Python／Node runtime。
- 8 套隔離瀏覽器 regression（原 7 套＋跨實體共用操作）；測試資料只存在於隔離瀏覽器，未寫入資料庫。
- 真實下載：啟動安全 Development 本機伺服器，執行 `node tests/report_download_browser.cjs`。
- Preview 下載使用同一測試，`TEI_AUDIT_BASE_URL` 指向非 Production Preview。若部署有保護，使用部署限定、短期授權入口，不解除保護；入口不寫入文件或 repo。
- PDF 以 pypdf 核對檔頭、橫式頁面、中英文、案號、新欄位、雙年份與 165 移除；Poppler 抽看標案／來源／圖譜頁。

## Preview 最終結果

修復 commit：`9c2df312aae0af0d81064445a34d01134c4b8883`；分支 `fix/full-audit-remediation`。
已驗證 Preview：<https://taiwan-entity-intelligence-cud7edrac-coldlight871029-9944.vercel.app/>。
部署 `dpl_WLpyUTfDJrdHSt8b8vmSvtebWVzU`，READY、target=null（非 Production）。

- 從提交本身建立乾淨隔離目錄重新驗證：545 Python tests、250 PostgreSQL integration checks、全部 JavaScript 測試、lint、build 通過。
- 原工作樹包含使用者既有備份變更，另跑 546 tests 通過；這些備份變更沒有混入本次 commit。以乾淨 commit 的 545 項作本次正式計數。
- 原有 7 套瀏覽器測試全部原樣通過，加上第 8 套跨 8 種實體測試通過。
- Preview 真實下載測試無 mock／route interception：聯上開發 `22659295`，點「下載完整調查 PDF」，report API 200，下載 `tei-company-22659295.pdf`、128,841 bytes、13 頁 A4 橫式、有效 `%PDF-` 檔頭。無 pageerror；已核對案號 0630800011、預算 0 原因、總決標金額、招標／決標方式、西元／民國年份、新資料取得日期標籤、來源與圖譜；165 與舊「來源角色」未出現。
- Poppler 實際檢視標案頁、關係圖頁、來源頁：中英文、長標題及 URL 可讀，頁邊沒有截字或水平溢出。長來源可跨列／跨頁；不是單頁摘要。
- Preview 真實跨類型：李彥秀 12 個已載入節點、社會福利及衛生環境委員會 9 個、高雄市北高雄扶輪社與陳駿季各 1 個。後兩者沒有已載入關係，維持真實空狀態，不增造連線。
- Preview 實際選節點→右側切換→回根實體成功，1440／1280／1024／768／390px 圖譜仍可操作，無 pageerror、無本輪捕獲的 API 5xx。
- 中華電信真實 API：200、13 位董監事、保留 cht.com.tw 官網；回應無 165 字樣或 anti_fraud 節點。舊 domain-check 410。
- 統計 API 200，6 項 canonical 聚合完整；當大表精確刷新逾時，仍保留已核對筆數，清楚標成 cached，沒有以估算或假 0 替代。
- 此 Preview 最近 30 分鐘 error／fatal runtime logs 無紀錄；這是觀察窗口內結果，不宣稱未來永不出錯。

本輪六項驗收完成。Production 未部署、未修改資料／RLS／migration／環境變數。仍須注意：統計快照非即時；外部來源可能暫時無法取得、報告明細先查前 8 筆；一般 Person 公開索引目前為零，不等於即時公司董監事來源不存在。這些限制不得寫成全國資料已完整。
