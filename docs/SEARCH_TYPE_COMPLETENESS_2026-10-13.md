# Global Search 類型完成度（Development，2026-10-13）

本表區分「選單可選／API 有實作」、「Development 已發布的 canonical Entity」和「其他即時或來源層資料」。已發布筆數不是全臺資料總量或覆蓋率；未查到 canonical Entity 不代表官方沒有該類紀錄。以下只讀 `tei-development`，沒有修改資料或 Production。

| 選單類型 | 搜尋實作 | 已發布 Entity | 實際完成度與缺口 |
| --- | --- | ---: | --- |
| 公司 / Company | 有 | 2 | 可用統編查經濟部即時登記；即時結果不等於已解析的 canonical Entity，不能直接用於關係路徑。全臺 Entity 索引未完成。 |
| 人物 / Person | 有 | 0 | 尚無公開可搜尋的 canonical Person。董監事可在即時公司調查中呈現，並非此類 Entity 索引完成。 |
| 政治人物 / Politician | 有 | 121 | 已發布立委主資料、任期與關係；另有 2 筆 draft 不會公開。不能把這 121 筆視為所有政治人物。 |
| 政府官員 / GovernmentOfficial | 有 | 0 | 尚未發布此類 Entity。 |
| 政府機關 / GovernmentAgency | 有 | 12 | 已發布的機關可搜尋，但不是完整機關名錄。 |
| 政黨 / PoliticalParty | 有 | 4 | 已發布部分政黨；不是完整政黨名錄。 |
| 標案 / Contract | 有 | 0 | 公司調查可查第一頁政府決標公告；尚未發布為可搜尋 Contract Entity，且來源第一頁不代表完整標案覆蓋。 |
| 裁判 / Judgment | 有 | 0 | 公司調查有獨立司法索引；尚未發布為可搜尋 Judgment Entity。歷史司法索引與官方 JDoc 異常仍有已知限制。 |
| 裁罰 / Penalty | 有 | 1 | 已發布 1 筆 canonical Penalty；另有 80,122 筆 labor source records，但不能等同已解析、可搜尋的 Penalty Entity。 |
| 政治獻金 / PoliticalContribution | 有 | 0 | Development 有 1 條已發布獻金關係及 Evidence，尚未發布此類獨立 Entity；資料量不足以支持全面覆蓋聲稱。 |
| 財產申報 / AssetDeclaration | 有 | 0 | Development 有 1 筆 `asset_declarations`，尚未發布此類獨立 Entity；資料量不足以支持全面覆蓋聲稱。 |
| 立法提案 / LegislativeBill | 有 | 0 | 此類 canonical Entity 未發布；提案／共同提案頁面空狀態不應視為完整資料。 |
| 遊說紀錄 / LobbyingRecord | 有 | 0 | 尚無公開可搜尋的 canonical Entity。 |

## 驗證基礎與限制

- 唯讀查詢 `public.entities` 依 `entity_type, publication_status` 分組；關係使用 `public.relationships.status='published'`。已發布關係包括 `COMMITTEE_MEMBER` 783、`LEGISLATOR_OF` 121、`MEMBER_OF` 121、`POLITICAL_CONTRIBUTION_TO` 1、`RELATED_TO_PENALTY` 1；不代表每個搜尋類型都有對應 Entity。
- `public.source_records` 的 labor 資料集為 80,122 筆；`public.asset_declarations` 為 1 筆；`public.evidence_records` 為 1,529 筆，`public.entity_evidence` 為 910 筆。來源筆數、Evidence 筆數、已發布實體筆數不應互換。
- 本盤點不依賴測試 fixture 或 schema 存在性推算 coverage。即時經濟部、政府採購與司法查詢的當次可用性需個別驗證；本表不將來源層命中算作 Global Search 已發布 Entity。
- 未經官方總量與抽樣召回率驗證，不給百分比完成度。建議在新增選單類型之前，優先完成現有來源的 canonical 發布、Evidence 串接與實際覆蓋率驗證。
