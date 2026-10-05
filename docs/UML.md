# UML 系統架構規畫

本文件是「縣市一週預報 MVP」的目標設計。目前已實作真實／合成解析器、SQLite、更新流程、JSON 日誌與 Streamlit 介面；圖中類別名稱仍表示責任邊界，實際函式以 src/weather 為準。圖以 Mermaid 表達 UML 類別、循序及狀態模型；名稱是規畫中的責任邊界，方法簽章可在實作時調整。既有需求見 [開發計畫](PLAN.md)，欄位與時間規則見 [架構設計](ARCHITECTURE.md)。

閱讀順序：先看使用情境與模組關係，再看資料模型，最後看更新與失敗處理。

## 1. 角色與系統邊界

| 角色／外部系統 | 主要互動 | 對應需求 |
| --- | --- | --- |
| 一般使用者 | 選縣市／日期、查看地圖／趨勢／表格、要求更新 | FR-04～FR-08 |
| 學習者 | 明確切換至示範模式，以固定範例操作 | FR-09 |
| 維護者 | 設定 Key、部署、檢查更新結果與安全錯誤代碼 | NFR-01、NFR-04、NFR-07 |
| CWA API | 回傳未來預報 JSON | FR-01、FR-02 |
| 底圖服務 | 為瀏覽器提供地圖圖磚；失效時表格仍可用 | FR-07、FR-10 |

MVP 的 Python 模組、Streamlit 與 SQLite 位於同一服務執行個體；瀏覽器是使用者入口。CWA 與底圖供應者在系統之外。這些模組不是微服務，不需要為每個模組新增 HTTP API。API Key 留在伺服器端；定位、通知與即時觀測圖層不屬本次 P0 架構。

## 2. 模組關係：設計類別圖

`boundary` 表示介面邊界、`control` 表示流程協調，其他標籤標示模組責任。虛線箭頭代表「依賴／呼叫」，不是資料的流向。為保持概略，本圖省略方法參數與基礎設施細節。

```mermaid
classDiagram
    direction TB
    class WeatherUI {
        <<boundary>>
        +render_dashboard()
        +select_location_and_date()
        +request_refresh()
    }
    class ForecastService {
        <<control>>
        +get_dashboard()
        +refresh_if_due()
        +refresh_on_request()
    }
    class CwaClient {
        <<adapter>>
        +fetch_forecast()
    }
    class DemoFixture {
        <<adapter>>
        +load_forecast()
    }
    class ForecastParser {
        <<service>>
        +normalize_and_validate()
    }
    class ForecastRepository {
        <<repository>>
        +read_snapshot()
        +publish_snapshot()
        +record_refresh_result()
    }
    class GeoCatalog {
        <<service>>
        +lookup_location()
    }
    class Settings {
        <<configuration>>
        mode
        refresh_interval
        stale_threshold
        cwa_api_key
    }
    class CwaApi {
        <<external>>
    }
    class SQLite {
        <<database>>
    }
    WeatherUI ..> ForecastService : 操作
    ForecastService ..> CwaClient : live 模式
    ForecastService ..> DemoFixture : demo 模式
    ForecastService ..> ForecastParser : 解析驗證
    ForecastService ..> ForecastRepository : 快照讀寫
    ForecastService ..> GeoCatalog : 縣市代表點
    ForecastService ..> Settings : 模式與更新政策
    CwaClient ..> Settings : 讀取密鑰與逾時設定
    CwaClient ..> CwaApi : HTTPS
    ForecastRepository ..> SQLite : 參數化 SQL 與交易
```

`WeatherUI` 包含 Streamlit 篩選、Pydeck 地圖、折線圖與表格；它接收同一批次的查詢結果，不自行解析 JSON。`ForecastService` 協調更新與查詢，持有單一更新鎖；一般篩選只查快照，不重新擷取。Demo 來源僅在使用者明確選取時使用。

## 3. 資料結構：領域類別圖

本圖描述資料實體及基數，不是完整 SQL schema。`0..1` 表示可無，`1..*` 表示至少一筆；nullable 欄位與資料約束以圖後說明為準。

```mermaid
classDiagram
    direction LR
    class Location {
        +string code
        +string name
        +float latitude
        +float longitude
        +string geo_source
        +string geo_version
    }
    class ForecastBatch {
        +int id
        +string dataset_id
        +string mode
        +string content_sha256
        +datetime source_issued_at
        +datetime fetched_at
        +int row_count
    }
    class ForecastPeriod {
        +int batch_id
        +string location_code
        +datetime start_at
        +datetime end_at
        +float min_temp_c
        +float max_temp_c
        +string quality_flags
    }
    class DatasetState {
        +string dataset_id
        +string mode
        +int current_batch_id
        +datetime last_checked_at
        +datetime last_success_at
        +string last_error_code
    }
    ForecastBatch "1" *-- "1..*" ForecastPeriod : 擁有
    Location "1" -- "0..*" ForecastPeriod : 對應縣市
    DatasetState "0..1" --> "0..1" ForecastBatch : 目前成功快照
```

