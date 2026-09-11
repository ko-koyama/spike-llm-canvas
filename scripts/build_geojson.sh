#!/usr/bin/env bash
set -euo pipefail

# levelに応じた行政区画単位(都道府県 / 市区町村 / 町丁目)に統合・簡略化したGeoJSONを生成するビルドスクリプト。
# 全レベルとも同じe-Stat小地域境界データ(shapefile/に手動配置)を都道府県ごとに処理し、
# backend/data/<level>/ 配下へ都道府県単位のファイルとして出力する
# (1ファイルに全国分をまとめるとGitHubの単一ファイルサイズ上限を超えるため)。
# 実行時には関与しない、ビルド時のみのツール。

LEVEL="${1:?levelを指定してください(prefecture|municipality|town)}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
SHAPE_DIR="${REPO_ROOT}/shapefile"

case "$LEVEL" in
  prefecture)   DISSOLVE_FIELDS="PREF_NAME" ;;
  municipality) DISSOLVE_FIELDS="PREF_NAME,CITY_NAME" ;;
  town)         DISSOLVE_FIELDS="PREF_NAME,CITY_NAME,S_NAME" ;;
  *)
    echo "不明なlevelです: ${LEVEL} (prefecture|municipality|townを指定してください)" >&2
    exit 1
    ;;
esac

OUT_DIR="${REPO_ROOT}/backend/data/${LEVEL}"
POINTS_FILE="${REPO_ROOT}/backend/data/${LEVEL}_points.json"

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

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

echo "==> mapshaperで都道府県ごとに${LEVEL}単位へ統合・簡略化中..."
find "$EXTRACT_DIR" -name '*.shp' -print0 | while IFS= read -r -d '' shp; do
  name="$(basename "${shp%.shp}")"
  dissolved="${WORKDIR}/${name}.geojson"
  npx --yes mapshaper "$shp" \
    -proj wgs84 \
    -dissolve fields="$DISSOLVE_FIELDS" \
    -clean \
    -simplify dp 10% keep-shapes \
    -clean \
    -o format=geojson precision=0.0001 "$dissolved"
  python3 "${REPO_ROOT}/scripts/assemble_region_name.py" "$dissolved" "${OUT_DIR}/${name}.geojson" "$DISSOLVE_FIELDS"
done

echo "==> 生成完了: ${OUT_DIR}/"
du -sh "$OUT_DIR"

echo "==> 代表点座標を計算中..."
uv run --project "${REPO_ROOT}/backend" python "${REPO_ROOT}/scripts/generate_points.py" "$OUT_DIR" "$POINTS_FILE"
echo "==> 生成完了: ${POINTS_FILE}"
