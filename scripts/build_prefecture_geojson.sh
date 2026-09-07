#!/usr/bin/env bash
set -euo pipefail

# MLIT国土数値情報(N03, 行政区域データ)の一次ソースから
# 都道府県単位に統合・簡略化したGeoJSONを生成するビルドスクリプト。
# 実行時には関与しない、ビルド時のみのツール。

YEAR="${1:-2026}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_FILE="${REPO_ROOT}/backend/data/japan_prefectures.geojson"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

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

echo "==> mapshaperで都道府県単位に統合・簡略化中..."
mkdir -p "${REPO_ROOT}/backend/data"
npx --yes mapshaper "$SHP" \
  -proj wgs84 \
  -dissolve2 fields=N03_001 \
  -rename-fields name=N03_001 \
  -simplify dp 0.3% keep-shapes \
  -clean \
  -o format=geojson precision=0.0001 "$OUT_FILE"

echo "==> 生成完了: $OUT_FILE"
wc -c "$OUT_FILE"
python3 -c "
import json
data = json.load(open('$OUT_FILE'))
names = sorted(f['properties']['name'] for f in data['features'])
print(f'features: {len(names)}')
print(names)
"
