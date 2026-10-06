# 即時觀測與地圖

在頁首切換「未來預報／即時觀測」。兩者有獨立資料庫、更新時間與控制項；Demo 只屬於預報模式。

## 操作

- 即時觀測使用 CWA `O-A0003-001`，沿用 `CWA_API_KEY`，不需新增 Secrets。
- 「更新即時觀測」至少間隔 60 秒。`WEATHER_AUTO_REFRESH="true"` 時，開啟或操作觀測頁每 10 分鐘檢查一次；預報仍為每 30 分鐘，沒有訪客時不會背景排程。
- 切換氣溫、當日累積雨量、風速風向、濕度；可依縣市篩選並點選測站圓點或下方測站選單查阅明細。
- 全台統計使用本資料集近一小時、非未來超過 5 分鐘的有效觀測；不隨縣市篩選改變。各測項排除缺值，各站時間可能不同。最高／最低氣溫是測站最新值的比較，不是當日歷史極值；最大風速是平均風速，不是陣風。
- 雨量是台灣時間當日累積，不是每小時雨量。雨跡 T、故障 X、缺值 -99 不轉成 0；-98 保留「連續 6 小時無降水」，不推算當日累積量。風向 990 不繪製方向箭頭。濕度原值已是百分率，不乘 100。
- 地圖支援深色／街道、界線、數字標籤開關。深色使用街道底圖灰階調暗。數字密集時可放大或關閉標籤；無座標仍保留於表格。這是測站點值，不是全台內插溫度場。

## 儲存與故障

觀測 SQLite 放在 `WEATHER_DB` 同目錄、檔名加 `_observations`，預設 `data/weather_observations.sqlite3`。只有成功解析且含新鮮有效觀測才以交易切換快照；更新失敗保留原資料，失敗嘗試亦節流。過期／未來時間異常資料不進統計，使用者可勾選「包含過期觀測」查阅。空資料庫會在啟用自動更新且有 Key 時重新擷取。

日誌只含資料集、成功／失敗、筆數及耗時，不記錄 Key、原始回應或請求 URL。原始樣本、SQLite、瀏覽器截圖均在 Git 忽略路徑。

## 資料與授權

- [CWA 觀測標準 v1.02](https://opendata.cwa.gov.tw/opendatadoc/Observation/A0040-002.pdf)，適用 O-A0003-001，欄位與特殊碼見第 3–5 頁；實際 JSON 使用 `StationId`。2026-10-06 20:10 的兩站精簡樣本為 `tests/fixtures/cwa_observation_20261006.json`，來源中央氣象署，僅供契約測試，非應用程式即時備援資料。
- [CWA 資料使用規範](https://opendata.cwa.gov.tw/about/rules)。
- 界線來源：[taiwan-atlas](https://github.com/dkaoster/taiwan-atlas)，內政部縣市界線衍生資料，固定 [2021.9.20 counties-10t.json](https://cdn.jsdelivr.net/npm/taiwan-atlas@2021.9.20/counties-10t.json)。解碼 TopoJSON delta arcs、反向共用邊並拼接為 GeoJSON，座標取小數六位；包含 22 縣市。概略展示用，不作現行地籍依據。
- 圖資衍生檔 `src/weather/fixtures/taiwan_counties.geojson` SHA-256：`65a6470a97caa96fde817878e133766d38fa7cde2d7934d5487434193c452dc2`。保留同目錄 `taiwan-atlas-LICENSE.txt` MIT 授權；[原始政府資料](https://data.gov.tw/dataset/7442)依其開放資料授權使用。
- 底圖：[OpenStreetMap](https://www.openstreetmap.org/copyright)。瀏覽器直接請求可見範圍圖磚，保留來源、Referer 與 HTTP 快取；不預抓、不提供離線下載。遵循 [圖磚使用政策](https://operations.osmfoundation.org/policies/tiles/)，高流量應更換適合的供應商。
- 原 CARTO 圖磚實測回傳 HTTP 200 但內容為 API KEY REQUIRED；因此改用 OSM，不能以 HTTP 成功作為底圖視覺驗收證據。

## 本次範圍以外

雷達、颱風、特報、定位、連續內插色彩場與圖片中的全螢幕浮動面板未納入這三項功能。
