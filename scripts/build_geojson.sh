#!/usr/bin/env bash
set -euo pipefail

# MLIT国土数値情報(N03, 行政区域データ)の一次ソースから
# levelに応じた行政区画単位(都道府県 or 市区町村)に統合・簡略化したGeoJSONを生成するビルドスクリプト。
# 実行時には関与しない、ビルド時のみのツール。

LEVEL="${1:?levelを指定してください(prefecture|municipality)}"
YEAR="${2:-2026}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

case "$LEVEL" in
  prefecture)
    DISSOLVE_FIELDS="N03_001"
    SIMPLIFY_PCT="2%"
    OUT_FILE="${REPO_ROOT}/backend/data/japan_prefectures.geojson"
    ;;
  municipality)
    DISSOLVE_FIELDS="N03_001,N03_003,N03_004"
    SIMPLIFY_PCT="5%"
    OUT_FILE="${REPO_ROOT}/backend/data/japan_municipalities.geojson"
    ;;
  *)
    echo "不明なlevelです: ${LEVEL} (prefecture|municipalityを指定してください)" >&2
    exit 1
    ;;
esac

echo "==> N03-${YEAR}をダウンロード中..."
curl -L -o "${WORKDIR}/N03.zip" \
  "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-${YEAR}/N03-${YEAR}0101_GML.zip"

echo "==> 展開中..."
python3 -m zipfile -e "${WORKDIR}/N03.zip" "${WORKDIR}/N03"

SHP="$(find "${WORKDIR}/N03" -name '*.shp' ! -name '*_prefecture.shp' | sort | head -1)"
if [ -z "$SHP" ]; then
  echo "shapefileが見つかりませんでした" >&2
  exit 1
fi

echo "==> mapshaperで${LEVEL}単位に統合・簡略化中..."
mkdir -p "${REPO_ROOT}/backend/data"
DISSOLVED="${WORKDIR}/dissolved.geojson"
npx --yes mapshaper "$SHP" \
  -proj wgs84 \
  -dissolve2 fields="$DISSOLVE_FIELDS" \
  -simplify dp 0.3% keep-shapes \
  -simplify dp "$SIMPLIFY_PCT" keep-shapes \
  -clean \
  -o format=geojson precision=0.0001 "$DISSOLVED"

echo "==> 地域名(name)を組み立て中..."
python3 - "$DISSOLVED" "$OUT_FILE" "$DISSOLVE_FIELDS" <<'PYEOF'
import json
import sys

in_path, out_path, fields_csv = sys.argv[1], sys.argv[2], sys.argv[3]
fields = fields_csv.split(",")

data = json.load(open(in_path))
for feature in data["features"]:
    props = feature["properties"]
    name = "".join(props.get(f) or "" for f in fields)
    feature["properties"] = {"name": name}

json.dump(data, open(out_path, "w"), ensure_ascii=False)

names = sorted(f["properties"]["name"] for f in data["features"])
print(f"features: {len(names)}")
print(names)
PYEOF

echo "==> 生成完了: ${OUT_FILE}"
wc -c "$OUT_FILE"
