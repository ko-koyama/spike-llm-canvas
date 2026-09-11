#!/usr/bin/env python3
"""行政区画ポリゴンのGeoJSON(都道府県ごとに分割されたディレクトリ)から、
地域名→代表点(経度・緯度)のJSONを生成する。"""

import json
import sys
from pathlib import Path

from shapely.geometry import shape


def main() -> None:
    geojson_dir, points_path = Path(sys.argv[1]), sys.argv[2]

    points: dict[str, list[float]] = {}
    for path in sorted(geojson_dir.glob("*.geojson")):
        data = json.loads(path.read_text())

        # simplify/cleanでポリゴンが潰れてgeometryがnull・空になっている地域は除外する
        valid_features = [
            f
            for f in data["features"]
            if f["geometry"] and not shape(f["geometry"]).is_empty
        ]
        dropped = len(data["features"]) - len(valid_features)
        if dropped:
            print(f"{path.name}: geometryが空のため除外: {dropped}件")
            data["features"] = valid_features
            path.write_text(json.dumps(data, ensure_ascii=False))

        for feature in valid_features:
            name = feature["properties"]["name"]
            point = representative_point(shape(feature["geometry"]))
            points[name] = [round(point.x, 4), round(point.y, 4)]

    json.dump(points, open(points_path, "w"), ensure_ascii=False, indent=2)
    print(f"points: {len(points)}")


def representative_point(geom):
    """ポリゴンの内部に必ず収まる代表点を返す。

    離島を含むMultiPolygonでは、GEOSのrepresentative_point()が
    最大面積の島(本土)ではなく小さな離島側を選ぶことがある
    (例: 沖縄県で八重山諸島側を選び、那覇から遠く離れる)。
    そのため最大面積のパーツに絞ってから代表点を求める。
    """
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda part: part.area)
    return geom.representative_point()


if __name__ == "__main__":
    main()
