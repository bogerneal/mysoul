# 架構與資料設計

本文件描述目標架構。目前已有真實／離線解析器、SQLite repository、更新服務、HTTP client 與資料查詢指令；UI 與地圖仍待實作。已核對兩份真實 CWA 樣本，官方溫度缺值語意仍待確認，詳見 [真實資料契約](LIVE_CONTRACT.md)。

搭配 [UML 系統架構](UML.md) 閱讀：該文件以類別圖、循序圖與狀態圖呈現本設計；本文件保留欄位、交易與部署規則。

## 1. 模組邊界

| 模組 | 責任 | 不應負責 |
| --- | --- | --- |
| `config` | 讀取環境設定、驗證必要參數 | 輸出密鑰 |
| `cwa_client` | HTTP、逾時、重試、回應狀態 | 操作 Streamlit 元件 |
| `parser` | API schema 映射、型別與時段驗證 | 連線資料庫或補造氣象數字 |
| `repository` | migration、交易、快照儲存與查詢 | 決定畫面樣式 |
| `forecast_service` | 固定批次、依日期彙整、資料狀態；協調更新鎖、擷取、驗證與儲存 | 在每次篩選時重新抓 API |
| `geo` | 縣市代碼、名稱與代表點對照 | 將代表點誤標為測站 |
| `ui` | 篩選、摘要、圖表、表格、地圖 | 自行解析 CWA JSON |

目標目錄如下，包含尚未建立的 API、資料庫與 UI 模組；目前實作另有 `models.py`、`demo.py`、`__main__.py` 及打包用合成 fixture：

```text
mysoul/
├── README.md
├── docs/
├── app.py
├── pyproject.toml
├── src/weather/
│   ├── config.py
│   ├── cwa_client.py
│   ├── parser.py
│   ├── repository.py
│   ├── forecast_service.py
│   ├── geo.py
│   └── ui/
├── migrations/
├── data/reference/        # 可公開且附來源的縣市對照
├── tests/fixtures/        # 合成／去密鑰範例，標明來源
└── .github/workflows/ci.yml
```

## 2. 內部資料契約

候選來源為 `F-D0047-091`。內部欄位名稱由本專案定義，不能假設 API 使用相同拼字或大小寫。

| 欄位 | 內部型別／規則 |
| --- | --- |
| `dataset_id` | 資料集識別碼 |
| `location_code` | 穩定縣市代碼；若 API 沒有，使用有來源且版本化的對照，不能取陣列索引 |
| `location_name` | 顯示名稱；「台／臺」別名只在輸入對照時正規化 |
| `start_at`、`end_at` | 帶時區 ISO 8601，內部轉成統一 UTC；`end_at > start_at` |
| `min_temp_c`、`max_temp_c` | 有限數字或 NULL；單位固定 °C，缺值不是 0 |
| `source_issued_at` | 來源發布時間；不存在則 NULL，不以抓取時間假冒 |
| `fetched_at` | 成功取得回應的時間，UTC |
| `mode` | `live` 或 `demo` |
| `quality_flags` | 缺值、部分涵蓋、來源缺少發布時間等可解釋標記 |

MinT 與 MaxT 依 `(location_code, start_at, end_at)` 對齊。預期欄位缺失、未知單位、無法識別縣市或 `min > max` 視為契約錯誤，拒絕發布該批次並保留原資料；已知缺值代碼可轉 NULL 並標記。未知 schema 不嘗試猜測。

沒有有效溫度的空回應不能替換既有成功快照。M1 確認預期縣市與時段覆蓋後，M2 加入覆蓋檢查；異常缺少整個縣市或大量時段時拒絕切換批次並記錄原因。

## 3. 日期與顯示語意

- 原始預報以半開區間 `[start_at, end_at)` 保存；介面統一顯示 Asia/Taipei。
- 使用者選擇日期 D 時，查詢與當地 `[D 00:00, D+1 00:00)` 有交集的時段。
- 當日最低溫取這些時段 MinT 的最小值，最高溫取 MaxT 的最大值；缺的一側維持缺值。
- 跨日時段可能同時影響相鄰兩日，這是「涵蓋該日之預報時段彙整」，不是逐時資料計算的精確日極值；畫面與匯出需說明。
- 日夜時段不足以完整涵蓋該日時標示「部分時段」，不補造剩餘資料。
- 最多顯示從台北當日開始、實際有資料的七個日期；沒有資料的未來日不生成假紀錄。Demo 使用 fixture 的固定日期，不以目前日期裁掉所有範例。
- 最高／最低溫平均不是觀測平均溫；MVP 不顯示這種衍生「平均溫」。

## 4. SQLite 資料模型

初期採不可變的成功快照與可切換的目前批次。比教學圖片的單一日期表多保留來源及時間資訊，以支援修訂、去重及失敗回復。

| 資料表 | 主要欄位 | 約束與用途 |
| --- | --- | --- |
| `locations` | `code`、`name`、`latitude`、`longitude`、`geo_source`、`geo_version` | `code` 主鍵；座標可空；座標為展示代表點 |
| `forecast_batches` | `id`、`dataset_id`、`mode`、`content_sha256`、`source_issued_at`、`fetched_at`、`row_count` | `(dataset_id, mode, content_sha256)` 唯一；只記錄完整通過驗證的快照 |
| `forecast_periods` | `batch_id`、`location_code`、`start_at`、`end_at`、`min_temp_c`、`max_temp_c`、`quality_flags` | 主鍵 `(batch_id, location_code, start_at, end_at)`；外鍵連接批次與縣市 |
| `dataset_state` | `dataset_id`、`mode`、`current_batch_id`、`last_checked_at`、`last_success_at`、`last_error_code` | `(dataset_id, mode)` 主鍵；真實／示範分開管理 |
| `schema_migrations` | `version`、`applied_at` | 記錄資料庫結構版本 |

