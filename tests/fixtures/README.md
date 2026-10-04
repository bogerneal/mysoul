# CWA 真實測試樣本

`cwa_weekly_20261004.json` 取自使用者合法授權後擷取的中央氣象署 `F-D0047-091` datastore 回應。

- 擷取時間：2026-10-04T07:19:09.450480Z。
- 來源：https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091 （授權碼不包含在本文件或樣本）。
- 原始檔 SHA-256：`63c8e663bf985cc200fa61c487990c60cf54e9b2f044ccad1e2ae0ff399b37f4`。
- 保留原始 22 個縣市與每個縣市 14 個最低／最高溫時段、原始時間與數值。移除座標、無關氣象因子與多餘欄位描述；不是合成預報。
- 來源欄位沒有已驗證的發布時間，不以擷取時間或預報起點代替。
- 縣市 Geocode／名稱對照另存 `src/weather/fixtures/cwa_counties_v1.json`，直接來自此回應，標準格式參考 [CWA 產品文件](https://opendata.cwa.gov.tw/opendatadoc/Forecast/F-D0047-001_093.pdf)。
- 這份固定歷史樣本用於測試，不代表目前天氣。原始私有檔仍留在 `data/private/`，不加入 Git。
- 官方資料來源：中央氣象署；使用與再利用條件依 [平台說明](https://opendata.cwa.gov.tw/about) 查核。此檔保留來源標示，不替外部資料聲稱專案自己的授權。

`cwa_weekly_20261004_evening.json` 使用相同精簡方式，擷取時間為 2026-10-04T12:20:52.271766Z，原始檔 SHA-256 為 `c52016bb1124d1b59a7b0e2b3d3474e5f4a635dad4ff5239e700daa071b313f8`。晚間批次每縣市有 **15** 個時段，涵蓋 2026-10-04 18:00 至 2026-10-12 06:00（UTC+08:00）；下午批次則有 14 個時段。兩份樣本共同驗證可變時段數，不能假設每次固定 14 筆。
