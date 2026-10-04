# M1：合成資料契約與待驗證對照

本文件保留 M1 合成契約定義。2026-10-04 已另外完成獨立 `parse_live_forecast`，以兩份真實回應驗證縣市／時段／溫度映射，詳見 [LIVE_CONTRACT.md](LIVE_CONTRACT.md)。`parse_demo_forecast` 仍只接受合成格式。官方溫度缺值語意尚待核對，M1 尚未全面驗收。

## 已有依據與限制

[中央氣象署精緻化天氣預報產品文件](https://opendata.cwa.gov.tw/opendatadoc/Forecast/F-D0047-001_093.pdf) 說明一週預報的 `Locations`、`Location`、`Geocode`、`WeatherElement`、`StartTime`、`EndTime` 及 `MinTemperature`／`MaxTemperature` 等標籤，溫度單位為攝氏度。

目前已透過真實 JSON 核對 `records` 外層、陣列形狀、中文 ElementName 與 22 縣市涵蓋。API 無已驗證發布時間，保留空值；溫度缺值的來源語意仍待核對。

## 合成格式 v1

範例位於 [synthetic_weekly_v1.json](../src/weather/fixtures/synthetic_weekly_v1.json)，打包在 Python 套件中。全部值由本專案虛構，沒有真實預報、個人資料或 API Key；`DEMO-TPE`／`DEMO-KHH` 不是政府縣市代碼。

| 欄位／路徑 | v1 規則 | 狀態 |
| --- | --- | --- |
| `schema_version` | 固定 `mysoul.synthetic-weekly.v1` | 本專案定義 |
| `synthetic`、`mode` | 必須為 JSON `true` 與 `demo` | 本專案定義 |
| `dataset_id` | `F-D0047-091`，僅表示未來欲對接的資料集 | 非真實擷取證明 |
| `temperature_unit` | 固定 `C` | 合成 wrapper 單位 |
| `source_issued_at` | 明確為 null，或含時區 ISO 8601 | 不假冒來源發布時間 |
| `payload.records.Locations[].Location[]` | 候選位置陣列 | 待真實 JSON 核對 |
| `Geocode`、`LocationName` | 固定兩個 DEMO 代碼與名稱配對 | 合成對照 |
| `WeatherElement[].ElementName` | `最低溫度`、`最高溫度`，各一次 | 中文值待真實回應核對 |
| `Time[].StartTime / EndTime` | 含時區、結束晚於開始、同因子不得重複或重疊 | 官方標籤＋本專案驗證 |
| `ElementValue[0].MinTemperature / MaxTemperature` | 數字、數字字串或 null；每個時段一個 ElementValue | 值與容器形狀待核對 |

未知版本、其他氣象元素、欄位缺失或不同結構一律拒絕；本版本不自動兼容舊式 `MinT`／`MaxT` JSON。真實資料通常包含更多元素，後續 live adapter 需明確選取需要的因子，不能直接把完整回應塞入 Demo parser。

## 正規化與驗證

- 依縣市與 UTC 起訖時間配對最低／最高溫，不依陣列順序。
- 輸出不可變的 `ForecastSnapshot` 與 `ForecastPeriod`；所有時間轉成 UTC。
- MinT／MaxT 的時段集合必須一致；一側缺數值以明確 null 表示，缺整個時段或元素視為錯誤。
- null 保留為 `None`，附缺值標記；0 為有效值。NaN、無限大、布林值及非數字拒絕。
- 合成契約的溫度合理範圍暫定 `-80～65°C`，超出則拒絕；這是本專案防錯規則，不是 CWA 官方界線，也不推定 `-99`／`-999` 的來源語意。
- 最低溫大於最高溫、同因子時段重疊、重複縣市／因子／時段、全部溫度缺值均拒絕。
- 無發布時間附 `missing_source_issued_at`；抓取／載入時間由呼叫端提供，不以它替代發布時間。
- CLI 只輸出安全錯誤代碼，不回顯原始壞資料或密鑰；Demo 不會呼叫網路，真實更新使用獨立的 `weather-data update-live` 指令。

fixture 故意包含時段亂序、跨年與一個缺值，僅兩個縣市、兩個時段。它不是完整七日或 22 縣市資料；完整覆蓋與日彙整在後續階段實作。

## 真實契約驗收前仍需完成

- [x] 在本機透過環境變數提供合法 API Key，取得並清理真實回應。
- [ ] 確認外層資料集識別、發布時間、大小寫、元素名稱、陣列層級與單位。
- [x] 建立具來源的縣市代碼對照與完整涵蓋檢查。
- [ ] 核對官方缺值代碼、時段頻率與發布更新規則。
- [x] 建立獨立 live adapter 與真實回應 fixture；保留 Demo 的明確標示與模式隔離。
- [ ] 以真實資料完成 FR-02 契約驗收，再進入 M2 真實擷取與儲存驗證。
