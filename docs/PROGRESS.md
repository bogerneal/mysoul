# 專案開發進度

最後更新：2026-10-04（Asia/Taipei）

## 目前位置

M1 離線基礎完成，M2 離線資料管線已實作並通過本機驗證。真實 CWA 契約與 live adapter 尚未完成，M2 尚未全面驗收。M3 查詢介面、M4 地圖、M5 部署仍待開發。

本機目錄：`C:\Users\USER\Downloads\mysoul`

目前分支：`feat/m2-local-pipeline`

同步分支：`origin/feat/m2-local-pipeline`；本次提交整理 M2 本機管線與設定文件，透過 PR 供審閱；`main` 合併狀態以 GitHub PR 為準。

## 里程碑

| 階段 | 狀態 | 尚缺項目 |
| --- | --- | --- |
| M0 規畫 | 文件初稿完成 | 隨實作修訂 |
| M1 資料契約 | 離線部分完成；已取得真實樣本 | 縣市對照、欄位、缺值及時段覆蓋驗證 |
| M2 資料管線 | 離線儲存及 HTTP client 完成 | live adapter、真實整合、更新冷卻、更新中狀態與批次耗時日誌 |
| M3 查詢介面 | 待開發 | 縣市／日期篩選、摘要、圖表、表格及狀態提示 |
| M4 互動地圖 | 待開發 | 代表點、圖例、選取連動與手機驗收 |
| M5 發布維運 | 待開發；CI 基礎已有 | 部署、重啟復原及完整產品驗收 |

## 已完成與驗證

### 2026-10-04：本機環境與 M2 離線管線

- 已安裝 Git、uv 0.12.21、Python 3.14.7，建立專案 `.venv` 並同步鎖定依賴。
- 新增 SQLite schema v1、外鍵、唯一約束、交易與固定快照讀取。
- 新增內容雜湊去重、目前／前一次成功快照保留、更新時間倒退拒絕與失敗回復。
- Demo 與 live 儲存狀態分離；過期判斷依最後成功時間及預報有效期間。
- 新增 `weather-data update-demo`、`status --mode demo/live` 指令。
- 新增 CWA HTTP client：逾時、有限重試、Retry-After 處理與安全錯誤碼。
- 新增 `capture-cwa --prompt-key`，隱藏輸入授權碼；原始樣本存於 Git 忽略的 `data/private/`，不直接發布為 live 預報。
- 已更新 README、開發計畫、架構與本機設定說明，並加入 CI 資料管線示範指令。

本機驗證結果（Windows／Python 3.14.7）：

| 檢查 | 結果 |
| --- | --- |
| pytest | 80 項通過 |
| Ruff lint／format | 通過 |
| sdist／wheel 建置 | 通過 |
| 連續兩次 Demo 匯入 | 同為 batch ID 1，未重複建立批次 |
| SQLite 查詢 | 正確讀取四筆合成預報 |
| Git 忽略規則 | 本機資料庫及私有樣本均被排除 |

此階段的 API 測試使用 HTTP mock；後續真實擷取結果見下方紀錄。新增 CI 設定尚未推送，因此沒有本次變更的雲端 CI 結果。

### 2026-10-04：進度文件維護

- 建立本文件，整理目前進度、驗證證據、待辦及使用者設定。
- 在 README 加入進度入口，並在專案協作指引記錄後續同步更新要求。
- 此次僅新增／調整文件，沿用上述程式驗證結果，未重跑測試。

### 2026-10-04：首次真實 CWA 樣本擷取

- 已使用使用者提供的授權碼成功擷取 `F-D0047-091`，結果為 `captured_unverified`。
- 私有檔案：`data/private/cwa-20261004T071909450480Z.json`（Git 已忽略）。
- 初步確認 `records.Locations` 有一組資料，內含 22 個縣市；位置欄位包含 `LocationName`、`Geocode`、`Latitude`、`Longitude`、`WeatherElement`。
- 原始樣本未包含授權碼；授權碼僅存在此次執行環境，已於結束時移除，未存入專案或持久環境設定。
- 首次 Requests 連線發生 TLS 憑證驗證失敗；加入 truststore，讓此 client 使用作業系統受信任憑證，仍檢查憑證與主機名稱，未關閉 HTTPS 驗證。
- 新增 TLS 錯誤分類及測試；本機 pytest **82 項通過**，Ruff lint／format 通過。
- 尚未完成真實欄位、缺值、完整時間覆蓋驗收，也未建立 live adapter 或匯入 live 快照。

### 2026-10-04：同步 GitHub

- 整理本機 M2 資料管線、CWA 樣本擷取／TLS 修正、測試與進度文件，發布至功能分支。
- 提交前檢查授權碼未出現在待提交檔案；私有樣本、SQLite、虛擬環境與建置產物不納入版本控制。
- 真實資料仍只有樣本擷取完成，live adapter 與網站介面尚未完成。
- 雲端 CI 結果以此次功能分支／PR 的 GitHub Actions 為準。

## 使用者需要做的事

授權碼申請及首次擷取已完成。目前不需要額外設定，下一步可直接使用本機樣本驗證資料契約。以下保留日後重新擷取步驟；請使用隱藏輸入，不要將授權碼加入 Git。

1. 前往 [中央氣象署開放資料平台](https://opendata.cwa.gov.tw/)完成註冊與平台要求的驗證，登入取得 API 授權碼。
2. 在本機 PowerShell 執行：

```powershell
cd C:\Users\USER\Downloads\mysoul
uv run --locked weather-data capture-cwa --prompt-key
```

3. 依提示輸入授權碼；成功顯示 `captured_unverified` 後，告知開發者「已擷取」。若失敗，只需提供錯誤代碼。

完整說明見 [LOCAL_SETUP.md](LOCAL_SETUP.md)。目前無需雲端帳號、網站部署或額外資料庫設定。

## 下一步

1. 使用已取得的本機真實樣本，核對縣市代碼、溫度欄位、時區、缺值及覆蓋範圍。
2. 建立獨立 live adapter 與去密鑰 fixture，完成 M1 真實契約驗收。
3. 接上 M2 真實匯入，驗證失敗回復、完整覆蓋與更新政策。
4. 依開發計畫進入 M3 查詢介面。

## 更新方式

每次完成一段實作、取得驗證結果、發現阻礙或需要使用者額外設定時，同步更新本文件。需求驗收勾選維護於 [PLAN.md](PLAN.md)；此處記錄實際進度與證據。明確區分本機／遠端、離線／真實驗證，不以測試全通過代表產品全部完成。
