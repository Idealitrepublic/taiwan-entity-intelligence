# T.E.I. v2 資料來源架構

## 核心原則

- 不把全台大型政府原始資料全部灌進 PostgreSQL。
- 原始檔案留在 Supabase Storage，只有必要的索引與關係進 PostgreSQL。
- 能用官方 API 的資料優先走 API。
- API/來源查詢結果統一轉成 Evidence，並顯示來源、查詢時間與可核對連結。

## 目前狀態

| 資料 | 官方/來源 | v2 策略 | 狀態 |
|---|---|---|---|
| 公司基本資料 | 經濟部商工行政資料開放平台 | 即時 API | 已接入既有 live graph |
| 董監事 | 經濟部商工行政資料開放平台 | 即時 API | Supabase Edge Function `directors-api` ACTIVE |
| 勞動裁罰 | 勞動部 API Service | 即時 API | Supabase Edge Function `labor-penalties-api` ACTIVE |
| 165 涉詐網域 | 警政署 / data.gov.tw | 官方公開資料；以最新可取得資源為準 | Supabase Edge Function `anti-fraud-api` ACTIVE |
| PCC 決標/標案 | 政府電子採購網資料；目前無查到官方查詢 API | 先以開放民間 API 作查詢層；重要資料保留官方來源連結 | Supabase Edge Function `pcc-api` ACTIVE |
| 司法院裁判書 | 司法院資料開放平台 | 官方 API；需帳號密碼與 Token | 查詢層已有接口，正式使用需設定帳密 |

## PCC 注意事項

目前查到的 `pcc-api.openfun.app` 是由民間開放資料專案整理政府電子採購網資料，不是行政院公共工程委員會官方 API。因此產品 UI 必須標明來源層級，並提供回原始政府電子採購網的連結，不把民間 API 本身寫成「政府官方 API」。

## 司法院注意事項

司法院裁判書 API 需要向司法院資料開放平台申請的帳號/密碼取得 Token；官方文件也說明 API 服務時間為每日 00:00–06:00。未設定憑證時，系統只能顯示未設定狀態與官方查詢連結，不應假裝已查詢完整裁判資料。
