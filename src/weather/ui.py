"""Local Streamlit dashboard. All visualizations use one immutable snapshot."""

import os
from datetime import UTC, datetime
from pathlib import Path

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from weather.dashboard import available_dates, summarize
from weather.demo import load_demo_document
from weather.forecast_service import refresh_if_due, update_demo, update_live
from weather.geo import load_points, map_rows
from weather.map_layers import attribution, border_layer, label_layer, map_controls, map_style
from weather.parser import DATASET_ID
from weather.presentation import TAIPEI, local_time, temperature
from weather.repository import ForecastRepository
from weather.update_log import configure_update_logging


def current_time():
    return datetime.now(UTC)


def setting(name, default=""):
    value = os.environ.get(name)
    if value is not None:
        return value.strip()
    try:
        return str(st.secrets.get(name, default)).strip()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default


def api_key():
    return setting("CWA_API_KEY")


def select_map_city(key, codes):
    state = st.session_state.get(key, {})
    selected = state.get("selection", {}).get("objects", {}).get("counties", [])
    if selected and selected[0].get("code") in codes:
        st.session_state.city = selected[0]["code"]


def draw_map(snapshot, day, cities):
    rows, table, missing = map_rows(snapshot, day, cities, load_points())
    st.subheader("同一天，各地溫度（°C）")
    st.caption("點選代表點切換縣市。藍 <20°C · 綠 20–<25°C · 黃 25–<30°C · 紅 ≥30°C · 灰 缺值")
    if missing:
        st.warning("缺少有效座標：" + "、".join(missing) + "；預報仍保留在縣市選單與表格。")
    basemap = map_controls("forecast")
    if not rows:
        st.info("此日期沒有可顯示的地圖座標，請使用下方表格。")
    else:
        try:
            render_map(snapshot, day, cities, rows, basemap)
        except Exception:
            st.warning("地圖暫時無法顯示，請使用縣市選單及下方表格查詢。")
    st.caption("座標：CWA 縣市預報代表點，非測站。底圖無法載入時，可關閉底圖並使用縣市選單與表格。")
    attribution()
    st.dataframe(
        pd.DataFrame(
            [
                {"縣市": r["name"], "最低溫": r["low"], "最高溫": r["high"], "涵蓋": r["coverage"]}
                for r in table
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def render_map(snapshot, day, cities, rows, basemap):
    enabled, theme, borders, labels = basemap
    rows = [{**r, "label": r["high"] + "°"} for r in rows]
    deck = pdk.Deck(
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                rows,
                id="counties",
                get_position="[lon, lat]",
                get_fill_color="color",
                get_radius=8500,
                radius_min_pixels=8,
                radius_max_pixels=22,
                pickable=True,
                stroked=True,
                get_line_color=[255, 255, 255],
                line_width_min_pixels=2,
            )
        ],
        initial_view_state=pdk.ViewState(latitude=23.8, longitude=120.5, zoom=5.5),
        map_provider="carto",
        map_style=map_style(enabled, theme),
        tooltip={"text": "{name}\n最低 {low} / 最高 {high}\n{coverage}"},
    )
    if borders:
        deck.layers.insert(0, border_layer())
    if labels:
        deck.layers.append(label_layer(rows))
    key = f"map_{snapshot.mode}_{snapshot.fetched_at.isoformat()}_{day}_{basemap}"
    st.pydeck_chart(
        deck,
        height=430,
        key=key,
        selection_mode="single-object",
        on_select=lambda: select_map_city(key, cities),
    )


def main():
    configure_update_logging()
    st.set_page_config(page_title="台灣氣象 · mysoul", page_icon="🌤️", layout="wide")
    section = st.segmented_control(
        "功能", ["未來預報", "即時觀測"], default="未來預報", key="section"
    )
    if section == "即時觀測":
        from weather.observation_ui import observation_page

        observation_page(api_key(), setting("WEATHER_AUTO_REFRESH", "false").lower() == "true")
        return
    forecast_page()


def forecast_page():
    st.title("台灣一週天氣")
    st.caption("選一座城市，看看接下來的溫度。｜中央氣象署縣市預報")
    repository = ForecastRepository(Path(os.environ.get("WEATHER_DB", "data/weather.sqlite3")))
    with st.sidebar:
        st.header("查詢設定")
        mode_label = st.radio("資料模式", ["真實天氣", "Demo 示範"], key="mode")
        mode = "live" if mode_label == "真實天氣" else "demo"
        key = api_key() if mode == "live" else ""
        automatic = setting("WEATHER_AUTO_REFRESH", "false").lower() == "true"
        if key and automatic:
            try:
                with st.spinner("正在檢查預報更新…"):
                    refresh_if_due(repository, key, now=current_time())
            except Exception:
                st.warning("自動更新未成功，保留最後成功資料；稍後會再次嘗試。")
        if mode == "live" and not key:
            st.info("可查看本機已有資料。更新天氣需設定 CWA_API_KEY，詳見 docs/LOCAL_SETUP.md。")
        if st.button(
            "更新真實天氣" if mode == "live" else "載入示範資料",
            disabled=mode == "live" and not key,
            width="stretch",
        ):
            try:
                with st.spinner("正在取得並驗證資料…"):
                    if mode == "live":
                        update_live(repository, key, cooldown_seconds=60)
                    else:
                        update_demo(repository, load_demo_document())
                st.success("資料已更新。")
            except Exception:
                st.error(
                    "未能更新：請確認金鑰、網路，或稍後再試（更新間隔至少 60 秒）。原資料仍保留。"
                )
        st.caption(
            "自動更新：開啟或操作頁面時每 30 分鐘檢查一次；其餘時間使用已保存資料。"
            if automatic and mode == "live"
            else "篩選與切換圖表不會重新呼叫 API。"
        )
    now = current_time()
    stored = repository.read(DATASET_ID, mode, now=now)
    snapshot = stored.snapshot
    if mode == "demo":
        st.warning("Demo：合成示範資料，固定日期為 2026/12/31–2027/01/01，並非目前的真實預報。")
    if snapshot is None:
        st.info("尚無資料。請在左側載入示範資料，或設定 API Key 後更新真實天氣。")
        return
    if mode == "live" and stored.stale:
        st.warning("資料已超過 6 小時未成功更新，或預報已到期。下方保留最後成功資料，請先更新。")
    if stored.last_error_code:
        st.warning("上次更新失敗，目前顯示最後成功保存的資料。")
    st.caption(
        f"{'CWA 真實預報' if mode == 'live' else '合成示範'} · 批次 {stored.batch_id} · "
        f"資料取得 {local_time(snapshot.fetched_at)} · "
        f"最後成功檢查 {local_time(stored.last_success_at)} · 台灣時間 UTC+8"
    )
    st.caption(f"來源發布時間：{local_time(snapshot.source_issued_at)} · 資料集 {DATASET_ID}")
    cities = {p.location_code: p.location_name for p in snapshot.periods}
    if st.session_state.get("city") not in cities:
        st.session_state.city = "63000000" if "63000000" in cities else next(iter(cities))
    with st.sidebar:
        code = st.selectbox("縣市", list(cities), format_func=cities.get, key="city")
        days = available_dates(snapshot, code, now.astimezone(TAIPEI).date())
        if not days:
            st.warning("沒有今天起可用的預報日期，請更新資料。")
            st.info(f"最後涵蓋至 {local_time(max(p.end_at for p in snapshot.periods))}")
            return
        if st.session_state.get("day") not in days:
            st.session_state.day = days[0]
        day = st.selectbox("預報日期", days, key="day", format_func=lambda d: d.isoformat())
    summary = summarize(snapshot, code, day)
    st.subheader(f"{cities[code]} · {day:%Y/%m/%d}")
    low, high, coverage = st.columns(3)
    low.metric("最低溫（°C）", temperature(summary.low))
    high.metric("最高溫（°C）", temperature(summary.high))
    coverage.metric("時段涵蓋", "部分時段" if summary.partial else "全天")
    if summary.missing:
        st.warning("部分時段溫度缺值；摘要只彙整已知值，請查看時段表格。")
    st.caption("彙整與當天有交集的預報時段；跨日時段可能影響相鄰兩日，非逐時計算的精確日極值。")
    trend = pd.DataFrame(
        [
            {"日期": str(d), "溫度": value, "類型": label}
            for d in days
            for daily in [summarize(snapshot, code, d)]
            for label, value in [("最低溫", daily.low), ("最高溫", daily.high)]
        ]
    )
    chart = (
        alt.Chart(trend)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "日期:O",
                sort=[str(d) for d in days],
                axis=alt.Axis(labelAngle=-30, labelExpr="slice(datum.label, 5)"),
            ),
            y=alt.Y("溫度:Q", title="溫度 (°C)", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "類型:N",
                legend=alt.Legend(orient="top"),
                scale=alt.Scale(domain=["最低溫", "最高溫"], range=["#2396b6", "#e7794b"]),
            ),
            tooltip=["日期:O", "類型:N", "溫度:Q"],
        )
        .properties(height=270)
    )
    st.altair_chart(chart, width="stretch")
    st.subheader("當日預報時段（溫度 °C）")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "縣市": p.location_name,
                    "開始（台灣時間）": local_time(p.start_at),
                    "結束（不含）": local_time(p.end_at),
                    "最低溫": temperature(p.min_temp_c),
                    "最高溫": temperature(p.max_temp_c),
                }
                for p in summary.periods
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    draw_map(snapshot, day, cities)
