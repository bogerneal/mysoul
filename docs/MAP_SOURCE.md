# 縣市代表點

`src/weather/fixtures/cwa_county_points_v1.json` 僅包含 22 縣市的代碼、名稱、經緯度。
來源為中央氣象署開放資料 `F-D0047-091`，2026-10-04 本機取得的回應，擷取
`Geocode`、`LocationName`、`Latitude`、`Longitude`；不含金鑰、請求網址或天氣原始樣本。

這些點是縣市預報代表點，不是測站，也不是縣市幾何中心。離島保留獨立代表點。
Demo 依名稱對應座標，但溫度與預報日期仍屬合成資料。

地圖採 Streamlit 內建 Pydeck 選取事件，取代原先規畫的 Folium，減少外掛依賴。
底圖使用 Pydeck 的 CARTO light 樣式，保留圖面來源標示；底圖需網路連線。
關閉底圖仍可看代表點；若 WebGL 或網路不可用，縣市選單與同日表格可完成查詢。

資料入口：[中央氣象署開放資料平台](https://opendata.cwa.gov.tw/)

2026-10-06：已加入代碼／名稱一致性及有限座標範圍檢查；個別或全部缺座標時明確警示，
全部縣市仍保留在同日表格。地圖繪製例外也不阻斷查詢；瀏覽器底圖網路失敗可手動關閉底圖。

本版使用 CARTO vector style；[官方說明](https://docs.carto.com/faqs/carto-basemaps)
指出向量底圖目前不受 raster 無 Key 浮水印影響，仍建議申請專用 Key 以因應後续規則調整。
頁面與地圖保留 CARTO／OpenStreetMap 標示；正式營運時依實際用途與用量確認供應者方案，
不把底圖服務視為永久無限制資源。
