# Streamlit Community Cloud 部署與復原

更新：2026-10-06（Asia/Taipei）。使用者已完成 Streamlit Community Cloud 部署。
公開網站：[台灣一週天氣 · mysoul](https://mysoul-9hyuk7z9oawbtdzjx2u3s4.streamlit.app/)。
真實預報與選配自動更新已在線上確認；其餘驗收結果與限制記錄於 PROGRESS.md。

## 部署設定

新增即時觀測沿用 `CWA_API_KEY` 與 `WEATHER_AUTO_REFRESH`，不需新增 Secrets。観測模式每 10 分鐘由訪客觸發更新，另存 `data/weather_observations.sqlite3`；預報維持 30 分鐘。首次切換即時觀測會建立並擷取資料。詳見 [即時觀測說明](OBSERVATIONS.md)。

1. 登入 <https://share.streamlit.io/>，連接具有 `bogerneal/mysoul` 存取權的 GitHub 帳號。
2. 建立 app：Repository `bogerneal/mysoul`、Branch `feat/weather-reliability`、入口 `app.py`。
   功能分支通過 CI 並合併後，可將部署分支改為 `main`。
3. Advanced settings 選 Python **3.14**（本機驗證 3.14.3），若平台尚未提供，改選 CI 已驗證的 3.12。
4. 在雲端 Secrets 填入以下結構；將占位文字換成自己的有效授權碼，不將實際值提交到 Git。

```toml
CWA_API_KEY = "填入你的有效授權碼"
WEATHER_AUTO_REFRESH = "true"
```

5. 按 Deploy，查看建置與啟動日誌。根目錄的 `uv.lock` 與 `pyproject.toml` 安裝
   `src/weather` 套件，不需要額外維護另一份 requirements.txt。
6. 首次開啟真實模式會取得最新預報。沒有 secrets 時仍可明確選擇 Demo，再按載入。

官方依據：[部署步驟](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)、
[依賴檔優先順序](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)、
[Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)。

## 更新與儲存政策

- SQLite 預設 `data/weather.sqlite3`，只保存目前與前一次成功快照，沒有歷史永久保存承諾。
- 雲端磁碟可能被重建；沒有資料庫時自動建立 schema，啟用自動更新且有 Key 時重新擷取。
- 自動更新由開啟／操作頁面觸發，每 30 分鐘最多嘗試一次；失敗也受節流限制。
  沒有訪客時不會固定排程更新。手動更新至少間隔 60 秒。
- 同一 Python 程序內互斥；不支援多程序／多執行個體共用此更新政策。
- 更新失敗保留成功快照；沒有成功快照則顯示空狀態，不自動用 Demo 替代真實資料。
- stdout 保留 CLI JSON；`weather.updates` 在 stderr 輸出 JSON 日誌，包含批次、資料集、
  模式、操作、耗時、筆數、結果及白名單錯誤碼，不輸出 API Key、原始 payload 或 URL。
- 未確認的溫度缺值會拒絕整批更新，並保留上一批；目前尚未全面完成官方缺值契約驗收。

## 上線後驗收

- [x] 公開網址可存取，Cloud 應用程式啟動成功；網址見本文件開頭。
- [ ] 管理頁核對部署分支與實際 commit（驗收前功能分支 HEAD 為 ebdfdf8，公開頁面未提供部署 SHA）。
- [x] 真實模式顯示 22 縣市、取得時間及預報日期；來源發布時間缺值明確標示。
- [x] 切換縣市／日期、離島、390px 模擬手機與 1440px 桌面查詢正常。
- [ ] 實體手機操作驗收。
- [x] 地理底圖視覺驗收：改用 OSM，等待圖磚載入後確認底圖、界線、數字標籤可見。
- [x] 關閉／阻擋底圖時，仍可透過選單與表格查詢。
- [x] 使用者 Reboot 後預報可讀，新觀測資料庫自動擷取 363 站，無需新增 Secrets。
- [ ] 人為磁碟重建及版本回復；不得以測試 fixture 冒充最新資料。
- [ ] 更新失敗時保留舊資料，無 Key 時可使用明確 Demo。
- [ ] 雲端日誌無密鑰或完整 API 請求 URL。

## 回復上一版

在 Streamlit 管理頁將 app 改回先前已驗證的 Git 分支／版本，或透過 Git revert 回復問題提交。
本次沒有變更 SQLite schema v1，舊版本可讀既有資料；若雲端資料庫遺失，依上述政策重建。
正式操作前先記錄目前版本，保留可回復的 Git 提交；不需要將本機私有樣本或 SQLite 上傳 GitHub。

## 已知限制

底圖改為 OpenStreetMap raster，需網路與 WebGL；提供者服務規則可能調整，頁面保留 OpenStreetMap 來源標示。預報地圖為縣市代表點、觀測地圖為真實測站；皆非全台連續溫度場。
官方溫度缺值規則與實體觸控裝置驗收尚待補齊；模擬手機測試不等同實機驗收。
