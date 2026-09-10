"""Agentに渡すツール定義。"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, Field
from strands import tool

from storage import upload_html

_CHART_TEMPLATE = (Path(__file__).parent / "templates" / "chart.html").read_text()
_MAP_TEMPLATE = (Path(__file__).parent / "templates" / "map_leaflet.html").read_text()
LevelName = Literal["prefecture", "municipality", "town"]

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

    html = _CHART_TEMPLATE.replace("{{chart_config}}", json.dumps(config))
    return upload_html(html)


class MapPoint(BaseModel):
    """地図上の1地点。"""

    prefecture: str  # 都道府県名(例: "東京都")。47都道府県の名称と完全一致させる
    municipality: str | None = Field(
        default=None,
        description=(
            "市区町村名。levelが'municipality'または'town'の場合のみ指定する"
            "(例: '府中市')。政令指定都市の区を指定する場合は区名まで含める"
            "(例: '横浜市中区')"
        ),
    )
    town: str | None = Field(
        default=None,
        description=("町丁目名。levelが'town'の場合のみ指定する(例: '丸の内一丁目')"),
    )
    value: float | None = None  # 塗り分けの濃淡、および流動線の太さに使う数値


@tool
def render_choropleth(level: LevelName, points: list[MapPoint]) -> str:
    """指定レベル(都道府県 / 市区町村 / 町丁目)の単位で数値を地図上に塗り分け表示する。

    市区町村・町丁目レベルの場合、pointsは50件までしか指定できない。
    """
    points = [MapPoint.model_validate(p) for p in points]
    _validate_map_points(level, points)

    return _render_map_html(mode="choropleth", level=level, points=points)


@tool
def render_spider(
    level: LevelName, origin_lat: float, origin_lon: float, points: list[MapPoint]
) -> str:
    """起点となる緯度経度から、指定レベルの各地点への流動線を地図上に描く。

    線の太さは値に比例する。市区町村・町丁目レベルの場合、pointsは50件までしか指定できない。
    """
    points = [MapPoint.model_validate(p) for p in points]
    _validate_map_points(level, points)

    return _render_map_html(
        mode="spider", level=level, points=points, origin=(origin_lon, origin_lat)
    )


# --- 以下、地図ツールの内部ヘルパー(呼び出される側が下になるよう並べている) ---


@dataclass(frozen=True)
class _LevelData:
    """levelごとの地図データ。

    パース済みGeoJSON FeatureCollectionと地点名→座標の辞書を保持する。
    """

    geojson: dict
    points: dict[str, list[float]]


def _load_level_data(level: LevelName) -> _LevelData:
    """dataディレクトリからlevelのGeoJSON(都道府県ごとに分割済み)と座標辞書を読み込む。"""
    data_dir = Path(__file__).parent / "data"
    features = []
    for path in sorted((data_dir / level).glob("*.geojson")):
        features.extend(json.loads(path.read_text())["features"])
    return _LevelData(
        geojson={"type": "FeatureCollection", "features": features},
        points=json.loads((data_dir / f"{level}_points.json").read_text()),
    )


_LEVEL_DATA: dict[LevelName, _LevelData] = {
    level: _load_level_data(level) for level in get_args(LevelName)
}

_DETAILED_LEVEL_POINTS_LIMIT = 50


def _validate_map_points(level: LevelName, points: list[MapPoint]) -> None:
    """MapPointのリストが空でなく、件数上限内で、重複がなく、すべて既知の地点かを検証する。"""
    if not points:
        raise ValueError("pointsが空です")
    if level != "prefecture" and len(points) > _DETAILED_LEVEL_POINTS_LIMIT:
        raise ValueError(
            f"{level}レベルで指定できるpointsは{_DETAILED_LEVEL_POINTS_LIMIT}件までです"
            f"(指定件数: {len(points)})"
        )
    known = _LEVEL_DATA[level].points
    seen: set[str] = set()
    for point in points:
        key = _point_key(level, point.prefecture, point.municipality, point.town)
        if key not in known:
            raise ValueError(f"未知の地点です: {key}")
        if key in seen:
            raise ValueError(f"pointsに同じ地点が重複しています: {key}")
        seen.add(key)


def _render_map_html(
    mode: Literal["choropleth", "spider"],
    level: LevelName,
    points: list[MapPoint],
    origin: tuple[float, float] | None = None,
) -> str:
    """地図描画用の設定をLeafletのmapテンプレートに埋め込みHTML文字列にする。"""
    values = [p.value for p in points if p.value is not None]
    config = {
        "mode": mode,
        "points": [_point_config(level, p) for p in points],
        "origin": [origin[0], origin[1]] if origin else None,
        "valueMin": min(values) if values else 0.0,
        "valueMax": max(values) if values else 0.0,
    }

    html = _MAP_TEMPLATE.replace(
        "{{regions_geojson}}",
        json.dumps(_regions_geojson(level, points), ensure_ascii=False),
    )
    html = html.replace("{{map_config}}", json.dumps(config))
    return upload_html(html)


def _regions_geojson(level: LevelName, points: list[MapPoint]) -> dict:
    """埋め込み用GeoJSONを返す。市区町村・町丁目レベルはpointsに対応する地域のみへ絞り込む(全国分を毎回埋め込むとサイズ・描画負荷の両面で実用に耐えないため)。都道府県レベルは47件のみで軽量なため、値のない地域もグレー表示できるよう全国分をそのまま返す。"""
    level_data = _LEVEL_DATA[level]
    if level == "prefecture":
        return level_data.geojson
    keys = {_point_key(level, p.prefecture, p.municipality, p.town) for p in points}
    return {
        "type": "FeatureCollection",
        "features": [
            f for f in level_data.geojson["features"] if f["properties"]["name"] in keys
        ],
    }


def _point_config(level: LevelName, point: MapPoint) -> dict:
    """MapPointを地図描画用のpoint設定(name/value/lon/lat)に変換する。"""
    key = _point_key(level, point.prefecture, point.municipality, point.town)
    lon, lat = _LEVEL_DATA[level].points[key]
    return {"name": key, "value": point.value, "lon": lon, "lat": lat}


def _point_key(
    level: LevelName, prefecture: str, municipality: str | None, town: str | None
) -> str:
    """levelに応じてMapPointから座標辞書の検索キーを作る。"""
    if level == "town":
        if not municipality:
            raise ValueError("levelが'town'の場合はmunicipalityの指定が必須です")
        if not town:
            raise ValueError("levelが'town'の場合はtownの指定が必須です")
        return f"{prefecture}{municipality}{town}"
    if town:
        raise ValueError(f"levelが'town'以外の場合はtownを指定できません: {town}")
    if level == "municipality":
        if not municipality:
            raise ValueError(
                "levelが'municipality'の場合はmunicipalityの指定が必須です"
            )
        return f"{prefecture}{municipality}"
    if municipality:
        raise ValueError(
            f"levelが'prefecture'の場合はmunicipalityを指定できません: {municipality}"
        )
    return prefecture
