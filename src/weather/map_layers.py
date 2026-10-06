"""Shared raster basemaps and bundled county boundaries, with no API credentials."""

import json
from functools import lru_cache
from importlib.resources import files
from urllib.parse import quote

import pydeck as pdk
import streamlit as st


def map_controls(prefix):
    enabled = st.checkbox("顯示網路底圖", True, key=f"{prefix}_base")
    theme = st.segmented_control(
        "底圖樣式", ["深色", "街道"], default="深色", key=f"{prefix}_theme"
    )
    borders = st.checkbox("縣市界線", True, key=f"{prefix}_borders")
    labels = st.checkbox("數字標籤", True, key=f"{prefix}_labels")
    return enabled, theme, borders, labels


def map_style(enabled=True, theme="深色"):
    style = {"version": 8, "sources": {}, "layers": []}
    if enabled:
        style["sources"]["osm"] = {
            "type": "raster",
            "tileSize": 256,
            "tiles": ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            "attribution": (
                '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            ),
            "maxzoom": 19,
        }
        paint = {"raster-saturation": -1, "raster-brightness-max": 0.45} if theme == "深色" else {}
        style["layers"] = [{"id": "base", "type": "raster", "source": "osm", "paint": paint}]
    return "data:application/json," + quote(json.dumps(style))


@lru_cache(maxsize=1)
def boundaries():
    return json.loads(
        files("weather").joinpath("fixtures/taiwan_counties.geojson").read_text("utf-8")
    )


def border_layer():
    return pdk.Layer(
        "GeoJsonLayer",
        boundaries(),
        id="county-borders",
        filled=False,
        stroked=True,
        get_line_color=[118, 157, 174],
        get_line_width=1,
        line_width_units=pdk.types.String("pixels"),
        line_width_min_pixels=1,
        pickable=False,
    )


def label_layer(rows, field="label"):
    return pdk.Layer(
        "TextLayer",
        rows,
        id="value-labels",
        get_position="[lon, lat]",
        get_text=field,
        get_size=13,
        get_color=[255, 255, 255],
        get_pixel_offset=[0, -15],
        background=True,
        get_background_color=[20, 30, 45, 220],
        background_padding=[3, 2],
        character_set=pdk.types.String("auto"),
        pickable=False,
    )


def attribution():
    st.caption(
        "資料：中央氣象署｜底圖：© OpenStreetMap contributors（深色為灰階調暗）｜"
        "縣市界線：內政部圖資衍生 taiwan-atlas 2021.9.20（概略展示用）"
    )
