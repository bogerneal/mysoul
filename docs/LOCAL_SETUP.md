# 本機開發與 CWA 設定

本機路徑：`C:\Users\user\Downloads\Fix\mysoul`。使用 PowerShell，先切換到專案目錄：

```powershell
cd C:\Users\user\Downloads\Fix\mysoul
uv sync --locked
```

## 開啟互動網頁

```powershell
uv run --locked streamlit run app.py --server.address 127.0.0.1
```

瀏覽 <http://localhost:8501>，或在套件安裝完成後雙擊 `start-dashboard.cmd`。
左側選「Demo 示範」再按「載入示範資料」；真實模式可查看現有資料庫，不需重新輸入 Key。
關閉終端會停止服務；下次重新執行即可，SQLite 內容會保留。預設不開放其他電腦連線。

如果想先更新資料、再看網頁，另開 PowerShell 執行：

```powershell
uv run --locked weather-data update-live --prompt-key
```

若要使用網頁「更新真實天氣」按鈕，先在啟動網頁的同一個 PowerShell 執行下列安全輸入，
再執行 `streamlit run` 指令（Key 不寫進命令歷史）：

```powershell
$cwaSecure = Read-Host 'CWA API Key' -AsSecureString
$env:CWA_API_KEY = [System.Net.NetworkCredential]::new('', $cwaSecure).Password
uv run --locked streamlit run app.py --server.address 127.0.0.1
Remove-Item Env:CWA_API_KEY
```

也支援被 Git 忽略的 `.streamlit/secrets.toml` 內 `CWA_API_KEY` 設定。
金鑰只在伺服器端讀取；沒有金鑰時更新按鈕停用。每個資料庫在同一程序內限制 60 秒一次更新，
程式重啟會重置冷卻；多程序部署前需要外部協調。改縣市／日期不會呼叫 API。
`WEATHER_DB` 可指定其他 SQLite 路徑；預設 `data/weather.sqlite3`，相對於啟動目錄。

## 不需要帳號的資料庫示範

```powershell
uv run --locked weather-data update-demo
uv run --locked weather-data status --mode demo
```

第一次會建立 `data/weather.sqlite3` 與版本 1 資料表。重複匯入相同資料會沿用 batch ID，更新成功檢查時間。資料庫保留目前與前一次成功快照；中途失敗回滾，舊資料仍可讀。模式隔離，不會將 Demo 當成真實資料。

`status` 輸出完整快照、最後檢查與成功時間、安全錯誤碼及 `stale`。超過六小時沒有成功確認，或全部預報時段已結束，會標成過期。範例日期固定，因此 Demo 並非當前天氣。原本的 `weather-demo` 仍只輸出 JSON，不建立資料庫。

## 你需要做的額外設定：申請 CWA API 授權碼

1. 開啟 [中央氣象署開放資料平台](https://opendata.cwa.gov.tw/)，完成帳號註冊及平台要求的驗證。
2. 登入平台，從會員／API 授權相關頁面取得個人 API 授權碼；畫面名稱以平台當前介面為準。
3. 在專案目錄執行以下指令，於隱藏輸入提示貼上授權碼並按 Enter。輸入時畫面不顯示字元是正常現象。

```powershell
uv run --locked weather-data capture-cwa --prompt-key
```

授權碼只在這次程式記憶體中使用，不寫入腳本、命令歷史或設定檔。後續請透過本機隱藏輸入或雲端 Secrets 設定，不放入 GitHub 或測試檔。若已在執行程序環境中設定 `CWA_API_KEY`，可省略 `--prompt-key`；程式不自動載入 `.env`。

成功會顯示 `captured_unverified`，回應儲存在 `data/private/cwa-<UTC時間>.json`，此資料夾已被 Git 排除。這是待檢查的原始樣本，不會匯入 live 資料庫。取得樣本後告知開發者「已擷取」，即可在本機核對 schema、縣市、缺值與時段覆蓋，再實作 live adapter。未知格式不會自動猜測或切換成 Demo。

常見錯誤：

| 代碼 | 需要的動作 |
| --- | --- |
| `api_key_required` | 加上 `--prompt-key`，輸入授權碼 |
| `authorization_failed` | 回平台確認授權碼是否正確、有效 |
| `rate_limited`／`retry_after_too_long` | 稍後再試，避免連續執行 |
| `timeout`／`connection_failed` | 確認網路可連線至 CWA，再重試 |
| `tls_verification_failed` | 檢查 Windows 日期時間與受信任憑證；不要關閉 HTTPS 驗證 |
| `invalid_json`／`unexpected_response`／`api_rejected` | 保留錯誤代碼供開發者檢查，不代表資料契約驗收成功 |

HTTP client 使用連線 5 秒／讀取 20 秒逾時、最多 3 次請求、最多 30 秒重試等待；若伺服器要求更長等待，直接停止而不提前重試。Requests 的讀取逾時是等待資料的逾時，並非整次下載的硬性總秒數。

HTTP client 使用 truststore 的系統憑證儲存區，保留憑證及主機名稱驗證。2026-10-04 已在本機成功擷取真實樣本（22 縣市），並完成 live adapter；官方溫度缺值語意等完整契約仍待核對。

**後續進度：已完成獨立 live adapter 與本機真實更新／查詢。** 上述 `capture-cwa` 保留作為原始樣本診斷工具，不會自行匯入資料庫；日常更新改用：

```powershell
uv run --locked weather-data update-live --prompt-key
uv run --locked weather-data status --mode live --summary --location 臺北市
```

現有電腦已匯入真實資料，可直接執行第二行。新電腦須先更新或用 `import-cwa --file ... --fetched-at ...` 匯入有原始擷取時間的樣本。完整規則見 [LIVE_CONTRACT.md](LIVE_CONTRACT.md)。授權碼不持久保存；網頁介面已完成，見本文件開頭。

## 開發驗證

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build
```

測試使用合成資料與 HTTP mock，不會呼叫真實 CWA 或需要 Key。Streamlit 本機介面已可使用；公開部署設定見 [DEPLOYMENT.md](DEPLOYMENT.md)。

依據：[CWA API 說明](https://opendata.cwa.gov.tw/dist/opendata-swagger.html)、[Requests 逾時與錯誤說明](https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts)。
