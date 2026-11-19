# T.E.I. 可重現模糊測試

這些是本機測試工具，不是產品資料源，也不會匯入資料庫。
參考 Lauren Tan 公開的 [pstack 驗證流程](https://github.com/cursor/plugins/blob/main/pstack/docs/guide/06-verify-and-ship.md)：定義可檢查結果、操作程式、保留失敗證據、修復後重跑。
公開資料沒有提供她內部完整 fuzzer；這裡是針對 T.E.I. 的生成式／變異式輸入與狀態式瀏覽器實作，不是 SpaceX 工具或認證，也不是 coverage-guided native binary fuzzing。

## 執行

使用專案 Python／Node 環境：

```sh
python tests/fuzz/campaign.py --seed 20261118 --cases 5000 --output /tmp/tei-fuzz.json
TEI_FUZZ_SEED=20261118 TEI_FUZZ_STEPS=150 node tests/fuzz/ui_campaign.cjs
node tests/fuzz/focus_race.test.cjs
python -m unittest tests.test_fuzz_regressions -v
```

也可使用 `npm run test:fuzz`／`npm run test:fuzz-ui`。瀏覽器需要既有 Playwright 與 Chrome；可由 `NODE_PATH`、`TEI_BROWSER_PATH` 指向安裝位置。

## 安全與隔離

- Python 禁止 `urllib.request.urlopen` 外連，公用 API 透過真實 WSGI dispatcher 驗證，但 repository／外部來源使用隔離替身；沒有執行 DB 寫入或 ingestion。
- 瀏覽器僅提供 `tei.local` 的合成回應，其他主機一律阻擋；沒有關閉 Vercel 保護、掃描 Production 或對官方 API 壓測。
- 輸出只含合成資料、種子、操作、錯誤、截圖與統計；不載入 `.env.local` 或真實帳密。
- `campaign.py --cases` 是每個 target 的次數，PDF 上限 100，避免無意義的重複建檔。不同案例可能等價；報告另外記錄每個 target 的 distinct input 數。
- 所有瀏覽器 session 在 finally 關閉；結果檔預設在 `/tmp`，不會寫入正式資料。

## 功能地圖與判定

| 範圍 | 生成／變異 | 判定依據 |
|---|---|---|
| WSGI／API | 中英文、長度、控制字元、URL 編碼、UUID、上限、方法與 JSON body | 客戶端輸入不可產生非預期 5xx；JSON／Content-Length／HEAD 合約正確；授權未成立不能執行私人寫入；受控來源未提供明細時 503 屬預期 |
| 標案正規化 | 有效公告混入錯誤型態、角色路徑、總筆數 | 有效公告不被別筆污染；異常角色不判定得標；較新異常修正不復活舊得標；原件不被修改 |
| 標案明細 | 異常欄位、長字串、不完整或非官方網址 | 回可用白名單或 unavailable，沒有未捕捉例外 |
| 指定中介路徑 | 3–13 個節點、隨機方向／迴圈與連線 | 與獨立 DFS oracle 比對 1／2／3 段；端點、節點不重複、每條線有證據 |
| HTML／PDF | 中英文、HTML 片段、畸形網址、長 URL、日期 | 無 script／事件屬性注入、不產生非 HTTP(S) 或含帳密的可點擊連結、有效橫式 PDF、來源標記仍存在、輸入不被修改 |
| UI 狀態 | 隨機展開、分頁、選取、快速切換、拖曳、縮放、置中、收合、範圍、focus 與 390–1440px | 不丟根節點、不重複 ID、座標有限、畫布存在、無 HTML 注入或 pageerror；隱藏側欄先依正常按鈕還原才操作 |

圖譜手動縮放／拖曳可能讓節點離開目前視野，這是可平移的畫布，不把每次不可見都誤判成資料遺失。完整標籤幾何與連線避讓另由既有八套 browser regression 檢查。

## 失敗與重播

`campaign.py` 以例外類型／訊息歸類，保留種子、索引與輸入，並以 delta-debug 縮小來源陣列／detail；不移除應受保護的有效標案。`repros.json` 保存真實產品失敗輸入，`test_fuzz_regressions.py` 每次完整測試都重播。瀏覽器失敗時留下操作序列及截圖，固定種子能重跑；動畫、排程仍可能影響時間，因此另將 focus 競態縮為確定性兩步測試。

## 限制

固定預算與合成來源不能證明沒有其他漏洞，也不能驗證官方資料真實性、真實使用者滿意度或全部 RLS 行為。RLS／migration 另跑隔離 PostgreSQL integration；Preview 只做正常少量 smoke 與真實 PDF 下載，不對雲端執行上述高量 fuzzing。

## 第二輪：不同操作與完成順序

2026-11-19 的新 campaign 不沿用上輪展開／拖曳的操作表。它以可手動釋放的回應 gate，強制「後查先回、先查後回」，並測試取消、跨公司／機關／路徑切換、標案明細失敗後篩選／重試、HTTP 503／HTML 200／壞 PDF／網路失敗後重試、下載期間改查另一公司，以及關閉尚未完成的預覽視窗。

```sh
TEI_FUZZ_SEED=91021 node tests/fuzz/async_workflows.test.cjs
TEI_FUZZ_SEED=91021 TEI_PYTHON=python3 node tests/fuzz/async_workflows_browser.cjs
```

另兩種子為 `43817`、`12077`。可用 `TEI_FUZZ_CASE=案例名稱` 只重播一個操作；`TEI_FUZZ_OUTPUT` 指定結果位置。每流程 18 秒隔離預算，逾時會記錄 FAIL，不把未完成算通過。此腳本會在本機呼叫專案 renderer 建立兩家公司不同內容的真實 PDF，用來逐 byte 核對下載，不載入憑證或真實 DB。

`beginInvestigation` 管理目前公司／實體／路徑的生命週期；名稱搜尋另有自己的世代編號。選擇新調查目標會淘汰舊畫面的回應；單純開關搜尋視窗仍讓目前公司的來源完成更新。兩者不能混為一個全部取消的狀態。
