# 公司來源連結核驗（Development，2026-10-22）

本紀錄只描述 `tei-development` 與版本化公開來源快照。沒有讀寫 Production，也沒有以公司名稱或裁判書提及文字建立新的正式 Relationship。筆數是此刻 Development 的狀態，不是全台資料涵蓋率。

## 1. 統編 ↔ 官網網域

- 人工核對的公司頁／文件：8 對；另從[證交所上市公司基本資料](https://data.gov.tw/dataset/18419)、[公開發行公司基本資料](https://data.gov.tw/dataset/28567)、[櫃買中心上櫃公司基本資料](https://data.gov.tw/dataset/25036)取得 531 對官方申報的統編、完整公司名稱與網站。版本化快照共 539 對。
- 來源申報網址若沒有 HTTPS，僅針對 Development 已發布公司探測同一網域的 HTTPS；16 對通過，跳轉別家公司網域或無法正常取得的網址排除。探測只證明當時可連線，不證明網域所有權或網站安全。
- Development 的 462 家已發布公司中，24 家同時符合統編及完整公司名稱，含 18 家官方申報網址、6 家人工核對資料；其餘 438 家仍未取得符合此門檻的官網連結。539 是對照表總量，**不是** Development 已連結公司數。
- 官網是 165 公開網域資料的比對輸入；165 未命中不代表安全，申報網址也不構成公司涉詐證據。若經濟部欄位與來源網域衝突，程式拒絕自動比對。

## 2. 勞動裁罰

- `source_records` 有 80,122 筆勞動來源列；只有 1 筆有可擷取的 8 位統編，並已連到已發布公司。其餘名稱命中僅為候選，不得批次轉為正式公司裁罰關係。
- 抽樣：大魯閣實業股份有限公司（04690983）來源列 `mol:64b2b93c4c7a53c5ee9d3511412b1c04bfbd8aa4397272e76f224f2e396f602b`，處分字號「府勞動字第1130101133號」、日期 2024-07-17。Development 內有公司 → `RELATED_TO_PENALTY` → 裁罰、2 筆 `entity_evidence` 連結與已發布 Evidence；來源檔 ID、原始公司標籤、統編、法條及[勞動部資料集入口](https://data.gov.tw/dataset/109896)均保留。
- 此資料集入口不是單筆永久網址。API 現在另外提供可複查的處分字號、日期、主管機關、來源檔及身分狀態；前端仍須顯示候選警示，不得把資料集入口稱為單筆原文。

## 3. 司法裁判

- 本機 JList/JDoc 公司名稱索引有 4,231 筆名稱命中；Development 目前 **0** 筆已發布 Judgment。名稱命中只表示文字出現，缺官方統編／當事人身分驗證，不能建立正式公司—案件關係。
- 抽查中華電信名稱命中的 JID `TCDM,114,金簡上,255,20260915,1`：[司法院原文](https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=TCDM%2C114%2C%E9%87%91%E7%B0%A1%E4%B8%8A%2C255%2C20260915%2C1)提及的是手機門號，不能據此認定中華電信為案件當事人。API／Graph 保留 JID、來源、日期與 `name_mention_unverified`、`party_role_status=unverified`。
- 未來若要正式發布司法 Relationship，須從官方原文辨識當事人角色，並取得可驗證的公司識別訊號；單靠名稱或摘要不足。

## 4. 政府採購

- Development 有 2 筆已發布 Contract / `CONTRACT_WITH`，各有官方 PCC 公告 URL、案號、得標廠商統編、角色、金額及主 Evidence。唯讀檢查器 `scripts/audit_official_procurement_dev.py` 會重新比對官方頁面的**同一投標廠商區塊**，不接受頁面其他位置的名稱文字。
- 本次首次開啟兩筆官方公告時可看到統編、案名與金額；連續自動複查時 PCC 轉為撲克牌驗證碼頁，因此自動驗收為 `official_captcha_manual_review_required`，**不是**官方內容不符，也不得據此新增發布。需要人工在 PCC 頁完成驗證碼後，再核對兩筆得標角色。
- OpenFun 結構化公告只作候選；未經獨立官方原文核對的紀錄維持 draft/source candidate，不宣稱官方已驗證。

## 可重跑與剩餘限制

在已確認連線目標為 `tei-development` 的本機環境，可執行 `scripts/build_official_company_websites.py --development-focus` 重新產生官網快照，`scripts/audit_graph_coverage_dev.py` 取得涵蓋量，`scripts/audit_official_procurement_dev.py` 唯讀複查採購。官方申報網站、裁罰來源及司法原文仍會變動；快照與查核時間需一併呈現。

剩餘核心缺口是 438 家 Development 公司缺高可信官網、80,121 筆勞動來源缺可核對統編、司法 4,231 筆名稱命中缺當事人身分證明，以及 PCC 驗證碼阻擋自動逐筆複查。這些不能用名稱相同或推測補齊。
