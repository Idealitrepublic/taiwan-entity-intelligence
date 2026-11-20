# 發布稽核五項修正

範圍：基準 af42751；僅本機與 Development／Preview。Production 程式、設定與資料未修改。此文件不宣告 Product Consolidation COMPLETE 或正式發布通過。

| 項目 | 狀態 | 實際處理與證據 |
|---|---|---|
| 密集圖譜字級 | 本機 PASS；Preview 待驗 | 展開後將主標籤提高至至少約 12px；視窗 resize、放大畫布及返回欄位改為恢復分支鏡頭，不再自動縮小整圖。顯式「置中」仍可看全圖；其餘節點可拖曳畫布查看。1440／1280／1024／768px 字級、節點固定、連線避字及 Evidence 回歸通過。 |
| PDF 同頁重複表頭 | 本機 PASS；Preview 待驗 | 一般表格只在列間分頁；超過整頁的單列只於新頁開始切分。真實聯上開發報告 15 頁，所有頁面無同頁重複章節表頭；超長列 900 次內容回歸完整。保留官方單筆連結、中英文及橫式。 |
| 團體名稱缺字 | PASS（隔離，非補造名稱） | 45 筆 ASCII 問號名稱：33 筆官方 CSV 原件同樣缺字；4 筆官方非 CSV 待覆核；8 筆官方來源目前無法取回。45 個既有實體與 45 個證據轉 draft，ID、原名、provenance、FK 全數保留，0 關係／0 收藏受影響。匯入流程加入缺字待核 gate，正常名稱照常發布。詳見逐筆 JSON。 |
| 真實兩個中介正例 | PARTIAL | anon/RLS 全部 1,389 段關係以雙向三段、不重複節點／邊 SQL 查核，真實公司三段路徑總數為 0。合成正例與獨立 oracle 通過，真實一個中介及三段無結果回應通過；尚無真實正例，不造邊、不改為「最多兩個中介」，不標此項 PASS。另核對中華電信 73、聯上 8 筆可取得標案，未找到可補驗的立法院採購正例。 |
| 當前範圍健康／復原／防護 | PASS（有明確界線） | 新增唯讀公開範圍健康檢查，保留歷史全來源報告及司法 checkpoint。公開結構 High=0，不等於全臺覆蓋或 freshness 已認證。實際 age 加密備份及全新 socket-only 本機 PostgreSQL 還原通過：30 表、39 migrations、120 indexes、73 RLS policies、205 constraints、38 functions、28 triggers、row counts／anon 可讀範圍一致。修復漏還原 tei_source_checks schema 的問題。透過既有 Vercel 登入唯讀核對已啟用 API 規則：600 次／60 秒／IP，超過門檻 Deny 403；排除 status／workspace-config。未改規則、未做正式站壓測。 |

## 測試

- 乾淨隔離副本：564 Python tests、328 PostgreSQL checks、套件 JavaScript tests、lint、build 通過。
- 瀏覽器回歸涵蓋 10／17／46+ 混合節點、66 層／79 節點連續展開、原節點固定、分支線與 Evidence、各桌面寬度、手機清單、右欄選取、真實 PDF 輸出流程。
- 新增／更新字級、鏡頭 resize、放大畫布與立即點選競態、長表格分頁、缺字匯入及健康範圍的回歸。
- 舊「展開時 zoom 絕對不變」斷言改為「不可縮小且字級至少約 12px」，避免原測試反過來強迫保留看不清楚的比例；幾何無重疊與連線避字門檻保留。
- 真實報告與截圖暫存於 /tmp/tei-five-fixes；憑證、age 私鑰及未加密備份不寫入 repo。

## 可重跑與復原

公開站健康（只讀 Development；先於安全子程序載入既有設定）：

```sh
.venv/bin/python scripts/public_release_health.py --local-env
```

這個流程讀 anon/RLS 可見資料；取得時間與官方事件時間分開、不推估母體。原司法健康檢查仍屬內部歷史同步範圍，不以公開站撤下功能冒充已修復官方來源。

名稱覆核：docs/CIVIL_NAME_QUALITY_REVIEW_2026-11-20.json 保留每個原實體與證據 ID、快照雜湊及此次官方取回結果。取得官方完整字形後才更正並覆核發布；不因 rollback 自動把缺字名稱重新上架。不重建人物、不改收藏或關係。

備份為 repo 外私有目錄中的 age 加密檔，隔離還原使用獨立 PostgreSQL 暫存 cluster；未連接既有本機 DB。演練含 tei_private 與 tei_source_checks，原 Supabase 平台 Auth／Storage 服務、原 ownership／ACL 與實際 Vercel 部署回滾不在此次本機演練的保證範圍。

## 剩餘發布條件

1. 真實兩個中介正例仍缺。應取得能用官方身分／單筆證據串接的資料後再驗收；無路徑是資料範圍結果，不是應以猜測補線的程式錯誤。
2. 45 筆缺字仍待官方名稱覆核；其中 12 筆未能取得可核對原件。另有 2 筆全形問號名稱須判別是否為合法標點，不自動視為缺字改名。
3. 來源 freshness、全國母體覆蓋及長時間負載尚未全面認證；公開結構 High=0 僅代表此次明列的完整性檢查通過。
4. 未修改或批准正式部署。正式發布與正式 smoke 仍需另外授權。
