"""Agentに渡すツール定義。"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from strands import tool

_CHART_TEMPLATE = (Path(__file__).parent / "templates" / "chart.html").read_text()
_MAP_TEMPLATE = (Path(__file__).parent / "templates" / "map.html").read_text()
_PREFECTURES_GEOJSON = (
    Path(__file__).parent / "data" / "japan_prefectures.geojson"
).read_text()
_PREFECTURE_POINTS: dict[str, list[float]] = json.loads(
    (Path(__file__).parent / "data" / "prefecture_points.json").read_text()
)

_MAP_NAME = "japan-prefectures"
_LINE_WIDTH_RANGE = (1.0, 12.0)

# 系列カラー未指定時のデフォルト配色
_DEFAULT_SERIES_COLORS = [
    "#0081cf",  # 青
    "#eb6834",  # オレンジ
    "#1baf7a",  # アクア
    "#eda100",  # 黄
    "#e87ba4",  # マゼンタ
    "#008300",  # 緑
    "#4a3aa7",  # 紫
    "#e34948",  # 赤
]


class ChartPoint(BaseModel):
    """散布図の1点。"""

    x: float
    y: float


class ChartSeries(BaseModel):
    """1本分のデータ系列。"""

    name: str | None = None
    color: str | None = Field(
        default=None,
        description="ユーザーが明示的に色を指定した場合のみ設定すること。指定がなければデフォルト配色が使われる。",
    )
    values: list[float | None] | None = None
    points: list[ChartPoint] | None = None


class ChartAxis(BaseModel):
    """軸の設定。"""

    title: str | None = None
    data: list[str] | None = None


@tool
def render_chart(
    style: Literal["line", "bar", "scatter", "pie"],
    series: list[ChartSeries],
    title: str | None = None,
    x_axis: ChartAxis | None = None,
    y_axis: ChartAxis | None = None,
) -> str:
    """数値系列データをChart.jsでグラフ化したHTMLを生成する。"""
    # strandsは引数を生のdictで渡すため、Pydanticモデルへ明示的に変換する。
    series = [ChartSeries.model_validate(s) for s in series]
    x_axis = ChartAxis.model_validate(x_axis) if x_axis else None
    y_axis = ChartAxis.model_validate(y_axis) if y_axis else None

    labels = x_axis.data if x_axis else None
    datasets = []
    for i, s in enumerate(series):
        if style == "scatter":
            data = [{"x": p.x, "y": p.y} for p in (s.points or [])]
        else:
            data = s.values or []

        if style == "pie":
            # 円グラフはスライスごとに色分けするため、要素ごとに配色を割り当てる
            color = [
                s.color or _DEFAULT_SERIES_COLORS[j % len(_DEFAULT_SERIES_COLORS)]
                for j in range(len(data))
            ]
        else:
            color = s.color or _DEFAULT_SERIES_COLORS[i % len(_DEFAULT_SERIES_COLORS)]

        datasets.append(
            {
                "label": s.name,
                "data": data,
                "borderColor": color,
                "backgroundColor": color,
            }
        )

    options = {
        "maintainAspectRatio": False,
        "plugins": {"title": {"display": bool(title), "text": title}},
    }
    if style != "pie":
        # 円グラフには直交座標軸が存在しないため、scalesはpie以外にのみ付与する
        options["scales"] = {
            "x": {
                "title": {
                    "display": bool(x_axis and x_axis.title),
                    "text": x_axis.title if x_axis else None,
                }
            },
            "y": {
                "title": {
                    "display": bool(y_axis and y_axis.title),
                    "text": y_axis.title if y_axis else None,
                }
            },
        }

    config = {
        "type": style,
        "data": {"labels": labels, "datasets": datasets},
        "options": options,
    }

    return _CHART_TEMPLATE.replace("{{chart_config}}", json.dumps(config))


class MapPoint(BaseModel):
    """地図上の1地点(都道府県名で指定)。"""

    prefecture: str  # 都道府県名(例: "東京都")。47都道府県の名称と完全一致させる
    value: float | None = None  # 塗り分けの濃淡、および流動線の太さに使う数値


@tool
def render_choropleth(points: list[MapPoint]) -> str:
    """都道府県単位の数値を地図上に塗り分け表示する。"""
    points = [MapPoint.model_validate(p) for p in points]
    _validate_map_points(points)

    values = [p.value for p in points if p.value is not None]
    value_min = min(values) if values else 0.0
    value_max = max(values) if values else 0.0

    option = {
        "tooltip": {},
        "visualMap": {
            "show": False,
            "min": value_min,
            "max": value_max,
            "inRange": {"color": ["#eef6ff", _DEFAULT_SERIES_COLORS[0]]},
        },
        "geo": _base_geo(),
        "series": [
            {
                "type": "map",
                "map": _MAP_NAME,
                "geoIndex": 0,
                "tooltip": {"formatter": "{b}　{c}"},
                "data": [{"name": p.prefecture, "value": p.value} for p in points],
                "label": {"show": False},
                "emphasis": {"label": {"show": False}},
            }
        ],
    }

    return _render_map_html(option)


@tool
def render_spider(origin: str, points: list[MapPoint]) -> str:
    """起点となる都道府県から、各都道府県への流動線を地図上に描く。線の太さは値に比例する。"""
    points = [MapPoint.model_validate(p) for p in points]
    _validate_map_points(points)
    if origin not in _PREFECTURE_POINTS:
        raise ValueError(f"未知の都道府県名です: {origin}")

    values = [p.value for p in points if p.value is not None]
    value_min = min(values) if values else 0.0
    value_max = max(values) if values else 0.0
    origin_coord = _PREFECTURE_POINTS[origin]

    dest_points = [p for p in points if p.prefecture != origin]

    option = {
        "tooltip": {},
        "geo": _base_geo(),
        "series": [
            {
                "type": "lines",
                "coordinateSystem": "geo",
                "tooltip": {"formatter": "{b}　{c}"},
                "lineStyle": {
                    "color": _DEFAULT_SERIES_COLORS[1],
                    "opacity": 0.6,
                    "curveness": 0.2,
                },
                "emphasis": {"focus": "self"},
                "blur": {"lineStyle": {"opacity": 0.1}},
                "data": [
                    {
                        "name": p.prefecture,
                        "value": p.value,
                        "coords": [origin_coord, _PREFECTURE_POINTS[p.prefecture]],
                        "lineStyle": {
                            "width": _scale_line_width(p.value, value_min, value_max)
                        },
                    }
                    for p in dest_points
                ],
            },
            # ポリゴンホバー時に線と同じ値入り吹き出しを出すための透明な当たり判定レイヤー
            {
                "type": "map",
                "map": _MAP_NAME,
                "geoIndex": 0,
                "tooltip": {"formatter": "{b}　{c}"},
                "data": [{"name": p.prefecture, "value": p.value} for p in dest_points],
                "itemStyle": {"color": "transparent", "borderWidth": 0},
                "label": {"show": False},
                "emphasis": {"label": {"show": False}, "itemStyle": {"color": "transparent"}},
            },
        ],
    }

    return _render_map_html(option)


def _validate_map_points(points: list[MapPoint]) -> None:
    """MapPointのリストが空でなく、すべて既知の都道府県名かを検証する。"""
    if not points:
        raise ValueError("pointsが空です")
    for point in points:
        if point.prefecture not in _PREFECTURE_POINTS:
            raise ValueError(f"未知の都道府県名です: {point.prefecture}")


def _base_geo() -> dict:
    """都道府県地図のgeoコンポーネント設定(全ツール共通)。

    離島(南鳥島・沖ノ鳥島など)まで自動フィット範囲に含まれると本州が
    小さく表示されてしまうため、centerとzoomで本土がほぼ収まる範囲に
    初期表示を固定する(roam: trueなのでユーザー側でさらに調整可能)。
    """
    return {
        "map": _MAP_NAME,
        "roam": True,
        "center": [137, 37.5],
        "zoom": 1.6,
        "label": {"show": False},
        "emphasis": {"label": {"show": False}},
    }


def _render_map_html(option: dict) -> str:
    """EChartsのoptionをmapテンプレートに埋め込みHTML文字列にする。"""
    html = _MAP_TEMPLATE.replace("{{prefectures_geojson}}", _PREFECTURES_GEOJSON)
    return html.replace("{{map_config}}", json.dumps(option))


def _scale_line_width(value: float | None, value_min: float, value_max: float) -> float:
    """値をmin-maxで線幅にスケーリングする。"""
    width_min, width_max = _LINE_WIDTH_RANGE
    if value is None or value_max <= value_min:
        return width_min
    ratio = (value - value_min) / (value_max - value_min)
    return width_min + ratio * (width_max - width_min)
