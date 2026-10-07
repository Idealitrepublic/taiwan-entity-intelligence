# P06 第二帳號實測 — 2026-10-08

狀態：**P0 OPEN；Product Consolidation 未完成**。

程式基準：`ff1508e639b89525ccaa115f69f4aa815c5030c0`。本次僅做 Development 實測、唯讀資料檢查與文件更新，未修改程式或 Production，未開始 P1/P2。

Preview：https://taiwan-entity-intelligence-nflw4wra4-coldlight871029-9944.vercel.app/

## 帳號與操作

使用者確認自行刪除 P01–P04，新增 `tei-pilot-p06@example.invalid`；這不是本次修復造成的帳號遺失。本次未重建舊帳號、重設密碼或還原其私人資料。刪除帳號對舊 Workspace 的影響尚未另行查證。

實際瀏覽器先顯示 P05 的五項真實收藏及一項追蹤。切換後實際介面顯示 P06；未提取或複製登入 token。建立 P06 專用 Workspace `16bd1cd0-af74-4638-89a6-1f80f28ffd01`，名稱 `P06 Owner Isolation 2026-10-08`，保留供後續重測。

## 本次驗收

| 項目 | 結果 | 實際證據／限制 |
|---|---|---|
| P06 登入狀態 | PASS | 真實 Preview 顯示 P06，而非 SQL 身分模擬；未驗證 token 到期與帳號復原。 |
| 私有列表隔離 | PASS | P06 初次列表無 Workspace、收藏及追蹤；沒有列出 P05 的四個專案、五項收藏或追蹤。 |
| 帳號切換表單清除 | FAIL | P06 無專案時，名稱／說明欄仍顯示 P05 的 `Final Phase A P05 2026-10-07` 與原說明；屬同頁殘留狀態，不能視為完全隔離。測試建立前已改為 P06 自己的內容。未證明後端允許跨帳號讀取。 |
| P06 新增／收藏／持久化 | PASS | 實際新增工作區、收藏大魯閣 Entity 與 Graph；兩項 owner/creator 均為 P06。重載同一頁仍有兩項。 |
| Entity／Graph／公開 Evidence | PASS（本案例） | 大魯閣公開頁有兩節點、一關係、MOL 處分及 MOEA 身分佐證，來源連結可見；不代表所有公司或來源 coverage 通過。 |
| P06 Watchlist | PASS（既有資料子集） | 真實新增一項追蹤、點擊檢查更新；重載仍在。零通知不代表通知產生／已讀轉換已驗證。 |
| P06 私有 PDF 下載 | PARTIAL／交付未通過 | 點擊下載後出現 PDF 備妥及可見 Save PDF 連結；再點儲存，但 Desktop／Downloads 未找到最近產生的 `tei-workspace-*.pdf`。未取得檔案，不能標記下載或版面 PASS，也不能僅憑此判定伺服器生成失敗。 |
| 直接讀取 P05 Workspace／Report 拒絕 | PARTIAL | 真實第二帳號列表隔離已驗證，但尚未完成帶 P06 身分的直接跨帳號請求；未使用擷取 token、管理員或角色模擬代替。 |
| 全流程、各關係範圍、Mobile／列印 | PARTIAL | 本次未完整重跑 Search→Path Finder→Evidence 收藏→Report 列印及所有尺寸；既有測試不能代替本次實測。 |

本次未修改程式，因此未重跑完整 build 或將先前 76 targeted／160 DB checks 說成新結果。瀏覽器錯誤查詢未取得可引用的新清單，亦不聲稱 runtime 零錯誤。

## Development 唯讀資料確認

29 public tables／29 RLS tables／25 migrations；Company 2、Politician 123（published 121）、GovernmentAgency 12、PoliticalParty 4、Penalty 1；Evidence 1,529（active published 911）、Entity Evidence links 910、Relationships 1,031（published 1,027）、source records 80,122、政治獻金關係 1、財產申報 1。

Workspace items 共 7，其中本次新增 2 項；無失效 Entity／Relationship／Evidence foreign key。此為當前狀態，非歷史無刪除證明。介面只顯示 908 個公開可見證據連結，與全表 910 不同；需保留「全表／公開可見」定義，不能把差異直接宣稱資料遺失。

## 建議下一步（依序，不自動實作）

1. **P0：清除帳號切換殘留**。登出、登入另一帳號及 401 時清空專案名稱／說明、收藏選取、下載連結與所有私有狀態；補兩帳號切換 regression test。
2. **P0：完成真實 PDF 交付**。追查手動 Save PDF 仍無檔案的瀏覽器下載行為，取得 P06 私有 PDF，再驗證內容、橫式、長 URL、中文及分頁；不要以「PDF ready」當交付成功。
3. **P0：補齊直接跨帳號權限驗收**。以真正 P06 登入嘗試 P05 Workspace／Report 的讀取與修改，確認拒絕且無資料洩漏；保留自己的正常操作作為對照。完整核心流程與三種關係範圍通過後才結案。
4. **其後才做 P1/P2**：高密度 Graph／手機操作，再集中修 Company Overview 重複資訊、原始欄位命名及 Report 冗長；目前仍未開始。
5. 測試帳號改用密碼管理器保存；需郵件復原時另行規劃可收信地址。不要把刪除重建帳號當作日常密碼復原，以免私人收藏失去歸屬。這是流程建議，不是已完成修改。

未新增資料來源、功能或假資料，未自動部署或提交新的程式 commit。

## 後續修復（使用者授權「開始修理」）

- 帳號切換根因：原 logout 只清空記憶體陣列，未清除 DOM 表單／私有列表；沒有 Workspace 時 `selectWorkspace` 也未清除名稱及說明。統一清除登入、登出、401 的私有狀態，移除私有下載 URL／預覽，增加 epoch 保護，避免舊帳號非同步回應覆寫新帳號畫面。
- PDF：原 Blob anchor 的成功點擊不等於磁碟交付，仍未證明瀏覽器靜默失敗的唯一原因。支援的瀏覽器改在使用者點擊當下開啟原生儲存對話框，驗證 PDF 後寫入／關閉檔案，只有寫入完成才顯示「PDF 已儲存」；取消、權限／磁碟錯誤明確處理。其他瀏覽器保留可見 Save PDF fallback，不宣稱落地成功。參考 [MDN 儲存對話框與使用者啟動限制](https://developer.mozilla.org/en-US/docs/Web/API/Window/showSaveFilePicker)。
- 登出仍沿用既有 Supabase API，未新增管理員能力或改 RLS；參考 [Supabase sign-out 說明](https://supabase.com/docs/reference/javascript/auth-signout)。
- 修復驗證：21 項 shipped JavaScript 回歸測試＋41 項 Workspace／Watchlist／Report／Path／Graph Python 測試通過；160 項離線 PostgreSQL checks、lint、50-module build 通過。新增測試包含清除所有私有表單、舊回應隔離、PDF picker 先於網路、取消不查詢、磁碟失敗不宣稱已儲存。
- 以上為程式及離線驗證，不是實際 P06 新 Preview 下載／跨帳號驗收；P0 仍 OPEN。未修改 schema、資料來源、Production 或 P1/P2。
