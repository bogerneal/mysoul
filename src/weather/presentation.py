"""Human-readable CLI output in Taiwan's UTC+08:00 forecast timezone."""

from datetime import datetime, timedelta, timezone

from weather.repository import StoredForecast

TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")


def local_time(value: datetime | str | None) -> str:
    if value is None:
        return "未提供"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M")


def temperature(value: float | None) -> str:
    return "缺值" if value is None else f"{value:g}"


def summarize(state: StoredForecast, mode: str, location: str | None = None) -> str:
    lines = [
        "【DEMO 合成資料：固定測試日期，並非真實天氣】"
        if mode == "demo"
        else "【CWA 真實預報：本機儲存快照，查詢不會自動更新】",
        "時間顯示：台灣時間 UTC+08:00",
    ]
    if state.snapshot is None:
        lines.append("目前沒有資料。請先執行 update-demo 或 update-live／import-cwa。")
    else:
        snapshot = state.snapshot
        county_count = len({p.location_code for p in snapshot.periods})
        lines.extend(
            [
                f"批次：{state.batch_id}；縣市：{county_count}；"
                f"總時段筆數：{len(snapshot.periods)}",
                f"原始擷取／Demo 載入：{local_time(snapshot.fetched_at)}",
                f"最後成功擷取／匯入所保留的時間：{local_time(state.last_success_at)}",
                f"來源發布時間：{local_time(snapshot.source_issued_at)}",
                f"有效期間：{local_time(min(p.start_at for p in snapshot.periods))} ～ "
                f"{local_time(max(p.end_at for p in snapshot.periods))}",
                "資料狀態：可能過期" if state.stale else "資料狀態：未達過期門檻",
            ]
        )
        selected = [
            p
            for p in snapshot.periods
            if location is None
            or location in {p.location_code, p.location_name, p.location_name.replace("臺", "台")}
        ]
        if not selected:
            lines.append("找不到符合的縣市，未沿用其他縣市資料。")
        else:
            lines.append("縣市 | 預報開始 | 預報結束 | 最低 °C | 最高 °C")
            lines.extend(
                f"{p.location_name} | {local_time(p.start_at)} | {local_time(p.end_at)} | "
                f"{temperature(p.min_temp_c)} | {temperature(p.max_temp_c)}"
                for p in selected
            )
    if state.last_error_code:
        lines.append(f"最近更新失敗：{state.last_error_code}；既有成功快照保留。")
    return "\n".join(lines)
