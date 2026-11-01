# 裁判資料擴充與法人案件角色

本輪沿用 Development，Production 不修改。案件公告由3組增至9組，
另新增1家以官方統編確認的公司與1條經人工核對的公司→案件關係。
這不是臺灣近五年完整裁判庫，也不是新聞人物／犯罪關聯名冊。

## 新增六組官方案件公告

| 案號 | 公告確定日期 | 官方來源 |
| --- | --- | --- |
| 最高法院112年度台上字第4688號 | 2023-11-16 | [法院公告](https://www.judicial.gov.tw/tw/cp-1888-984048-4263c-1.html) |
| 最高法院112年度台上字第3396號 | 2023-09-07 | [法院公告](https://www.judicial.gov.tw/tw/cp-1888-937067-42991-1.html) |
| 最高法院113年度台上字第3919號 | 2024-11-27 | [法院公告](https://www.judicial.gov.tw/tw/cp-1888-1207403-050dd-1.html) |
| 最高法院112年度台上字第3852號 | 2023-09-21 | [法院公告](https://www.judicial.gov.tw/tw/cp-1888-947052-54003-1.html) |
| 最高法院112年度台上字第1046號 | 2023-05-02 | [法院公告](https://www.judicial.gov.tw/tw/cp-1888-857388-8f4f8-1.html) |
| 最高法院113年度台上字第3802號 | 2024-10-04 | [法院公告](https://www.judicial.gov.tw/tw/cp-1888-1175483-9f64d-1.html) |

逐筆核對上訴審案號、日期、確定記載與前審案號。1046號保留「部分撤銷自為改判、
其他上訴駁回」的區別，沒有把所有案件摘要套成單純駁回。
只匯出案件metadata，不擷取私人當事人姓名、匿名姓名、健康資訊、家庭關係、地址或刑度。
同一官方來源的內容核對不等於獨立來源互證，亦未全面確認後續救濟最新狀態。
原三組公告與Evidence ID完全不變，沒有重新發布或覆寫舊證據。

## 法人角色核對

- 公司：頂新製油實業股份有限公司，統編59066479。
- 登記依據：實際成功下載[經濟部統編查詢回應](https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6?%24format=json&%24filter=Business_Accounting_NO+eq+59066479&%24skip=0&%24top=1)，
  確認唯一回應、完整法人名稱、統編、核准設立與設立時間。
- 案件角色依據：[最高法院110年度台上字第2443、2463號公告](https://www.judicial.gov.tw/tw/cp-1888-688053-1d44f-1.html)
  列明完整法人名稱及其上訴當事人角色，並非僅被旁及的名稱。
- 法院公告本身沒有列統編。本輪為「完整法人名稱＋官方統編回應＋設立時間早於案件」
  的人工對照，關係信心為 **HIGH**，不把法院公告說成含有統編或EXACT身分裁判。
- 公司本身的識別為官方統編 **EXACT**；這與關係／案件結論的信心不同。
- 唯一新線為 `Company → RELATED_TO_JUDGMENT → Judgment`，
  `source_role` 為「法院公告當事法人 / Corporate party in court announcement」。
  起訖日期同為2022-07-29，表示該公告事件，不推論持續中的犯罪或其他關係。
- 角色Evidence保留法院與登記兩份原件雜湊、官方URL、統編、核對方法、案件日期及信心。
  Registry Evidence作為context補強，不拿登記資料證明案件有罪。
- 新線由另外的法人核對adapter產生；原先三組公告adapter仍只輸出案件與來源。
  原公告摘要的「不建立人物或企業連結」是該來源投影的範圍，並非聲稱經另一證據核對後不能關聯案件。

## 新聞連接原則與尚未實作範圍

「同篇新聞出現」不等於有實質關係，「有關係、不等於違法」註記不能代替身分與角色證據。
本輪沒有建立任意新聞人名抽取、同名合併、黑幫／慣犯標籤或一般個人的犯罪關聯檔案。
本輪資料來自法院新聞稿與官方登記，**沒有聲稱已完成大量媒體新聞串接**。
新聞共同提及若將來採用，必須與可證實的交易、職務、訴訟角色分開，不能生成未核實的正式Relationship。
可核實的公司／組織與公開人物之公共職務相關資料，仍需各自來源、時間及具體角色核對。

圖譜連線的Evidence面板補上「來源角色 / Source role」，缺值顯示未提供；
角色文字經既有安全轉義，不執行來源內的HTML。保留既有展開、拖曳、縮放與Evidence功能。
沒有新增Relationship type、API、schema、RLS或大型產品功能。

## 驗收發現的預設公司流程漏接與修復

第一版Preview中，公司名稱搜尋會進入既有即時調查流程。該流程只讀舊
`evidence`表及本機JDoc名稱索引，沒有讀canonical Company→Judgment角色；
因此同一筆案件在已發布圖譜可見，預設公司頁卻顯示司法0筆。資料未遺失。

修復在既有company資料組裝層：依公開統編identifier與EXACT公司識別，
最多讀12條已發布、EXACT/HIGH且角色非空、primary Evidence active的相關裁判線。
不依公司名稱新增連結，不讀service-role，不覆蓋舊司法索引。
這些角色資料進入預設公司Evidence、司法清單、Graph及報告資料；
司法名稱命中數與已核對法人角色數分開顯示，公告沒有JID時只顯示來源紀錄，禁止造JID。
來源不可用或更多頁未載入則標partial／未知，保留既有可讀索引，不當成確認零筆。

## 可重跑與復原

沿用 `scripts/ingest_court_notices_dev.py`，預設只校驗。
加 `--with-reviewed-corporate-link` 才加入唯一人工核對的法人關係；不接受任意姓名或公司的搜尋參數。
`--apply-dev` 仍需最近24小時的已驗證age加密備份及repo外新receipt。
前後檢查容量、實際增量與來源版本；不同版本停止，保留原始Evidence。
receipt新增 `new_relationship_ids`，區分這輪新增與重跑前既有資料。
撤下該角色primary Evidence會撤下相應關係；再依receipt撤下本輪新Entity及Evidence，
不得撤下既有2443／2463公告或其他共享公司資料。中斷若receipt為prepared，先查實際提交狀態。

## 實際驗證

- 新增：7 Entity（6案件＋1公司）、8 Evidence、1 Relationship；人物新增0。
- 重跑：Entity、Evidence、Relationship新增均為0。
- DB合計：65,900 → 65,907 Entity；67,833 → 67,841 Evidence；1,395 → 1,396 Relationship。
- 已發布公司463家；本來源公告9組；人工核對法人案件線1條。
- DB容量475,335,827 bytes，低於480,000,000保守停寫線，未清除資料或升級方案。
- 18項adapter／guard、8項預設公司投影回歸及14項關係說明UI測試通過；完整450項Python、181項DB checks、
  既有JS regression、lint、完整build通過。
- Development匿名讀取真測：公司統編搜尋、Entity兩筆Evidence、Relationship角色、
  Graph一條線及Report API均200。
- 本機真實預設 `/api/company/59066479` 回應200（本次6.83秒）：司法1筆、
  已核對法人角色1筆、Evidence1筆、預設Graph包含該角色；未產生假JID。
- 真實transaction演練：撤下角色primary Evidence後匿名可見關係為0；ROLLBACK後恢復1，
  演練未留下持久異動。未重新執行完整平台隔離還原。
- 第一版Preview為 `a3d306c`，發現上述預設流程缺口後未宣告整體PASS；
  `9b2b74b`修復版Preview READY，實際公司名稱搜尋→預設公司頁→司法清單→
  圖譜2022年→07月→案件節點→來源角色已驗證，預設司法及證據均顯示1筆。
- 司法清單顯示來源紀錄與案件角色，沒有假JID。驗收另發現原JDoc日期通用說明
  不適用公告，已補回歸測試並分開說明JDoc日期與法院公告事件日。
- 1440／1024／768／390px檢查新增案件角色區塊，頁面均無水平overflow，角色資訊可見；
  驗證後已還原視窗設定。這不是全站Auth／Pilot／所有手機流程的驗收聲明。

## 仍未完成

五年完整coverage分母仍未知；不能以9組樣本推估全臺覆蓋率。
一般新聞、其他公司／組織案件角色及後續救濟狀態尚待逐項來源核實。
本輪不宣告全臺資料補全或整個產品驗收完成，Production仍未修改。