- `ForecastBatch` 組合擁有 `ForecastPeriod`：預報時段不能脫離批次存在；只發布完整驗證過的批次。
- `DatasetState` 對每個 `(dataset_id, mode)` 唯一；第一次成功匯入前可沒有目前批次。指向的批次必須具有相同資料集與模式；舊批次不一定有狀態物件指向。
- `ForecastPeriod` 複合鍵為 `(batch_id, location_code, start_at, end_at)`；批次的 `(dataset_id, mode, content_sha256)` 唯一，防止重複匯入。
- 座標、來源發布時間、首次更新前的成功時間／批次指標及缺失的溫度可為 NULL；無錯誤時錯誤代碼可空。圖中的型別不表示必填。
- 時間儲存為 UTC，畫面轉為 Asia/Taipei；最高／最低溫依原始時段對齊。日摘要是查詢結果，不另存成來源事實。
- `schema_migrations` 屬資料庫維護資訊，為保持圖面簡潔未列入領域圖。

## 4. 更新與查詢：循序圖

以下描述 live 模式。更新可能由到期檢查或使用者按鈕觸發，兩者都受到更新鎖與冷卻時間限制。Demo 以固定 fixture 取代 CWA 呼叫，且使用獨立模式的快照。

```mermaid
sequenceDiagram
    actor User as 使用者
    participant UI as WeatherUI
    participant Service as ForecastService
    participant Client as CwaClient
    participant API as CWA API
    participant Parser as ForecastParser
    participant Repo as ForecastRepository
    participant DB as SQLite

    User->>UI: 開啟頁面或要求更新
    UI->>Service: refresh_if_due / refresh_on_request
    Service->>Service: 檢查模式、到期、冷卻與更新鎖
    alt 允許更新且取得鎖
        Service->>Client: fetch_forecast
        Client->>API: HTTPS 請求（有限重試）
        API-->>Client: JSON 或失敗（含逾時）
        Client-->>Service: 擷取結果
        alt HTTP 或網路失敗
            Service->>Repo: record_refresh_result（安全錯誤代碼）
            Repo->>DB: 更新狀態，保留目前批次
        else 擷取成功
            Service->>Parser: normalize_and_validate
            Parser-->>Service: 正規化資料或契約錯誤
            alt 驗證失敗
                Service->>Repo: record_refresh_result（契約錯誤）
                Repo->>DB: 更新狀態，保留目前批次
            else 驗證通過
                Service->>Repo: publish_snapshot（資料與雜湊）
                Repo->>DB: 交易：檢查發布時間與內容雜湊
                alt 可接受的新內容
                    Repo->>DB: 新增或重用完整批次，切換指標，COMMIT
                else 與目前內容相同
                    Repo->>DB: 更新成功檢查時間，COMMIT
                else 過舊內容或寫入失敗
                    Repo->>DB: ROLLBACK；可寫時另記錄錯誤
                end
                Repo-->>Service: 成功／未變更／失敗
            end
        end
        Service->>Service: finally 釋放更新鎖
    else 未到期、冷卻中或已有更新
        Service->>Service: 使用既有快照，回報更新狀態
    end
    Service-->>UI: 更新結果
    User->>UI: 選擇縣市與日期
    UI->>Service: get_dashboard
    Service->>Repo: read_snapshot
    Repo->>DB: 同一讀取交易固定批次並取得資料
    DB-->>Repo: 批次、預報與狀態
    Repo-->>Service: 一致快照或無資料
    Service->>Service: 日期彙整、座標對照、判斷過期
    Service-->>UI: 儀表板資料或空資料狀態
    UI-->>User: 地圖、趨勢、表格及資料狀態
```

失敗時使用先前快照；沒有先前快照則顯示「尚無資料」。資料庫本身不可讀時顯示儲存錯誤，不保證仍能讀取舊資料。API Key 不出現在前端或錯誤日誌，所有更新分支都必須釋放鎖。

## 5. 更新生命週期：狀態圖

此圖描述更新工作的狀態；「資料是否過期」由時間與有效區間另外計算，不與更新成功／失敗混成一個狀態。

```mermaid
stateDiagram-v2
    state "閒置" as Idle
    state "擷取資料" as Fetching
    state "驗證資料" as Validating
    state "交易處理" as Publishing
    state "更新成功或內容未變" as Succeeded
    state "更新失敗" as Failed
    [*] --> Idle
    Idle --> Fetching: 允許更新且取得鎖
    Idle --> Idle: 未到期、冷卻中或已有更新
    Fetching --> Validating: 取得回應
    Fetching --> Failed: 網路或 HTTP 錯誤
    Validating --> Publishing: 資料契約通過
    Validating --> Failed: schema、單位或覆蓋錯誤
    Publishing --> Succeeded: 交易提交
    Publishing --> Failed: 過舊內容或交易失敗
    Succeeded --> Idle: 更新狀態並釋放鎖
    Failed --> Idle: 保留原批次並釋放鎖
```

畫面同時顯示三種獨立資訊：資料模式（live／demo）、可用性（有資料／無資料／過期）及最近更新結果。更新失敗不一定代表舊資料已過期；更新成功也不能讓已超過有效期間的預報重新變成有效。

## 6. 開發對應

| UML 範圍 | 主要實作階段 | 核心驗證 |
| --- | --- | --- |
| Client、Parser、Settings、DemoFixture | M1～M2 | 契約、缺值、逾時與無 Key 測試 |
| Repository、領域實體、更新狀態 | M2 | 冪等、交易回復、模式隔離與快照一致性 |
| Service、UI 的查詢流程 | M3 | 日期彙整及摘要／圖表／表格一致 |
| GeoCatalog、UI 地圖 | M4 | 座標映射、點擊同步與離島顯示 |
| 單一服務部署與 secrets | M5 | 重啟重建、密鑰管理與發布驗收 |

後續若新增即時觀測或多執行個體部署，需另補資料模型與並行控制設計；不直接重用預報時段或單一程序更新鎖。
