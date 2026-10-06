"""Station observations are never presented as county forecasts or interpolated fields."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from weather.geo import load_points
from weather.map_layers import attribution, border_layer, label_layer, map_controls, map_style
from weather.observations import DATASET, ObservationStore, fresh_rows
from weather.presentation import local_time

FIELDS = {
    "氣溫": ("temperature", "°C", -5, 40),
    "當日累積雨量": ("rain", "mm", 0, 100),
    "風速風向": ("wind", "m/s", 0, 20),
    "濕度": ("humidity", "%", 0, 100),
}


def display(value):
    return "—" if value is None else f"{value:g}"


def station_table(rows):
    return pd.DataFrame(
        [
            {
                "測站": r["name"],
                "代碼": r["id"],
                "縣市": r["county"],
                "鄉鎮": r["town"],
                "觀測時間（台灣）": local_time(datetime.fromisoformat(r["time"])),
                "氣溫 °C": r["temperature"],
                "當日雨量 mm": r["rain"],
                "雨量註記": r["rain_note"],
                "風速 m/s": r["wind"],
                "風向 °（來向）": r["direction"],
                "濕度 %": r["humidity"],
                "天氣": r["weather"],
                "緯度": r["lat"],
                "經度": r["lon"],
                "海拔 m": r["altitude"],
            }
            for r in rows
        ]
    )


def map_rows(rows, field, unit, low, high):
    result = []
    for r in rows:
        if r["lon"] is None or r["lat"] is None:
            continue
        value = r[field]
        ratio = 0 if value is None else max(0, min(1, (value - low) / (high - low)))
        color = (
            [140, 150, 160]
            if value is None
            else [int(40 + 210 * ratio), int(170 - 80 * ratio), int(230 - 180 * ratio)]
        )
        note = r["rain_note"] if field == "rain" else ""
        label = note or (display(value) + unit if value is not None else "缺值")
        result.append(
            {
                **r,
                "label": label,
                "color": color,
                "observed": local_time(datetime.fromisoformat(r["time"])),
                "arrow": "↑",
                "angle": 180 - (r["direction"] or 0),
                "wind_text": display(r["direction"]) + "°（來向）",
            }
        )
    return result


def station_selected(map_key, ids):
    objects = st.session_state.get(map_key, {}).get("selection", {}).get("objects", {})
    chosen = objects.get("stations", [])
    if chosen and chosen[0].get("id") in ids:
        st.session_state.obs_station = chosen[0]["id"]


def representative_labels(markers, field):
    """One real station nearest each county reference point; never an interpolated value."""
    points = {p["name"]: p for p in load_points()}
    labels = []
    for county in sorted({r["county"] for r in markers}):
        stations = [r for r in markers if r["county"] == county]
        valid = [r for r in stations if r[field] is not None]
        point = points.get(county, stations[0])
        labels.append(
            min(
                valid or stations,
                key=lambda r: (r["lat"] - point["lat"]) ** 2 + (r["lon"] - point["lon"]) ** 2,
            )
        )
    return labels


def observation_page(key, automatic):
    st.title("台灣即時氣象觀測")
    st.caption("測站最新觀測，並非未來預報。雨量為台灣時間當日累積；風向為風的來向。")
    path = Path(os.environ.get("WEATHER_DB", "data/weather.sqlite3"))
    store = ObservationStore(path.with_name(path.stem + "_observations.sqlite3"))
    now = datetime.now(UTC)
    with st.sidebar:
        st.header("觀測設定")
        manual = st.button("更新即時觀測", disabled=not key, width="stretch")
        if key and (manual or automatic):
            try:
                with st.spinner("檢查測站觀測…"):
                    changed = store.update(key, automatic=not manual, now=now)
                if manual:
                    st.success("觀測已更新。") if changed else st.info(
                        "更新間隔至少 60 秒，沿用目前資料。"
                    )
            except Exception:
                st.error("觀測更新失敗，保留最後成功資料；請稍後再試或確認 API 授權。")
        if not key:
            st.info("尚未設定觀測更新授權，可查看已保存的觀測資料。")
        st.caption(
            "自動更新：開啟／操作本頁時每 10 分鐘檢查一次。"
            if automatic
            else "自動更新未啟用，請按更新取得觀測。"
        )
    snapshot = store.read()
    rows = snapshot["rows"]
    if not rows:
        st.info("尚無即時觀測資料。請按「更新即時觀測」；預報資料仍可在「未來預報」查詢。")
        return
    fresh = fresh_rows(rows, now)
    fresh_ids = {r["id"] for r in fresh}
    if snapshot["failed"]:
        st.warning("上次觀測更新失敗，以下為最後成功快照。")
    st.caption(
        f"來源：CWA {DATASET} · 取得時間 {local_time(snapshot['fetched'])} · "
        f"{len(rows)} 個測站 · 近一小時有效觀測 {len(fresh)} 站"
    )
    if len(fresh) != len(rows):
        st.warning(
            f"{len(rows) - len(fresh)} 站超過一小時或時間異常，不納入全台統計；仍可查閱明細。"
        )
    st.subheader("全台有效測站統計")
    columns = st.columns(4)
    for column, title, field, unit, choose in zip(
        columns,
        ["最高氣溫", "最低氣溫", "最大當日雨量", "最大平均風速"],
        ["temperature", "temperature", "rain", "wind"],
        ["°C", "°C", "mm", "m/s"],
        [max, min, max, max],
        strict=True,
    ):
        valid = [r for r in fresh if r[field] is not None]
        record = choose(valid, key=lambda r: r[field]) if valid else None
        column.metric(title, display(record[field]) + " " + unit if record else "—")
        if record:
            column.caption(
                f"{record['name']} · {record['id']} · "
                f"{local_time(datetime.fromisoformat(record['time']))}（有效 {len(valid)} 站）"
            )
    st.caption("比較本資料集近一小時各測站最新值；氣溫高低不是今日歷史極值。缺值／雨跡不當作 0。")
    with st.sidebar:
        layer = st.radio("觀測圖層", list(FIELDS), key="obs_layer")
        county = st.selectbox(
            "觀測縣市", ["全部縣市"] + sorted({r["county"] for r in rows}), key="obs_county"
        )
        include_stale = st.checkbox("包含過期觀測", False, key="obs_stale")
        controls = map_controls("observation")
        all_labels = st.checkbox("全部測站數字（可能重疊）", False, key="obs_all_labels")
    filtered = [
        r
        for r in rows
        if (county == "全部縣市" or r["county"] == county)
        and (include_stale or r["id"] in fresh_ids)
    ]
    if not filtered:
        st.info("目前篩選沒有有效測站，勾選「包含過期觀測」可查最後保存值。")
        return
    field, unit, low, high = FIELDS[layer]
    markers = map_rows(filtered, field, unit, low, high)
    st.subheader(f"{layer} · {county}")
    st.caption(
        f"藍 → 紅：{low}～{high} {unit}（超出範圍沿用端點顏色）；灰色為缺值。"
        "數字顯示原值，點選測站查看明細。" + ("箭頭表示風吹往的方向。" if field == "wind" else "")
    )
    if len(markers) < len(filtered):
        st.warning("部分測站缺少 WGS84 座標，保留於選單與表格。")
    enabled, theme, borders, labels = controls
    layers = [border_layer()] if borders else []
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            markers,
            id="stations",
            get_position="[lon, lat]",
            get_fill_color="color",
            get_radius=1800,
            radius_min_pixels=5,
            radius_max_pixels=12,
            pickable=True,
        )
    )
    if labels:
        layers.append(label_layer(markers if all_labels else representative_labels(markers, field)))
        st.caption(
            "數字預設每縣市選最接近縣市代表點的一個有效測站，並非縣市平均；"
            "其他站可點選，或勾選全部測站數字。"
        )
    if field == "wind":
        arrows = [r for r in markers if r["direction"] is not None and r["wind"] not in (None, 0)]
        layers.append(
            pdk.Layer(
                "TextLayer",
                arrows,
                id="wind-arrows",
                get_position="[lon, lat]",
                get_text="arrow",
                get_angle="angle",
                get_size=25,
                get_color=[255, 255, 255],
                character_set=pdk.types.String("auto"),
            )
        )
    map_key = (
        f"obs_map_{snapshot['fetched'].isoformat()}_{layer}_{county}_{controls}_{include_stale}"
    )
    ids = {r["id"] for r in filtered}
    try:
        st.pydeck_chart(
            pdk.Deck(
                layers=layers,
                initial_view_state=pdk.ViewState(latitude=23.8, longitude=120.5, zoom=6),
                map_provider="carto",
                map_style=map_style(enabled, theme),
                tooltip={"text": "{name} · {id}\n{label}\n{observed}\n風向 {wind_text}"},
            ),
            height=580,
            key=map_key,
            selection_mode="single-object",
            on_select=lambda: station_selected(map_key, ids),
        )
    except Exception:
        st.warning("地圖暫時無法顯示，請使用下方測站選單與表格。")
    attribution()
    by_id = {r["id"]: r for r in filtered}
    if st.session_state.get("obs_station") not in by_id:
        st.session_state.obs_station = next(iter(by_id))
    selected = st.selectbox(
        "測站明細",
        list(by_id),
        key="obs_station",
        format_func=lambda identity: f"{by_id[identity]['name']} · {identity}",
    )
    st.dataframe(station_table([by_id[selected]]), hide_index=True, width="stretch")
    st.subheader(f"測站列表（{len(filtered)} 站）")
    st.dataframe(station_table(filtered), hide_index=True, width="stretch")
