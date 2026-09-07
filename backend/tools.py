"""Agentに渡すツール定義。"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from strands import tool

_CHART_TEMPLATE = (Path(__file__).parent / "templates" / "chart.html").read_text()

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
