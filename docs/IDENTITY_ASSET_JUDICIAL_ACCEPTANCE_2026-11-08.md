# 同名身分／資產公司／司法缺件驗收（2026-11-08）

**整項 PARTIAL，未補齊全部資料，不構成正式發布驗收。** 本輪以 `0f8c272` 為基準，
僅本機及 Development；沒有合併、刪除、發布或更新任何雲端資料，Production 未連線、未修改。

## 實際範圍與判定

| 檢查 | 結果 | 實際證據／限制 |
|---|---|---|
| 已發布身分／關係完整性 | PASS（限定已發布資料） | 65,905 Entity、1,391 Relationship、67,227 Evidence；斷裂公開端點／主 Evidence、identifier 衝突、資產 FK 異常均 0 |
| 同名觀察覆核 | PASS（抽樣，不代表全臺核身完成） | 唯讀 1,500,899 筆董監事觀察；抽查陳建宏、陳怡君、陳俊宏、林怡君、陳淑芬，每組保留公司統編、來源列、職位與 snapshot hash；不以同名合併 |
| 空缺職位 | PASS（防護） | 原件 4,140 筆「暫缺／缺額／待補／出缺／空缺／無」保持來源觀察；候選引擎拒絕把它們核准為人物；未刪原件 |
| 洪申翰跨角色 | PARTIAL（身分脈絡有官方佐證；未合併） | 兩個公開 Entity 分別為立法院精確識別、行政院首長來源觀察；不是兩個公司／人物資料列遺失。下列官方簡歷與辭職文書可交叉核對；保留不同來源、歷史與原 FK，未杜撰跨角色 canonical ID |
| 資產原件與 API | PASS（現有 63 筆） | 廉政專刊 319 期 PDF hash 與既有 Evidence 相同；本機 API 三頁共 63 筆、不重複、來源與取得時間完整；Entity、Evidence、Graph 均 200 |
| 資產公司正式連結 | PARTIAL | 12 筆有名稱，6 股票、6 保險；精確 company_entity_id 仍 0。未在來源列發現統編／證券代碼，禁止從名稱猜補 |
| 現有司法快照完整性 | PASS（僅指定快照） | 232/232 批、5,786 JID 全部交代：5,096 成功、690 upstream unavailable、0 pending；690 份錯誤皆有重複指紋、官方 JList metadata、HTTP200、時間與 provenance |
| 官方案例重新核對 | PASS（3/3 已知案例） | 官方公開裁判網頁重新讀取成功；整體公司司法索引 8,507 JID、不重複。抽樣命中率不是全臺歷史 recall |
| 690 筆目前是否可取回 | PARTIAL／尚待線上 | 本輪台灣白天不在 JList/JDoc API 00:00–06:00 時段，沒有違規呼叫或把舊錯誤當成最新調查。舊快照、Evidence 與 checkpoint hash 均保留 |
| 缺件重查與續跑 | PASS（離線防護與模擬） | 凍結名單、逐筆進度、重複官方錯誤與 transient 分流；重查完成前段持續 unavailable 時後段仍會被處理；換 snapshot 拒絕沿用 journal；關閉時段與 check-only 不呼叫 API |

目前 private resolution_candidates 表為 0，不能宣稱真實配對 precision/recall 100%。
公開同名群組只有洪申翰跨角色兩個 Entity；原始董監事來源中的同名觀察不等於 canonical Person。

## 已修正

1. 官方 opaque identifier 不再套姓名的大小寫轉換，防止 `AbC`、`abc` 被當成同一 ID。
2. 自我列／同 Entity 的重複候選不再製造假歧義；不同 Entity 共用識別碼仍拒絕。
3. 不同姓名、倒置／缺少可比任期、沒有候選 Evidence，不可僅靠公司／職位脈絡進入 HIGH；空缺不當人物。
4. 資產公司 lookup 遇到全形／半形正規化碰撞，保留所有候選並拒絕歧義，不採最後一筆覆蓋。
5. 缺件清關要求完整官方 receipt；缺指紋、一次性錯誤、429、timeout 等不得冒充 upstream unavailable。
6. 舊 `--judicial-recheck-unavailable` 預設只取排序前 25 筆。新增凍結缺件名單的續跑器，避免前段持續異常永久餓死後段。

候選引擎版本 v2 不覆寫 v1、既有實體／關係／收藏 ID；沒有 migration 或 RLS 放寬。

## 資產公司逐類缺口

- 聯嘉投控：監察院原件寫股票簡稱、數量及價額，沒有發行人代碼／統編。
  證交所公告可交叉建立候選範圍（3717、完整公司名），但不得將外部查到的代碼
  冒稱原件直接提供或已完成精確持有配對。
