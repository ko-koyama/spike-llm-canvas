"""Agentに渡すツール定義。"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from strands import tool

_CHART_TEMPLATE = (Path(__file__).parent / "templates" / "chart.html").read_text()


class ChartPoint(BaseModel):
    """散布図の1点。"""

    x: float
    y: float


class ChartSeries(BaseModel):
    """1本分のデータ系列。"""

    name: str | None = None
    color: str | None = None
    values: list[float] | None = None
    points: list[ChartPoint] | None = None


class ChartAxis(BaseModel):
    """軸の設定。"""

    title: str | None = None
    data: list[str] | None = None


@tool
def render_chart(
    style: Literal["line", "bar", "scatter"],
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
    for s in series:
        if style == "scatter":
            data = [{"x": p.x, "y": p.y} for p in (s.points or [])]
        else:
            data = s.values or []
        datasets.append(
            {
                "label": s.name,
                "data": data,
                "borderColor": s.color,
                "backgroundColor": s.color,
            }
        )

    config = {
        "type": style,
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "maintainAspectRatio": False,
            "plugins": {"title": {"display": bool(title), "text": title}},
            "scales": {
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
            },
        },
    }

    return _CHART_TEMPLATE.replace("{{chart_config}}", json.dumps(config))
