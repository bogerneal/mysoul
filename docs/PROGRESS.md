# 專案開發進度

最後更新：2026-10-06（Asia/Taipei）

## 2026-10-06：可靠性與部署版本準備

- 真實 CWA 擷取成功，台灣時間 01:36，22 縣市、330 筆，涵蓋 10/06 00:00～10/13 06:00。原始回應與 SQLite 留在 Git 忽略路徑，無持久保存 Key。
- 已加入 JSON 更新日誌、錯誤碼白名單、失敗狀態儲存保護；缺座標及地圖繪製失敗仍保留全部縣市表格。
- 新增凌晨精簡 fixture，三份真實樣本逐筆核對；Windows／Python 3.14.3 與乾淨的 Python 3.12.13 環境各 138 項測試通過。
- 加入選配 30 分鐘訪客觸發更新及空資料庫復原，已選定 Streamlit Community Cloud，部署文件已建立。
- 官方 PDF 已重新下載核對，仍未找到溫度缺值定義；未知缺值維持拒絕整批更新。
- 01:47 再以實際 update-live 更新成功，沿用 batch 1（330 筆），JSON 日誌記錄耗時約 280ms；真實服務驗證與離線測試分開記錄。
- Edge 154／Intel Core i5-12400：1440px 桌面切換金門約 0.194 秒（不含外部底圖）；390px 模擬觸控選連江成功，無整頁水平溢出。阻擋外部底圖時兩份表格仍可查，無頁面例外。CARTO 樣式與圖磚請求回應 200；截圖與 browser-results.json 留於 data/private。
- 模擬手機不等於實體手機；目前沒有實機與雲端正式網址驗收，不將兩者勾選完成。
- 已修正文檔中 live／網頁尚未實作的舊描述，新增 DEPLOYMENT.md；目標分支為 feat/weather-reliability，雲端部署仍待使用者登入授權與設定 secrets。
- 已透過 GitHub 連線同步功能分支，提交 `b524f1e`，建立 [PR #5](https://github.com/bogerneal/mysoul/pull/5)。[雲端 CI](https://github.com/bogerneal/mysoul/actions/runs/37351636933) 已完成且成功；尚未合併 main。
- 使用者協助事項：登入 Streamlit Community Cloud，選 `bogerneal/mysoul`、`feat/weather-reliability`、`app.py`，在 Advanced settings 選 Python 3.14 並設定 `CWA_API_KEY`／`WEATHER_AUTO_REFRESH="true"`，部署後提供公開網址以便實測。現有工具沒有 Streamlit 帳號登入與部署權限，不能將 GitHub CI 成功視為網站已上線。

## 2026-10-06：完整儲存庫讀取與進度查核

- 從 GitHub 複製 `main`，查核版本 `f4af2f800e390505451dfe49adf1039d28bb6de8`。本次工作目錄為 `C:\Users\user\Downloads\Fix\mysoul`；下方舊路徑與既有資料庫描述屬先前工作紀錄，不代表新副本已有 live 資料庫。
- 遞迴讀取此版本全部 51 個 Git 追蹤檔案，包含隱藏設定、10 份 docs 文件、程式、測試、全部 JSON 與 `uv.lock`；全部可用 UTF-8 解碼，無二進位檔案或子模組。讀取範圍不含其他分支歷史版本、Git 內部物件及未上傳的私有檔案。
- 大型資料完整解析：兩份真實 fixture 各含 22 縣市，分別為 308／330 筆配對時段；鎖定檔含 45 個套件記錄（含本專案）。逐檔讀取清單與 SHA-256 留在工作區上層 `mysoul-read-manifest.json`。
- 本次實際驗證：`uv sync --locked` 成功；Windows／Python 3.14.3 下 pytest 116 項通過、Ruff lint 與 format 通過、sdist／wheel 建置成功。測試為固定樣本及 HTTP mock，未請求真實 CWA、未重新進行瀏覽器或公開部署驗收。
- 目前實作確認：真實／Demo 隔離、SQLite 快照與失敗保留、查詢介面、日期彙整、代表點地圖已存在。M1 官方溫度缺值語意、M2 結構化批次日誌、M4 異常情境驗收、M5 部署仍待完成。
- 發現文件落差：`LIVE_CONTRACT.md`、`LOCAL_SETUP.md`、`REFERENCES.md`、`UML.md` 部分段落仍稱 live 或網頁未實作；`ARCHITECTURE.md` 混合目標設計與現況。後續應同步修正文案，不能以舊段落判斷實作進度。
- 發現地圖驗收缺口：`ui.draw_map` 遇個別縣市缺座標會略過，只有全部無可畫資料才顯示提示；同日地圖表格也僅取有座標的列。尚未滿足 FR-07 的個別缺座標警示與資料保留要求，本次未修改功能。
- 建議下一步：先修正文案與現況差異，再補 M1 缺值依據／更多發布批次、M2 安全批次耗時日誌及 M4 缺座標／底圖失效驗收，最後進行 M5 部署與重啟復原驗證。
- 同步狀態：本次僅本機進度文件變更，尚未提交或推送；里程碑驗收標準未變，PLAN 不調整。檢視 Demo 不需 Key；新副本取得最新真實預報仍需 CWA 授權碼。

## 2026-10-05：參考網站功能差異盤點

- 實際以瀏覽器查看參考網站與雨量／雷達／颱風／風速圖層入口，整理 [功能比較](REFERENCE_COMPARISON.md)。
- 主要差距：即時觀測、多氣象欄位、測站、特報、雷達／颱風、地圖操作與公開部署。
- 保留「即時觀測」與「一週預報」資料語意，新增功能順序屬建議，尚未實作。
- 比較文件與本進度紀錄同步至 GitHub `main`；本次僅修改 Markdown，已檢查差異與格式，未變更程式功能，未重跑程式測試。

## 2026-10-05：Streamlit 查詢介面與基本地圖完成

- 依圖片工作流程推進 M3／M4，已安裝並鎖定 Streamlit、Pandas、Altair、Pydeck。
- 已加入縣市／日期選擇、每日溫度彙整、趨勢圖、時段表與代表點地圖。
- 明確分離真實與 Demo；顯示資料取得時間、發布時間缺值、過期與更新失敗狀態。
- 網頁更新採程序內互斥與每資料庫 60 秒冷卻，切換篩選不重新請求 API。
- 本機 116 項 pytest 通過，Ruff lint／format、sdist／wheel 建置通過。
- Edge 瀏覽器實測：1440px 桌面與 390px 手機寬度、22 縣市資料、地圖底圖、點選金門連動側欄成功，沒有頁面例外或整體水平溢出。截圖留在被 Git 忽略的 `data/private/`。
- 修正關閉底圖時 Streamlit 自動套用預設底圖的情況，改用明確空白樣式。
- 網頁功能已透過 [PR #4](https://github.com/bogerneal/mysoul/pull/4) 合併至 GitHub `main`；[Python 3.12～3.14 雲端 CI](https://github.com/bogerneal/mysoul/actions/runs/37297095077) 全數通過。
- 使用者設定：查看現有資料／Demo 不需 API Key；手動更新真實天氣需伺服器端 `CWA_API_KEY`。
- 新增 `start-dashboard.cmd`；README、PLAN 與 LOCAL_SETUP 已更新。預覽為 `http://localhost:8501`。
- 本次沒有重新請求 CWA；畫面讀取既有 batch 3 並標示過期，不將本機 UI 驗證冒充即時 API 更新。

## 目前位置

本機真實 CWA → 解析 → SQLite → Streamlit 查詢已接通，現有真實資料包含 22 縣市、330 筆時段。M2 結構化日誌、M3 介面、M4 缺座標與繪製失敗降級已完成；M1 官方缺值語意、M4 實體觸控及 M5 雲端部署驗收仍待補齊。

本機目錄：`C:\Users\user\Downloads\Fix\mysoul`

目前功能分支：`feat/weather-reliability`，基於 `main` 的 `f4af2f8`。

既有真實管線（PR #3）與 Streamlit 網頁（PR #4）已在 GitHub `main`；本次可靠性與部署修改使用獨立功能分支，不代表已合併或公開上線。API Key 不保存，SQLite、私有原始樣本及瀏覽器截圖維持 Git 忽略。

## 里程碑

| 階段 | 狀態 | 尚缺項目 |
| --- | --- | --- |
| M0 規畫 | 文件初稿完成 | 隨實作修訂 |
| M1 資料契約 | 三份真實樣本逐值驗證、22 縣市與時段完整 | 官方溫度缺值语意、更多發布批次 |
| M2 資料管線 | 真實更新／儲存／查詢、冷卻、JSON 日誌與單程序協調完成 | 多程序為未支援範圍 |
| M3 查詢介面 | 本機實作與自動化測試完成 | 持續使用回饋 |
| M4 互動地圖 | 代表點、缺座標保留、底圖阻擋與模擬觸控驗證完成 | 實體觸控裝置驗收、正式營運授權條件確認 |
| M5 發布維運 | 已選 Cloud、補復原與更新政策、乾淨環境可執行 | 雲端登入部署、雲端重啟復原及公開網址驗收 |

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

此階段的 API 測試使用 HTTP mock；後續真實擷取結果見下方紀錄。功能分支與 PR 的雲端 CI 已通過；main 合併後的執行結果以 GitHub Actions 為準。

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

### 2026-10-04：更新 GitHub 主分支

- PR #2 已合併至 `main`，GitHub 首頁直接顯示目前 M2 開發成果。
- 本機 82 項測試、Ruff 與套件建置通過，功能分支／PR CI 通過。
- 私有樣本、API Key、SQLite 與虛擬環境未上傳；真實契約及 live adapter 仍待完成。

## 使用者需要做的事

本機已有真實資料，查詢不需額外設定。公開部署需要使用者登入 Streamlit 並設定雲端 Secrets，詳見本文件最新紀錄及 DEPLOYMENT.md。本機查看指令：

```powershell
cd C:\Users\user\Downloads\Fix\mysoul
uv run --locked weather-data status --mode live --summary --location 臺北市
```

若要再擷取最新預報，執行 `uv run --locked weather-data update-live --prompt-key`，在隱藏提示輸入授權碼。此指令才會連線；`status` 只讀本機。以下保留單獨擷取原始樣本的步驟供診斷使用。

1. 前往 [中央氣象署開放資料平台](https://opendata.cwa.gov.tw/)完成註冊與平台要求的驗證，登入取得 API 授權碼。
2. 在本機 PowerShell 執行：

```powershell
cd C:\Users\user\Downloads\Fix\mysoul
uv run --locked weather-data capture-cwa --prompt-key
```

3. 依提示輸入授權碼；成功顯示 `captured_unverified` 後，告知開發者「已擷取」。若失敗，只需提供錯誤代碼。

本機說明見 [LOCAL_SETUP.md](LOCAL_SETUP.md)；雲端帳號、部署與資料復原見 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 下一步

1. 依 [DEPLOYMENT.md](DEPLOYMENT.md) 登入 Streamlit Community Cloud，使用功能分支與 app.py，設定雲端 secrets。
2. 完成雲端建置、公開網址、重啟／空資料庫復原及實體手機驗收。
3. 取得 CWA 官方溫度缺值定義或真實缺值樣本，繼續補契約依據；目前維持拒絕未知缺值。

## 2026-10-04：本機真實資料管線完成

- 新增獨立 live parser，核對資料集、22 縣市代碼／名稱、最高／最低溫、相同時段集合及連續性。
- 下午樣本每縣市 14 時段，晚間樣本每縣市 15 時段；兩份精簡真實樣本與來源說明已加入測試。原始樣本仍留在 Git 忽略目錄。
- 新增 `update-live`、`import-cwa` 與中文 `status --summary --location`。摘要使用台灣時間並突出 Demo／真實來源。
- 匯入樣本要求原始擷取時間；過期、資料覆蓋倒退、未知缺值及錯誤更新不會覆蓋有效快照，不會退回 Demo。
- 真實網路更新成功：batch 3，22 縣市、330 筆；擷取約台灣時間 2026-10-04 20:21，有效期間 2026-10-04 18:00～2026-10-12 06:00。
- 首次晚間更新因 15 時段被原先 14 時段檢查拒絕，既有 batch 2 保留；核對新樣本並補測試後成功更新，錯誤狀態清除。
- 本機 pytest **106 項通過**，Ruff lint／format 及 sdist／wheel 建置通過；GitHub 同步時另執行雲端 CI。
- 溫度缺值 null／`-`／`-99` 未獲官方語意確認，先拒絕，不能宣稱全部契約已完成。

## 更新方式

每次完成一段實作、取得驗證結果、發現阻礙或需要使用者額外設定時，同步更新本文件。需求驗收勾選維護於 [PLAN.md](PLAN.md)；此處記錄實際進度與證據。明確區分本機／遠端、離線／真實驗證，不以測試全通過代表產品全部完成。

## 2026-10-04：真實資料查詢同步 GitHub

- PR #3 已合併，GitHub `main` 顯示最新真實 CWA 查詢成果。
- 本機 106 項測試、Ruff 與建置通過；[PR 雲端檢查](https://github.com/bogerneal/mysoul/actions/runs/37202726092) 成功。
- API Key、私有原始樣本與 SQLite 未上傳；有來源記錄的精簡天氣測試樣本已納入版本控制。
