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
def render_map(
    points: list[MapPoint],
    origin: str | None = None,
    title: str | None = None,
) -> str:
    """都道府県単位の数値を地図上に塗り分け表示する。originを指定すると流動線も重ねて表示する。"""
    # strandsは引数を生のdictで渡すため、Pydanticモデルへ明示的に変換する。
    points = [MapPoint.model_validate(p) for p in points]

    for point in points:
        if point.prefecture not in _PREFECTURE_POINTS:
            raise ValueError(f"未知の都道府県名です: {point.prefecture}")
    if origin is not None and origin not in _PREFECTURE_POINTS:
        raise ValueError(f"未知の都道府県名です: {origin}")

    values = [p.value for p in points if p.value is not None]
    value_min = min(values) if values else 0.0
    value_max = max(values) if values else 0.0

    map_series: dict = {
        "name": "塗り分け",
        "type": "map",
        "map": _MAP_NAME,
        "data": [{"name": p.prefecture, "value": p.value} for p in points],
    }
    series = [map_series]
    geo = None

    if origin is not None:
        geo = {"map": _MAP_NAME, "roam": False}
        map_series["geoIndex"] = 0
        origin_coord = _PREFECTURE_POINTS[origin]
        series.append(
            {
                "name": "流動線",
                "type": "lines",
                "coordinateSystem": "geo",
                "lineStyle": {
                    "color": _DEFAULT_SERIES_COLORS[1],
                    "opacity": 0.6,
                    "curveness": 0.2,
                },
                "data": [
                    {
                        "coords": [origin_coord, _PREFECTURE_POINTS[p.prefecture]],
                        "lineStyle": {
                            "width": _scale_line_width(p.value, value_min, value_max)
                        },
                    }
                    for p in points
                ],
            }
        )

    option = {
        "title": {"text": title} if title else {},
        "tooltip": {},
        "legend": {"data": [s["name"] for s in series]},
        "visualMap": {
            "min": value_min,
            "max": value_max,
            "calculable": True,
            "inRange": {"color": ["#eef6ff", _DEFAULT_SERIES_COLORS[0]]},
        },
        "series": series,
    }
    if geo is not None:
        option["geo"] = geo

    html = _MAP_TEMPLATE.replace("{{prefectures_geojson}}", _PREFECTURES_GEOJSON)
    return html.replace("{{map_config}}", json.dumps(option))


def _scale_line_width(value: float | None, value_min: float, value_max: float) -> float:
    """値をmin-maxで線幅にスケーリングする。"""
    width_min, width_max = _LINE_WIDTH_RANGE
    if value is None or value_max <= value_min:
        return width_min
    ratio = (value - value_min) / (value_max - value_min)
    return width_min + ratio * (width_max - width_min)