- Berkshire Hathaway Inc、Figma Inc、NVIDIA Corp、Palantir Technologies、Tesla Inc：
  需可對應申報證券的識別碼、股別／發行人及適用時間；不能把美國公司硬接臺灣同名公司或子公司。
- 南山人壽 1、國泰人壽 2、富邦人壽 3 筆：原件是保單。即使日後核實承保公司，
  也不能生成 ASSET_OWNERSHIP／BUSINESS_INVESTMENT；目前保留原始名稱與空值。
- 沒有複製測試 fixture、以 UI 補值或發佈推測關係。上述資料仍是缺口，未宣告完成。

## 重現驗收與續跑

本機唯讀核對（只接受已驗證 Development connection，值不寫入命令）：

```sh
.venv/bin/python scripts/audit_identity_asset_judicial_dev.py --output reports/identity_asset_judicial_2026-11-08.json
.venv/bin/python scripts/recheck_judicial_unavailable.py --check-only
```

回傳 integrity PASS 與 task_completion PARTIAL 是刻意區分；不能拿前者宣告資料補齊。
下一個 00:00–06:00 時段，在 repo 根目錄只將已忽略、0600 的 .env.local 司法憑證載入子程序：

```sh
.venv/bin/python - <<'PYTHON'
import os, subprocess
from pathlib import Path
from scripts.run_dev import read_local_env
local = read_local_env(Path('.env.local'))
env = os.environ.copy()
for name in ('JUDICIAL_USER', 'JUDICIAL_PASSWORD'):
    if local.get(name):
        env[name] = local[name]
raise SystemExit(subprocess.run([
    '.venv/bin/python', 'scripts/recheck_judicial_unavailable.py'
], env=env).returncode)
PYTHON
```

續跑器只選 frozen journal 未完成的缺件，不重跑成功 JDoc。暫時失敗保留 pending，
下一次沿原 journal 重試；時段結束停止。journal 在 ignored data/，不是新 JList checkpoint。
本輪 sweep 完成不表示官方文件已修復；須重算成功／pending／upstream counts，再刷新 Data Health。
不要單純改 retrieved_at 消除 stale。若需另開新輪，先保留已完成 journal 作履歷，不刪舊 snapshot。

## 驗收證據檔與限制

- reports/identity_asset_judicial_2026-11-08.json：Development 唯讀完整性、逐資產 locator、snapshot hashes。
- reports/identity_source_sample_2026-11-08.json：官方來源 snapshot／列號／同名觀察抽樣。
- reports/identity_local_api_2026-11-08.json：實際本機六次 Entity／資產三頁／Evidence／Graph 回應。
- reports/judicial_benchmark_2026-11-08.json：官方三案例重新核對，僅代表樣本。
- 測試、完整 DB 回歸、build、Preview 收據完成後附於下方；未驗證事項不得標成 PASS。
- 本輪不代表全站新一輪真人 Pilot、Production smoke、全國資料補全或 690 份新鮮官方文件取得。

官方交叉核對來源：
- 勞動部部長簡歷：https://www.mol.gov.tw/1607/1608/80563/80572/?cprint=pt
- 立法院辭職議案文書：https://ppg.ly.gov.tw/ppg/download/agenda1/02/pdf/11/02/12/LCEWA01_110212_00111.pdf
- 證交所聯嘉投控上市公告：https://wwwc.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d697fc438f01989dc23d80029a.pdf

## 最終本機驗收收據

- 2026-11-08：518 項 Python tests、全部既有 JavaScript suites、181 項 PGlite DB checks 通過。
- 完整 lint、額外新增 operator scripts lint、web 語法檢查、完整 Python/WSGI/PDF build 通過。
- 本機 Development API：Entity、3 頁資產（25+25+13）、Evidence、Graph 共 6 個 200；
  63 個資產 ID 不重複、每筆內嵌 Evidence 有 source_url 與 retrieved_at。
  測試曾以超出契約上限的 limit=50 呼叫，回傳預期 400；改用既有 25 筆分頁契約後完成逐頁核對，沒有為驗收放寬 API。
- 司法原件、JList、checkpoint 在本輪前後 SHA-256 相同；沒有線上司法同步或缺件復原成功宣稱。
- Development 全部 63 筆仍保留、0 錯配／0 新發布公司關係；Production 未修改。
- Preview 使用既有 fix/launch-readiness 非 main 分支，分支測試入口：
  https://taiwan-entity-intelligence-git-fix-764717-coldlight871029-9944.vercel.app/
  雲端 ready 狀態及部署 commit 需以對應 Vercel 收據核對，不代表本文件列出的缺件已補齊。
