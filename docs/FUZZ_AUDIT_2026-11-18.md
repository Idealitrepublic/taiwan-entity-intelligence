# 2026-11-18 模糊測試與修復驗收

測試於 2026-11-18 開始，2026-11-19 完成最後 Preview 驗收（臺灣時間）。

基準：`7a91cfb`；分支 `test/reproducible-fuzz-audit`。僅本機／隔離瀏覽器與 Preview，Production 不修改。沒有載入真實憑證到模糊測試，沒有寫入資料庫，也沒有向官方 API 或公開網站發送高量測試。

## 方法來源與實際採用

已閱讀 Lauren Tan 公開的 [pstack](https://github.com/cursor/plugins/tree/main/pstack) 與其[驗證流程](https://github.com/cursor/plugins/blob/main/pstack/docs/guide/06-verify-and-ship.md)。本輪採用可重跑的完成條件、實際操作、失敗證據、修復後重播的原則。她內部完整 fuzzing 工具沒有公開，不能宣稱複製 SpaceX 內部系統或取得任何認證；也沒有導入自動合併或 Production 發布。

實作為固定種子的生成／變異式 Python campaign 加上狀態式 Playwright campaign。重播方式與判定見 [測試說明](../tests/fuzz/README.md)，機器可讀結果見 [本輪數據](FUZZ_AUDIT_2026-11-18.json)。

## 找到並修復的問題

| 編號／嚴重程度 | 失敗證據 | 根因與修復 | 驗收 |
|---|---|---|---|
| F-01／High | seed 20261118、procurement 第 7 案；1 筆角色路徑為整數的異常公告，導致另一筆有效標案也消失 | 角色解析假設所有來源欄位都是正確 dict/list，例外落到整批 fallback。加入欄位型態檢查，異常角色保持 unresolved，保留其他有效公告；輸出異常筆數與 UI 提醒。錯誤總筆數不再清空有效公告。仍先選較新公告，再判斷角色，不能因新修正異常而復活舊得標。 | 最小案例、較新異常修正、metadata 異常回歸及三種子通過 |
| F-02／Medium | PDF 第 2 案 `https://[`；另外 HTML 100 案探測也重現同類錯誤 | URL parser 例外使整份報告中止。HTML／PDF 保留來源文字、略過無效連結；標案明細亦保留有效欄位，只停用異常官方連結；只產生無帳密的 HTTP(S) 連結。 | PDF／HTML、非 HTTP URL、含帳密 URL、來源標記與不可變性檢查通過 |
| F-03／Medium | UI seed 20261118 第 12–13 步：focus→立刻選根節點；資訊框被清除 | focus 的 requestAnimationFrame 延後重設選取，覆蓋較新的點選。把該次重設與 focus 動作同步完成；不再排程全域選取清除。 | 兩步確定性失敗→通過；同種子 150 步及另外兩種子通過 |

初輪 API 曾出現由測試阻擋外連引起的 502；調整隔離來源回應後無產品重現，故沒有列成產品漏洞。另一個 UI 探測在放大畫布隱藏側欄時嘗試選側欄，屬無效測試操作，已改為先按「返回完整畫面」。沒有以修改產品來迎合這些測試假警報。

## 執行結果

| 範圍 | 3 個種子的執行次數 | 結果 |
|---|---:|---|
| WSGI／API 輸入、方法、JSON／HEAD | 15,000 | PASS |
| 標案正規化與異常來源隔離 | 15,000 | PASS |
| 精確版本標案明細 | 15,000 | PASS |
| 1／2／3 段路徑，獨立 DFS 比較 | 15,000 個圖／45,000 次深度比較 | PASS |
| PDF 檔案、來源與頁面 | 300 | PASS |
| HTML escaping／連結 | 15,000 | PASS |
| 瀏覽器隨機操作序列 | 450 步序列，416 步實際操作 | PASS |

總計 75,300 次生成案例；這是執行次數，不是 75,300 種獨特資料。每 target、每種子的 distinct input 數已保留在 JSON（例如來源明細的 5,000 次有 132 種不同輸入）。固定種子：`20261118`、`20261119`、`73013`。修復後未留下可重現的失敗類別；不表示所有輸入或時間排程均已窮盡。

- 原工作樹完整測試：551 Python tests（含使用者原有備份變更）、250 隔離 PostgreSQL checks、JavaScript、lint、build 通過。已另外從提交本身建立乾淨隔離目錄：550 Python tests、250 DB checks、全部 JavaScript、lint、build 通過；原有備份修改未混入本次提交。
- 原有八套瀏覽器 regression 全部通過：公司來源、路徑、中華電信、多層持續展開、分類年度、密集圖譜、右側與 responsive、跨類型共用操作。
- UI 序列包含 450 次狀態檢查、416 步實際操作，34 次因當時不適用而明確記錄未操作，不算按鈕通過。UI 隨機測試涵蓋展開／分頁、選取、快速切換、拖曳、縮放、置中、收合、範圍、focus、390／768／1024／1280／1440px；沒有 pageerror、重複節點 ID、非有限座標或 HTML 注入。所有非隔離主機外連均攔截，未向真實服務 fuzz。
- 每個實際產品失敗都保留最小 regression，已加入一般完整測試；重跑也保留種子、生成索引、輸入與瀏覽器操作序列。

## Preview 驗收

修復提交：`5bd5fdcec7a09281ee7169b18cefe87e9484098a`（前一修復 `59dd6ca`）。
部署：`dpl_B46MWA8sERsGuqXibBs7qpRHTTsD`，READY、target=null，非 Production。
實測 Preview：<https://taiwan-entity-intelligence-q0k6sfmhd-coldlight871029-9944.vercel.app/>。

以下為正常少量的真實查詢，並未對 Preview 執行高量 fuzz：

| 項目 | 結果 | 證據 |
|---|---|---|
| 聯上開發標案 | PASS | API 200、8 筆公告、本次 malformed=0 |
| 中華電信公司／人員 | PASS | API 200、13 位董監事 |
| 統計 | PASS | API 200、公司 472、人物與政治人物 152、Evidence 67,134，快取有核對日期 |
| 真實圖譜 focus→選取 | PASS | 社會福利及衛生環境委員會；點放大圖譜後立刻選節點，經過兩個動畫 frame 資訊框仍存在；返回完整畫面與右側選取正常 |
| Responsive | PASS | 1440／1280／1024／768／390px 畫布仍存在且可操作 |
| 實際按鈕下載 | PASS | 聯上開發，report API 200，`tei-company-22659295.pdf`，128,717 bytes、有效 `%PDF-`、13 頁橫式；案號 0630800011、預算、決標總額、資料取得日期與民國年份保留；無 165 章節 |
| 瀏覽器／API 錯誤 | PASS（本次觀察） | 真實流程無 pageerror、無捕獲的 API 5xx |
| Runtime logs | PASS（觀察窗口） | 此 Preview 查詢最近 30 分鐘 error／fatal 無紀錄；不推論窗口外永無錯誤 |

本輪驗收完成；未推進 Production。這份紀錄後續文件提交與本次已驗證修復程式相同，不重新宣稱已測到不同的功能版本。

## 限制

本輪是有界的生成式／狀態式測試，不是覆蓋率導向的原生二進位 fuzzing、滲透測試認證、官方資料逐筆真實性覆核或真人 Pilot。RLS 由隔離 PostgreSQL checks 驗證，沒有向雲端私人表新增帳號或測試資料。外部服務停機、完整資料覆蓋、特定裝置及所有時間排程仍可能存在本輪未涵蓋情況。
