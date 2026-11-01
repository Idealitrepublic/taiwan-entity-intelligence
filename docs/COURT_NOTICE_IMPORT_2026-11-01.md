# 近五年裁判公告：首批 Development 匯入

範圍：2021-11-01 至 2026-11-01，以法院公告的確定日期篩選。
僅三組人工核對的歷史案件公告，**不是全臺近五年完整裁判資料庫**，也不是個人犯罪名冊。
Production、既有身分／Relationship／私人 Workspace 不修改。

## 官方來源與交叉核對

| 案號 | 公告確定日期 | 來源及核對 |
| --- | --- | --- |
| 最高法院110年度台上字第3984號 | 2022-06-29 | [法院公告](https://www.judicial.gov.tw/tw/cp-1888-667383-d90bf-1.html)及[官方 PDF](https://www.judicial.gov.tw/tw/dl-156754-0d14fca45f7b49fd92c103e41a49883d.html)案號、日期一致；公告明載程序駁回及全案確定，前審為108年度金上重訴字第5號。 |
| 最高法院110年度台上字第2443、2463號 | 2022-07-29 | [法院公告](https://www.judicial.gov.tw/tw/cp-1888-688053-1d44f-1.html)明載駁回上訴及全案確定，前審為108年度重矚上更一字第17、18號。兩案號保留同一公告群組，不拆造 JID。 |
| 最高法院113年度台上字第4710號 | 2024-12-11 | [法院公告](https://www.judicial.gov.tw/tw/cp-1888-1216430-79a4a-1.html)及[官方 PDF](https://www.judicial.gov.tw/tw/dl-224718-f90869f8383249288d8e956359958cc6.html)案號、日期一致；公告明載上訴駁回及全案確定，前審為112年度金上重訴字第56號。 |

這是同一官方發布機關的內容／格式一致性核對，**不是獨立來源互證**。
引用前審案號不代表已取得並逐項覆核前審全文。全案確定不等於所有當事人或罪名有罪。
不匯入個人定罪檔案、刑度、住址、聯絡資料、照片或別名；不建立人物／企業犯罪關聯檔案。
後續再審與非常上訴未全面核實，公開摘要明示限制，不宣稱當前法律狀態。

## 模型與保護

- 沿用既有 `Judgment`、`Evidence`、`entity_evidence`；不改 schema、API、RLS 或 UI。
- `SOURCE_SCOPED` 以官方公告編號識別，不以姓名合併。標題明示「裁判結果公告」。
- Evidence 保留官方 URL、案號、確定日期、前審案號、結果摘要、擷取時間、
  原始檔 SHA-256、核對日期及歷史範圍；不把公告冒充判決全文。
- 原件、acquisition manifest、加密備份與匯入 receipt 均在 repo 外私有目錄。
- 本批新增三組案件、三個 Evidence、三組來源連結；人物／公司及 Relationship 新增均為零。
- 未核實統編、案件角色與時間，不建立企業關係線；沒有線不表示沒有關係。

## 執行／重跑／復原

1. `.env.local` 必須被 Git 忽略、權限為 `0600`。既有 `TEI_DEV_DATABASE_URL`
   只接受 `tei-development` 的指定連線格式，公開讀取不用 service-role key。
2. 原件目錄的 `acquisition.json` 保留 URL、bytes、SHA-256、帶時區擷取時間。
3. `python scripts/ingest_court_notices_dev.py <私有原件目錄> --as-of 2026-11-01`
   預設只校驗，不連資料庫；任一來源不符或超出範圍，整批停止。
4. 寫入需加 `--apply-dev --backup-manifest <加密備份 manifest> --receipt <新的私有紀錄檔>`。
   備份限最近24小時且已驗證 Development，加密檔 checksum 必須一致。
5. receipt 先保存基線與本次新增 ID；單一 transaction 呼叫既有 ingestion RPC，
   檢查 Entity／Evidence 增量及 Relationship 不變，並於前後檢查容量低於480,000,000 bytes。
   這是保守停寫線，不是供應商硬額度；超線回滾，不刪歷史或升級付費。
6. 同 snapshot 重跑不新增；不同來源版本需人工檢查，不自動覆寫。
7. 若 receipt 停在 `prepared`，先核對 ID 實際存在／發布狀態；不能因連線中斷就假定未提交。
8. 需撤回時，核對 project、來源及 receipt，僅將 `new_evidence_ids` 設為
   `publication_status='withdrawn', status='retracted'`，將 `new_entity_ids`
   設為 `publication_status='withdrawn'`，在 Development transaction 內執行。
   不刪原件、共享資料或重跑前已存在的 ID；保留原始 Evidence 供稽核。

## 實際驗收

- age 加密備份與 archive／來源 bundle 驗證成功；本次未重做完整平台隔離還原。
- 匯入成功；重跑 Entity、Evidence 新增均為0。
- 匯入前：65,897 Entity、67,830 Evidence、1,395 Relationship。
- 匯入後：65,900 Entity、67,833 Evidence、1,395 Relationship；三組來源連結完整。
- DB 空間：475,278,483 → 475,286,675 bytes，低於保守停寫線。
- 實際撤下／RLS transaction 演練：匿名可見 Entity=0、Evidence=0；
  `ROLLBACK` 後三組均恢復公開，演練無持久異動。
- Development anon 權限下，三組均完成 Search → Entity → Evidence → Graph → Report
  API 真實讀取，共15項200回應；Graph 均無憑空推論的連結。
- 9項新增回歸、62項既有 targeted tests、433項完整 Python tests、181項 PostgreSQL
  integration checks及既有 JS regression、lint、build通過。
- Preview 驗收於部署完成後補記；本文件不宣告整體產品收斂或全臺覆蓋完成。

## 限制

全臺五年完整覆蓋、逐一當事人裁判結論、後續救濟最新狀態、企業案件身分連結均未完成。
不可把這三組試批當成完整名冊、犯罪傾向評分或關聯者有罪的依據。
