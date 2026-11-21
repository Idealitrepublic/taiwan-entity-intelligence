# 自創範例驗收 — 2026-11-21

範圍：只更新本機與 Development Preview；本次不更動正式站、公開資料、資料模型或環境變數。

## 展示內容

- 3 家虛構公司、2 位虛構人物、1 個虛構機關、2 件虛構標案。
- 10 段關係、6 份範例證據；全部使用非統編的 `demo:`／`DEMO-` 編號。
- 一次顯示公司職務、共同法人董事、得標案件、共同採購機關四種情境。
- 範例甲、乙公司：1 個中介為共同法人董事；2 個中介為標案與採購機關。範例甲與法人丙公司可測直接關係。
- 全程顯示「自創／虛構」中英文提示；證據沒有偽造官方網址，無真實實體或 PDF 連結。

## 已執行本機驗收

| 項目 | 結果 | 驗證方式 |
| --- | --- | --- |
| 範例資料完整性與四種情境 | PASS | 檢查所有實體、關係、Evidence FK、角色與虛構標記 |
| 直接／1／2 個中介 | PASS | 自動檢查三家公司各方向與各範圍；Chrome 實際操作直接、一與兩個中介，及無路徑提示 |
| 8 個節點的右側資料 | PASS | Chrome 逐一啟動公司、人物、機關與標案節點並核對名稱 |
| 10 段關係的範例證據 | PASS | Chrome 逐一開啟，核對自創證據說明且無來源連結 |
| 收合與重新展開 | PASS | Chrome 收合至 1 節點，點甲公司重新展開至 5 節點 |
| 版面 | PASS | Chrome 實際驗證 1440／1280／1024／768／390／320px；無頁面橫向溢出，手機清單可選機關 |
| 範例資料隔離 | PASS | 本機請求紀錄在上述操作只有既有 `/api/status` 唯讀輪詢，沒有實體、公司、標案、路徑或報告 API 請求；未寫入資料庫 |
| 路由與退出／真實查詢 | PASS | Chrome 驗證 `/#demo`、清空、上一頁／下一頁；退出後查詢中華電信，取得 13 位董監事與 73 筆採購；載入範例後不混入真實資料 |
| 程式回歸 | PASS | 578 Python tests、338 隔離 PostgreSQL checks、JavaScript 回歸測試、2,000 回應順序模糊測試、lint、build 全部通過 |

既有兩套瀏覽器測試腳本已改為自行選擇真實測試公司，不依賴首頁範例；本輪透過 Chrome 實際互動驗收，未執行其 headless 腳本，因此不將其列為已執行 PASS。

## 已執行 Preview 獨立複驗

- PASS：全圖初次顯示 8 節點、10 段關係、6 份範例證據，右側含四種情境。
- PASS：1 個中介回傳 3 節點／2 段；2 個中介回傳 4 節點／3 段；點乙公司可繼續展開至 7 節點；返回全圖為 8 節點。
- PASS：選擇範例機關時，右側顯示機關資料及 2 件範例標案。
- PASS：切到標案後再載入範例會回到總覽；範例不產生真實實體／PDF 連結。
- PASS：退出範例後，以名稱選取真實公司「聯上開發／敦峰汽車」並查找，取得原有 3 節點／2 段有來源關係；沒有自創提示或範例混入。這段只是回歸驗收，首頁預設範例已不使用特定政治人物。
- PASS：最新部署再驗證 320／768／1440px，沒有頁面橫向溢出；Chrome 無 console/runtime error。
- PASS：本機拖曳甲公司後，4 段相鄰連線端點距圓心仍均為 26 單位（圓半徑）；放大、縮小、Fit 與手機清單可操作。
- PASS：最後功能 commit 再次執行 lint、build、578 Python tests、338 PostgreSQL checks 與全部 JavaScript tests。
- PASS：GitHub Actions [本次雲端驗證](https://github.com/Idealitrepublic/taiwan-entity-intelligence/actions/runs/44917508149) 完成 success；不將 hosted runner 環境中的跳過項目當作本機實跑結果。

## 限制

自創範例只展示上述四種情境，不提供真實查核、報告下載或外部官方紀錄。真實資料仍透過原有搜尋操作。裁判、裁罰、候選人、財產申報、遊說與 165 不因範例重新開放。

## 部署

- 已驗收 Preview：[直接開啟自創範例](https://taiwan-entity-intelligence-b1nsth26j-coldlight871029-9944.vercel.app/#demo)
- 功能 commit：`c2f9f6750a58a53c598341a5d797b8aa720595a1`。
- 部署：`dpl_E5asynk3GiL7GSW8iuRKjp4UHGae`，READY，Preview（target 為 null），分支 `feature/fictional-demo-20261121`。
- 畫面：本機 `/Users/lengguangchen/Documents/Codex/tei-fictional-demo-2026-11-21/preview-demo.jpg`。
- 本次沒有正式部署、環境變數修改或資料寫入。正式站仍為 `4badb87`，等待使用者另外授權同步。
