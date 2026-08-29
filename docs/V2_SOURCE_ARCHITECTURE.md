# T.E.I. v2 來源架構

## 核心原則

- 公司基本資料：即時查詢經濟部商工行政資料開放平台 API
- 董監事／人物：即時查詢經濟部商工行政資料開放平台 API
- 165 反詐：原始開放資料放 Supabase Storage；查詢只建立精簡索引，不把完整原始資料灌入 PostgreSQL
- 政府裁罰：原始開放資料放 Supabase Storage；查詢只建立精簡索引
- PCC：優先官方 API／官方查詢介面，不再使用全站資源爬蟲作為主要方案
- 裁判書：官方開放資料／API；搜尋結果只保存必要 metadata 與來源連結

## PostgreSQL 使用原則

PostgreSQL 只保存：
- entity identity / normalized keys
- 查詢索引
- 關係圖需要的 edge
- Evidence metadata
- 來源狀態與更新時間

禁止：
- 每筆資料都保存完整 raw JSON
- 把可由官方 API 即時查得的全量資料鏡像進 DB
- 為單一原始紀錄重複建立大量冗餘 Evidence

## 董監事 API

Supabase Edge Function：`directors-api`

官方資料來源：經濟部商工行政資料開放平台「公司登記董監事資料」API。

呼叫方式：
`GET /functions/v1/directors-api?uniform_number=XXXXXXXX&top=50&skip=0`

`top` 最大 1000；`skip` 用於分頁。

前端與後端查詢公司時，優先使用 live directors API；不得依賴全台董監事本地快照。