規畫約束與索引：

- 每次連線啟用 SQLite 外鍵；MinT／MaxT 皆存在時檢查 `min_temp_c <= max_temp_c`。
- 時間寫入前正規化為相同 UTC 格式，再檢查起訖；建立 `(batch_id, start_at, end_at)` 查詢索引。
- SQL 參數化，不拼接使用者輸入。
- 先只保留目前及前一個成功快照；切換成功後才清理更舊批次。歷史預報倉儲不屬 MVP。
- 畫面請求在同一讀取交易中固定 `current_batch_id` 並取得所需資料，再由記憶體結果繪製所有視圖，避免清理舊批次時影響正在讀取的畫面。

## 5. 更新、去重與快取

1. 取得單一更新鎖，避免多使用者／rerun 同時啟動擷取。MVP 限單一服務執行個體。
2. 請求 CWA，驗證 HTTP、JSON schema、單位、資料覆蓋與溫度值。
3. 將穩定排序的正規化資料、資料集、模式與來源發布時間（若有）計算雜湊；排除抓取時間，避免每次都產生新內容。
4. 雜湊與目前資料相同時只更新成功檢查時間；內容變更時，在同一交易內新增批次與全部預報，再切換目前批次。若雜湊已存在於保留快照，通過時間檢查後重用該批次，避免唯一約束衝突。
5. 寫入失敗則 rollback；在獨立狀態更新記錄安全錯誤代碼。舊批次仍可讀。
6. 若來源發布時間早於目前批次，拒絕倒退；來源沒有發布時間時記錄限制，且僅允許序列更新。
7. 查詢快取包含批次 ID；成功切換批次後不會誤用舊快取。

初始可調政策：連線逾時 5 秒、讀取逾時 20 秒，最多 3 次請求；僅暫時性網路錯誤、429 與部分 5xx 重試，尊重 `Retry-After` 並設總等待上限。401／403、schema 錯誤不反覆重試。

更新檢查間隔暫定 30 分鐘，超過 6 小時未成功確認資料則提示可能過期；這是產品初值，不是 CWA 發布頻率或承諾，M1 查核後調整。即使最近檢查成功，若全部預報有效時間已過也必須標記過期。

MVP 在頁面使用時按到期條件更新，並提供受冷卻時間限制的手動更新；沒有訪客時不承諾背景更新。固定排程是部署階段的獨立決策。

## 6. 介面規畫

桌面：側欄放縣市、日期、更新操作與資料狀態；主區放摘要、地圖與溫度趨勢，下方為時段表格。手機：篩選區在上方，摘要、地圖、圖表、表格依序排列。

地圖顯示選定日期的各縣市代表點，選定縣市加上醒目外框；色彩表示「當日預報最高溫」，tooltip 包含縣市、日期、最低／最高溫、資料有效區間及部分涵蓋提示。缺值用中性色並顯示「無資料」。地圖點擊與選單共用同一選取狀態。

初期固定色階草案：`<20°C`、`20–<25°C`、`25–<30°C`、`>=30°C`，僅協助讀圖，不是氣象警報門檻。圖例含文字，不能只靠顏色。離島需可看見或可透過選單移動視野。

## 7. 部署與資料生命週期

本機先完成可重現驗證，再評估 Streamlit Community Cloud 作展示。其本機檔案不保證持久保存，故 SQLite 初期視為可重建快照。來源：[Streamlit 官方說明](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)。

若有永久歷史、多人寫入或多執行個體需求，改用持久磁碟或外部 PostgreSQL，並重新評估 migration、備份及並行控制。不能把本機 SQLite 的單一更新鎖直接當成分散式鎖。

CWA Key 由環境變數或 Streamlit secrets 提供；若 API 將授權放在 query，日誌需移除該參數。底圖／地理資料的授權與來源確認後才納入發布版本。

發布失敗時回復上一個已驗證提交，資料庫 migration 需有相容性或重建策略。MVP 不執行不可逆的歷史資料遷移；真實資料不可以離線示範數字靜默替代。

## 8. M2 本機實作差異

- schema 版本使用 SQLite `PRAGMA user_version=1`；未知未來版本拒絕開啟，初始化具交易保護。
- `forecast_periods` 暫時直接保存不可變的縣市代碼／名稱；含座標的 `locations` 目錄於真實縣市契約與 M4 再加入，避免不同快照的名稱被覆寫。
- 所有批次資料先驗證，再於 `BEGIN IMMEDIATE` 交易內寫入、切換與保留兩個快照；讀取同一交易固定批次。
- 更新鎖目前適用單一 Python 程序，SQLite 另序列化寫入；時間檢查拒絕倒退。UI 的全流程更新鎖、冷卻與計時日誌仍待整合。
- `capture-cwa` 只存 Git 忽略的私有待驗證樣本，不建立 live 快照。沒有 Key 時的測試為 HTTP mock，不能替代真實契約驗收。

## 9. 真實更新與樣本匯入

`update-live` 在同一程序更新鎖中完成網路擷取、契約驗證與 SQLite 原子發布。`import-cwa` 保留呼叫者提供的原始擷取時間，不把匯入時間當新擷取。除既有擷取／發布時間倒退檢查，live 快照也拒絕預報末端倒退；同一覆蓋期間的修訂先後因 API 缺發布時間仍有限制。任何失敗保留舊批次。

版本化解析規則：完整 22 縣市、每縣市 14／15 時段、第一時段可不足 12 小時，其後連續 12 小時、末端台灣時間 06:00；兩份真實 fixture 同時驗證。未知溫度缺值先拒絕，需更多來源依據才能安全轉 NULL。
