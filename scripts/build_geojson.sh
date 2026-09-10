#!/usr/bin/env bash
set -euo pipefail

# levelに応じた行政区画単位(都道府県 or 市区町村)に統合・簡略化したGeoJSONを生成するビルドスクリプト。
# levelごとにデータソースが異なる。
#   prefecture:   MLIT国土数値情報(N03)をダウンロードして生成
#   municipality: e-Stat小地域境界データ(shapefile/に手動配置)から生成
#                 ※N03には政令指定都市の区の境界が無いため
# 実行時には関与しない、ビルド時のみのツール。

LEVEL="${1:?levelを指定してください(prefecture|municipality)}"
YEAR="${2:-2026}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
mkdir -p "${REPO_ROOT}/backend/data"
DISSOLVED="${WORKDIR}/dissolved.geojson"

case "$LEVEL" in
  prefecture)
    DISSOLVE_FIELDS="N03_001"
    SIMPLIFY_PCT="0.02%"
    OUT_FILE="${REPO_ROOT}/backend/data/japan_prefectures.geojson"
    POINTS_FILE="${REPO_ROOT}/backend/data/prefecture_points.json"
    ;;
  municipality)
    DISSOLVE_FIELDS="PREF_NAME,CITY_NAME"
    OUT_FILE="${REPO_ROOT}/backend/data/japan_municipalities.geojson"
    POINTS_FILE="${REPO_ROOT}/backend/data/municipality_points.json"
    SHAPE_DIR="${REPO_ROOT}/shapefile"

    if [ ! -d "$SHAPE_DIR" ] || [ -z "$(find "$SHAPE_DIR" \( -name '*.zip' -o -name '*.shp' \) -print -quit)" ]; then
      echo "${SHAPE_DIR}/にe-Statの境界データ(zip)が見つかりません。READMEを参照して手動配置してください" >&2
      exit 1
    fi

    EXTRACT_DIR="${WORKDIR}/extracted"
    mkdir -p "$EXTRACT_DIR"

    echo "==> shapefile/配下のzipを展開中..."
    find "$SHAPE_DIR" -name '*.zip' -print0 | while IFS= read -r -d '' zip; do
      python3 -m zipfile -e "$zip" "$EXTRACT_DIR"
    done

    echo "==> shapefile/配下の展開済みshpをリンク中..."
    find "$SHAPE_DIR" -name '*.shp' -print0 | while IFS= read -r -d '' shp; do
      base="${shp%.shp}"
      for ext in shp shx dbf prj cpg; do
        [ -f "${base}.${ext}" ] && ln -sf "${base}.${ext}" "${EXTRACT_DIR}/" || true
      done
    done

    SHP_COUNT=$(find "$EXTRACT_DIR" -name '*.shp' | wc -l)
    echo "==> ${SHP_COUNT}件のshapefileを検出しました(全国47件推奨。不足分は未収録のまま生成されます)"

    echo "==> mapshaperで市区町村(政令指定都市の区を含む)単位に統合・簡略化中..."
    npx --yes mapshaper "${EXTRACT_DIR}"/*.shp combine-files \
      -proj wgs84 \
      -dissolve2 fields="$DISSOLVE_FIELDS" \
      -clean \
      -simplify dp 10% keep-shapes \
      -clean \
      -o format=geojson precision=0.0001 combine-layers "$DISSOLVED"
    ;;
  *)
    echo "不明なlevelです: ${LEVEL} (prefecture|municipalityを指定してください)" >&2
    exit 1
    ;;
esac

# N03のダウンロードはprefectureのみ必要。municipalityはshapefile/のe-Statデータを使う
if [ "$LEVEL" = "prefecture" ]; then
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
  # 元データの座標密度が非常に高く(全国で1000万点超)、
  # -clean を simplify の後に置くと自己交差の修復に失敗し
  # 出力が肥大化するため、簡略化前に一度topologyを整えておく。
  npx --yes mapshaper "$SHP" \
    -proj wgs84 \
    -dissolve2 fields="$DISSOLVE_FIELDS" \
    -clean \
    -simplify dp "$SIMPLIFY_PCT" keep-shapes \
    -clean \
    -o format=geojson precision=0.0001 "$DISSOLVED"
fi

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

echo "==> 代表点座標を計算中..."
uv run --project "${REPO_ROOT}/backend" python "${REPO_ROOT}/scripts/generate_points.py" "$OUT_FILE" "$POINTS_FILE"
echo "==> 生成完了: ${POINTS_FILE}"
