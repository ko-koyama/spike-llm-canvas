# 市区町村レベル地図可視化 対応 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `render_choropleth`/`render_spider`を都道府県レベルに加えて市区町村レベルでも使えるようにする。

**Architecture:** 既存ツールに`level`(`"prefecture"` | `"municipality"`)パラメータを追加し、level別のGeoJSON/代表点座標をモジュールロード時に読み込んで切り替える。`render_spider`の起点は行政区画名ではなく緯度経度で直接指定する形に変更する。

**Tech Stack:** Python 3.12 / FastAPI / strands-agents / Pydantic / mapshaper(Node, npx経由) / shapely / Leaflet.js

**Spec:** `docs/superpowers/specs/2026-09-10-municipality-level-map-design.md`

## Global Constraints

- パッケージの追加・削除は`pyproject.toml`を直接編集せず`uv add`/`uv remove`を使う(`backend/`配下で実行)
- コミットメッセージは`<type>: <説明>`形式・1行・40字程度(`type`は`feat`/`fix`/`chore`のいずれか)
- 自動テストは追加しない。動作確認は都度コマンド実行やPlaywrightでの手動確認で行う(本リポジトリは技術検証用のため)
- ソースコードのコメント・関数docstringは日本語で書く
- 作業ブランチは`feat/municipality-level-map`(作成済み)。各タスック完了ごとにこのブランチにコミットする

---

## 事前準備: ネットワークアクセスの確認

以降のタスクはMLIT(国土交通省)のサーバーからのダウンロード(`nlftp.mlit.go.jp`)と、mapshaperの取得(`npx`経由でnpmレジストリ)を必要とする。実行環境からこれらにアクセスできることを前提とする(既存の`scripts/build_prefecture_geojson.sh`が過去に実行できていることから、開発環境では疎通済みのはず)。

---

### Task 1: ビルドスクリプトのlevel対応化(GeoJSON生成)

> **状況:** このタスクは実施中に2回設計変更が入っている。
> 1. 1回目のコミット(`ef37c1f`)後、簡略化(`-simplify`)が効かず都道府県71KB想定が3.5MB・市区町村が173MBに肥大化する不具合が見つかり、`-clean`をdissolve直後に置く・簡略化率を下げる、で修正した(`83fddfd`。都道府県71KB、市区町村2.6MB)。
> 2. その後、MLIT N03には政令指定都市の区(例: 横浜市中区)の境界が独立ポリゴンとして存在しないことが判明し、市区町村レベルのデータソースをe-Stat「令和2年国勢調査 小地域集計」境界データ(ユーザーが手動ダウンロードし`shapefile/`直下にzipのまま配置)に変更することになった。あわせて、Task 3で「市区町村レベルは常に選択された地域(最大50件)のみをHTMLに埋め込む」設計に変更されたため、全国分のファイルサイズを厳しく詰める必要はなくなった。ただし個々のポリゴンの頂点数が異常に多くならないよう、軽い簡略化は残す。
>
> **`prefecture`ブランチは`83fddfd`で完了済み・動作確認済みのため変更不要。** 以下のStepは`municipality`ブランチの書き直しのみを対象とする。

**Files:**
- Modify: `scripts/build_geojson.sh`(`municipality`ブランチをe-Stat由来の生成ロジックに書き換える。`prefecture`ブランチは変更しない)
- Create (スクリプト実行結果): `backend/data/japan_municipalities.geojson`(再生成)

**Interfaces:**
- Produces: `scripts/build_geojson.sh municipality`実行で`backend/data/japan_municipalities.geojson`を生成する(featureは`properties = {"name": "<都道府県名><市区町村名>"}`。政令指定都市は区名まで含む。例: `"神奈川県横浜市中区"`)
- Consumes: リポジトリ直下`shapefile/`配下にユーザーが手動配置したe-Statのzip(または展開済みディレクトリ)。現時点では動作確認用に北海道分(`shapefile/A002005212020DDSWC01/`)のみ配置されている。残り46都道府県は後日ユーザーが追加する想定。スクリプトは`shapefile/`配下に存在するファイルだけを対象に処理する(全部揃っていなくても実行はできる)

- [ ] **Step 1: `scripts/build_geojson.sh`の`municipality`ブランチを書き換える**

現在の`case "$LEVEL" in ... municipality) ... ;; esac`ブロックのうち`municipality)`の中身を、以下に置き換える(`prefecture)`ブロックと末尾の地域名組み立て・代表点生成部分は変更しない)。

```bash
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
        [ -f "${base}.${ext}" ] && ln -sf "${base}.${ext}" "${EXTRACT_DIR}/"
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
      -o format=geojson precision=0.0001 "$DISSOLVED"
    ;;
```

`DISSOLVED`変数は既存の`prefecture`ブロックと共有する(スクリプト冒頭で`DISSOLVED="${WORKDIR}/dissolved.geojson"`として定義済みのはず。定義されていなければ`case`文の直前に追加する)。

- [ ] **Step 2: 動作確認用に配置済みの北海道データで実行する**

```bash
./scripts/build_geojson.sh municipality
```

Expected: `1件のshapefileを検出しました`のようなログの後、`features: <北海道内の市区町村数(180前後)>`が出力され、地域名一覧に`"北海道札幌市中央区"`のような区名を含む名称が確認できること(区ごとに別featureになっていること)。生成される`backend/data/japan_municipalities.geojson`のサイズを`wc -c`で確認し、数百KB〜数MB程度(異常に大きくない)であることを確認する。

- [ ] **Step 3: コミットする**

北海道1県分のみだが、スクリプトの動作確認は完了しているため一旦コミットする(残り46都道府県分は`shapefile/`にユーザーが追加後、同じコマンドを再実行すれば`backend/data/japan_municipalities.geojson`が全国分に更新される。これは実装計画の対象外の後日作業とする)。

```bash
git add scripts/build_geojson.sh backend/data/japan_municipalities.geojson
git commit -m "feat: 市区町村データをe-Stat境界データに変更"
```

---

### Task 2: 代表点(重心)座標の自動生成

**Files:**
- Modify: `backend/pyproject.toml`(`uv add --dev shapely`で追加)
- Create: `scripts/generate_points.py`
- Modify: `scripts/build_geojson.sh`
- Modify (スクリプト実行結果): `backend/data/prefecture_points.json`(手打ちデータから自動生成に置き換え)
- Create (スクリプト実行結果): `backend/data/municipality_points.json`

**Interfaces:**
- Consumes: Task 1で生成した`backend/data/japan_prefectures.geojson` / `japan_municipalities.geojson`(`properties.name`で地域名を持つ)
- Produces: `scripts/generate_points.py <geojson_path> <points_json_path>`。実行すると`{"地域名": [経度, 緯度], ...}`形式のJSONを生成する

- [ ] **Step 1: shapelyをbackendの開発依存に追加する**

```bash
cd backend && uv add --dev shapely
cd ..
```

- [ ] **Step 2: 代表点生成スクリプトを作成する**

`scripts/generate_points.py`を作成する。

```python
#!/usr/bin/env python3
"""行政区画ポリゴンのGeoJSONから、地域名→代表点(経度・緯度)のJSONを生成する。"""

import json
import sys

from shapely.geometry import shape


def main() -> None:
    geojson_path, points_path = sys.argv[1], sys.argv[2]
    data = json.load(open(geojson_path))

    points: dict[str, list[float]] = {}
    for feature in data["features"]:
        name = feature["properties"]["name"]
        # representative_point()はポリゴン(離島を含む複数パーツの場合も含む)の
        # 内部に必ず収まる点を返すため、重心が海上にはみ出す問題を避けられる
        point = shape(feature["geometry"]).representative_point()
        points[name] = [round(point.x, 4), round(point.y, 4)]

    json.dump(points, open(points_path, "w"), ensure_ascii=False, indent=2)
    print(f"points: {len(points)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: `build_geojson.sh`に代表点生成ステップを追加する**

`scripts/build_geojson.sh`の`case`ブロックに`POINTS_FILE`を追加し、末尾に生成ステップを追加する。

```bash
case "$LEVEL" in
  prefecture)
    DISSOLVE_FIELDS="N03_001"
    SIMPLIFY_PCT="2%"
    OUT_FILE="${REPO_ROOT}/backend/data/japan_prefectures.geojson"
    POINTS_FILE="${REPO_ROOT}/backend/data/prefecture_points.json"
    ;;
  municipality)
    DISSOLVE_FIELDS="N03_001,N03_003,N03_004"
    SIMPLIFY_PCT="5%"
    OUT_FILE="${REPO_ROOT}/backend/data/japan_municipalities.geojson"
    POINTS_FILE="${REPO_ROOT}/backend/data/municipality_points.json"
    ;;
  *)
    echo "不明なlevelです: ${LEVEL} (prefecture|municipalityを指定してください)" >&2
    exit 1
    ;;
esac
```

ファイル末尾(`wc -c "$OUT_FILE"`の後)に追記する。

```bash
echo "==> 代表点座標を計算中..."
uv run --project "${REPO_ROOT}/backend" python "${REPO_ROOT}/scripts/generate_points.py" "$OUT_FILE" "$POINTS_FILE"
echo "==> 生成完了: ${POINTS_FILE}"
```

- [ ] **Step 4: 両レベルで再実行し、座標を確認する**

```bash
./scripts/build_geojson.sh prefecture
./scripts/build_geojson.sh municipality
```

Expected: `backend/data/prefecture_points.json`が上書きされ、`backend/data/municipality_points.json`が新規生成される。以下のPythonワンライナーで、全座標が日本の大まかな範囲(経度122〜154、緯度20〜46)に収まっていることを確認する。

```bash
python3 -c "
import json
for path in ['backend/data/prefecture_points.json', 'backend/data/municipality_points.json']:
    data = json.load(open(path))
    bad = [(name, lon, lat) for name, (lon, lat) in data.items() if not (122 <= lon <= 154 and 20 <= lat <= 46)]
    print(path, 'total:', len(data), 'out_of_range:', bad)
"
```

Expected: `out_of_range: []`(空リスト)。加えて`git diff backend/data/prefecture_points.json`で沖縄県・東京都・長崎県・鹿児島県の座標が旧来の手打ち値(本島側の値)から大きく外れていないことを目視確認する。大きく外れている場合はTask完了とせず、原因(重心計算方法)を見直す。

- [ ] **Step 5: コミットする**

```bash
git add backend/pyproject.toml backend/uv.lock scripts/generate_points.py scripts/build_geojson.sh backend/data/prefecture_points.json backend/data/municipality_points.json
git commit -m "feat: 代表点座標を重心から自動生成"
```

---

### Task 3: `render_choropleth`のlevel対応とテンプレート汎用化

**Files:**
- Modify: `backend/tools.py`
- Modify: `backend/templates/map_leaflet.html`

**Interfaces:**
- Consumes: Task 1/2で生成した`backend/data/japan_{prefectures,municipalities}.geojson`, `backend/data/{prefecture,municipality}_points.json`
- Produces: `LevelName = Literal["prefecture", "municipality"]`(型エイリアス)
- Produces: `MapPoint(prefecture: str, municipality: str | None, value: float | None)`
- Produces: `_point_key(level: LevelName, prefecture: str, municipality: str | None) -> str`
- Produces: `_validate_map_points(level: LevelName, points: list[MapPoint]) -> None`
- Produces: `_regions_geojson(level: LevelName, points: list[MapPoint]) -> dict`(市区町村レベルはpointsの地域だけに絞り込んだFeatureCollection、都道府県レベルは全国分をそのまま返す)
- Produces: `_render_map_html(mode: Literal["choropleth", "spider"], level: LevelName, points: list[MapPoint], origin: tuple[float, float] | None = None) -> str`
- Produces: `render_choropleth(level: LevelName, points: list[MapPoint]) -> str`(Task 4で`render_spider`が同じ`_validate_map_points`/`_render_map_html`を使う)

- [ ] **Step 1: `backend/tools.py`のデータ読み込み部分をlevel対応にする**

`import json` の下に `from dataclasses import dataclass` を追加する。

以下の部分を

```python
_PREFECTURES_GEOJSON = (
    Path(__file__).parent / "data" / "japan_prefectures.geojson"
).read_text()
_PREFECTURE_POINTS: dict[str, list[float]] = json.loads(
    (Path(__file__).parent / "data" / "prefecture_points.json").read_text()
)
```

以下に置き換える。

```python
LevelName = Literal["prefecture", "municipality"]

_LEVEL_FILES: dict[LevelName, tuple[str, str]] = {
    "prefecture": ("japan_prefectures.geojson", "prefecture_points.json"),
    "municipality": ("japan_municipalities.geojson", "municipality_points.json"),
}


@dataclass(frozen=True)
class _LevelData:
    """levelごとの地図データ(パース済みGeoJSON FeatureCollectionと地点名→座標の辞書)。"""

    geojson: dict
    points: dict[str, list[float]]


def _load_level_data(geojson_filename: str, points_filename: str) -> _LevelData:
    """dataディレクトリからGeoJSONと座標辞書を読み込む。"""
    data_dir = Path(__file__).parent / "data"
    return _LevelData(
        geojson=json.loads((data_dir / geojson_filename).read_text()),
        points=json.loads((data_dir / points_filename).read_text()),
    )


_LEVEL_DATA: dict[LevelName, _LevelData] = {
    level: _load_level_data(*files) for level, files in _LEVEL_FILES.items()
}
```

- [ ] **Step 2: `MapPoint`に`municipality`フィールドを追加する**

```python
class MapPoint(BaseModel):
    """地図上の1地点。"""

    prefecture: str  # 都道府県名(例: "東京都")。47都道府県の名称と完全一致させる
    municipality: str | None = Field(
        default=None,
        description=(
            "市区町村名。levelが'municipality'の場合のみ指定する(例: '府中市')。"
            "政令指定都市の区を指定する場合は区名まで含める(例: '横浜市中区')"
        ),
    )
    value: float | None = None  # 塗り分けの濃淡、および流動線の太さに使う数値
```

- [ ] **Step 3: `render_choropleth`をlevel対応にする**

```python
@tool
def render_choropleth(level: LevelName, points: list[MapPoint]) -> str:
    """指定レベル(都道府県 or 市区町村)の単位で数値を地図上に塗り分け表示する。市区町村レベルの場合、pointsは50件までしか指定できない。"""
    points = [MapPoint.model_validate(p) for p in points]
    _validate_map_points(level, points)

    return _render_map_html(mode="choropleth", level=level, points=points)
```

- [ ] **Step 4: `_validate_map_points`・`_render_map_html`をlevel対応にする(`render_spider`は次タスクで対応するため、ここでは一旦削除して構わない)**

既存の`_validate_map_points`・`_render_map_html`を削除し、以下に置き換える。市区町村レベルは件数が多く、地図上に大量表示すると視認性・描画負荷の両面で実用に耐えないため、`points`の件数に上限(`_MUNICIPALITY_POINTS_LIMIT = 50`)を設ける(都道府県レベルは47件で収まるため上限は設けない)。

```python
_MUNICIPALITY_POINTS_LIMIT = 50


def _point_key(level: LevelName, prefecture: str, municipality: str | None) -> str:
    """levelに応じてMapPointから座標辞書の検索キーを作る。"""
    if level == "municipality":
        if not municipality:
            raise ValueError("levelが'municipality'の場合はmunicipalityの指定が必須です")
        return f"{prefecture}{municipality}"
    return prefecture


def _validate_map_points(level: LevelName, points: list[MapPoint]) -> None:
    """MapPointのリストが空でなく、件数上限内で、すべて既知の地点かを検証する。"""
    if not points:
        raise ValueError("pointsが空です")
    if level == "municipality" and len(points) > _MUNICIPALITY_POINTS_LIMIT:
        raise ValueError(
            f"市区町村レベルで指定できるpointsは{_MUNICIPALITY_POINTS_LIMIT}件までです(指定件数: {len(points)})"
        )
    known = _LEVEL_DATA[level].points
    for point in points:
        key = _point_key(level, point.prefecture, point.municipality)
        if key not in known:
            raise ValueError(f"未知の地点です: {key}")


def _point_config(level: LevelName, point: MapPoint) -> dict:
    """MapPointを地図描画用のpoint設定(name/value/lon/lat)に変換する。"""
    key = _point_key(level, point.prefecture, point.municipality)
    lon, lat = _LEVEL_DATA[level].points[key]
    return {"name": key, "value": point.value, "lon": lon, "lat": lat}


def _regions_geojson(level: LevelName, points: list[MapPoint]) -> dict:
    """埋め込み用GeoJSONを返す。市区町村レベルはpointsに対応する地域のみへ絞り込む(全国約1,900件を毎回埋め込むとサイズ・描画負荷の両面で実用に耐えないため)。都道府県レベルは47件のみで軽量なため、値のない地域もグレー表示できるよう全国分をそのまま返す。"""
    level_data = _LEVEL_DATA[level]
    if level == "prefecture":
        return level_data.geojson
    keys = {_point_key(level, p.prefecture, p.municipality) for p in points}
    return {
        "type": "FeatureCollection",
        "features": [
            f for f in level_data.geojson["features"] if f["properties"]["name"] in keys
        ],
    }


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
        "{{regions_geojson}}", json.dumps(_regions_geojson(level, points), ensure_ascii=False)
    )
    html = html.replace("{{map_config}}", json.dumps(config))
    return upload_html(html)
```

- [ ] **Step 5: `map_leaflet.html`のプレースホルダ・命名を汎用化する**

`backend/templates/map_leaflet.html`を以下の通り変更する。

- `const geojson = {{prefectures_geojson}};` → `const geojson = {{regions_geojson}};`
- `const prefectureLayer = drawPrefectures();` → `const regionLayer = drawRegions();`
- `map.fitBounds(prefectureLayer.getBounds(), { padding: [16, 16] });` → `map.fitBounds(regionLayer.getBounds(), { padding: [16, 16] });`
- `linkPolygonAndLineHover(prefectureLayer, lineByName);` → `linkPolygonAndLineHover(regionLayer, lineByName);`
- `function drawPrefectures() {` → `function drawRegions() {`
- `function linkPolygonAndLineHover(prefectureLayer, lineByName) {` → `function linkPolygonAndLineHover(regionLayer, lineByName) {`
- `prefectureLayer.eachLayer((layer) => {` → `regionLayer.eachLayer((layer) => {`

- [ ] **Step 6: バリデーション・描画ロジックを手動確認する**

`render_spider`はまだ未対応(Task 4)のため、`_validate_map_points`・`_render_map_html`のみをコード内から直接呼び出して確認する。`render_choropleth`自体は`@tool`デコレータ付きでstrandsのAgent実行系を前提にしており、Pythonから素で呼び出せる保証がないため、ここでは同じロジックを持つ非デコレータのヘルパー(`_validate_map_points`・`_render_map_html`)を直接呼ぶことで代替する(`render_choropleth`本体はこの2つを呼ぶだけの薄いラッパーなので、これで実質的なロジックはカバーできる)。`backend/`ディレクトリで以下を実行する(事前に`export VIZ_S3_BUCKET=spike-llm-canvas-viz`などREADMEの手順でS3設定を済ませておく)。

```bash
cd backend
uv run python -c "
from tools import MapPoint, _validate_map_points, _render_map_html, _regions_geojson

# 正常系: 都道府県レベル
_validate_map_points('prefecture', [MapPoint(prefecture='東京都', value=1.0)])
print('OK: prefecture正常系')

# 正常系: 市区町村レベル(政令指定都市の区を含む)
points = [
    MapPoint(prefecture='東京都', municipality='府中市', value=1.0),
    MapPoint(prefecture='神奈川県', municipality='横浜市中区', value=2.0),
]
_validate_map_points('municipality', points)
print('OK: municipality正常系')

# 準正常系: 未知の市区町村名
try:
    _validate_map_points('municipality', [MapPoint(prefecture='東京都', municipality='存在しない市', value=1.0)])
    print('NG: 例外が発生しなかった')
except ValueError as e:
    print(f'OK: {e}')

# 準正常系: 市区町村レベルでpointsが50件を超える
try:
    too_many = [MapPoint(prefecture='東京都', municipality='府中市', value=1.0) for _ in range(51)]
    _validate_map_points('municipality', too_many)
    print('NG: 例外が発生しなかった')
except ValueError as e:
    print(f'OK: {e}')

# 正常系: 市区町村レベルは埋め込みGeoJSONがpointsの地域だけに絞り込まれること
filtered = _regions_geojson('municipality', points)
assert len(filtered['features']) == len(points), f'絞り込み件数が一致しない: {len(filtered[\"features\"])}'
print('OK: municipalityは', len(filtered['features']), '件に絞り込み')

# 正常系: 都道府県レベルは全国分がそのまま埋め込まれること(絞り込まない)
pref_points = [MapPoint(prefecture='東京都', value=1.0)]
full = _regions_geojson('prefecture', pref_points)
assert len(full['features']) == 47, f'都道府県は絞り込まれないはずが{len(full[\"features\"])}件だった'
print('OK: prefectureは全国47件のまま')

# 正常系: render_choropleth相当(_validate_map_points + _render_map_html)でHTML生成までできること(S3設定済みであること)
key = _render_map_html(mode='choropleth', level='municipality', points=points)
print('OK: _render_map_html ->', key)
"
```

Expected: すべて`OK:`で始まる行が出力され、`NG:`が出力されないこと。

- [ ] **Step 7: コミットする**

```bash
git add backend/tools.py backend/templates/map_leaflet.html
git commit -m "feat: 地図ツールをlevel対応に拡張"
```

---

### Task 4: `render_spider`の起点を緯度経度指定に変更

**Files:**
- Modify: `backend/tools.py`

**Interfaces:**
- Consumes: Task 3の`_validate_map_points`, `_render_map_html`, `MapPoint`
- Produces: `render_spider(level: LevelName, origin_lat: float, origin_lon: float, points: list[MapPoint]) -> str`

- [ ] **Step 1: `render_spider`を書き換える**

既存の`render_spider`を以下に置き換える。

```python
@tool
def render_spider(
    level: LevelName, origin_lat: float, origin_lon: float, points: list[MapPoint]
) -> str:
    """起点となる緯度経度から、指定レベル(都道府県 or 市区町村)の各地点への流動線を地図上に描く。線の太さは値に比例する。市区町村レベルの場合、pointsは50件までしか指定できない。"""
    points = [MapPoint.model_validate(p) for p in points]
    _validate_map_points(level, points)

    return _render_map_html(
        mode="spider", level=level, points=points, origin=(origin_lon, origin_lat)
    )
```

これにより、旧実装にあった「originと同名のpointを除外するフィルタ」(`dest_points = [p for p in points if p.prefecture != origin]`)は不要になり削除される(originが行政区画に紐づかなくなったため)。

- [ ] **Step 2: 動作確認する**

`render_spider`も`@tool`デコレータ付きのためPythonから素で呼び出せる保証がなく、ここでも同じロジックを持つ非デコレータのヘルパー(`_validate_map_points`・`_render_map_html`)を直接呼ぶことで代替する(`render_spider`本体はこの2つを`mode="spider"`・`origin=(origin_lon, origin_lat)`で呼ぶだけの薄いラッパー)。`backend/`ディレクトリで以下を実行する。

```bash
cd backend
uv run python -c "
from tools import MapPoint, _validate_map_points, _render_map_html

# 正常系: 施設(緯度経度)を起点にした市区町村レベルのスパイダーマップ相当
points = [
    MapPoint(prefecture='東京都', municipality='府中市', value=10.0),
    MapPoint(prefecture='神奈川県', municipality='横浜市中区', value=20.0),
]
_validate_map_points('municipality', points)
key = _render_map_html(mode='spider', level='municipality', points=points, origin=(139.7671, 35.6812))
print('OK: spider(municipality) ->', key)

# 正常系: 都道府県レベル(回帰確認)
points = [MapPoint(prefecture='大阪府', value=5.0)]
_validate_map_points('prefecture', points)
key = _render_map_html(mode='spider', level='prefecture', points=points, origin=(139.6917, 35.6895))
print('OK: spider(prefecture) ->', key)
"
```

Expected: 2件とも`OK:`で始まる行が出力されること。

- [ ] **Step 3: コミットする**

```bash
git add backend/tools.py
git commit -m "feat: spiderの起点を緯度経度指定に変更"
```

---

### Task 5: README更新とエンドツーエンド動作確認

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1〜4で完成した全機能

- [ ] **Step 1: READMEのツール説明・スクリプト参照を更新する**

`README.md`の以下の記述を更新する。

```
  - `render_choropleth`: D3.jsによる都道府県単位の塗り分け地図(コロプレスマップ)の描画
  - `render_spider`: D3.jsによる起点都道府県からの流動線地図(スパイダーマップ)の描画
```

を

```
  - `render_choropleth`: Leafletによる都道府県/市区町村単位の塗り分け地図(コロプレスマップ)の描画
  - `render_spider`: Leafletによる任意地点(緯度経度)を起点とした流動線地図(スパイダーマップ)の描画
```

に変更する(合わせて、実装がすでにLeafletに移行済みであるにもかかわらずD3.jsのまま古くなっていた記述も修正する)。

また、

```
- `backend/data/japan_prefectures.geojson`は`scripts/build_prefecture_geojson.sh`で生成した都道府県ポリゴンデータ(生成手順はスクリプト内コメント参照)
```

を

```
- `backend/data/japan_{prefectures,municipalities}.geojson`・`{prefecture,municipality}_points.json`は`scripts/build_geojson.sh <level>`で生成した行政区画ポリゴン・代表点データ(生成手順はスクリプト内コメント参照)
- 市区町村レベル(`municipality`)のデータ生成には、e-Stat「令和2年国勢調査 小地域集計」境界データが必要
  - https://www.e-stat.go.jp/gis/statmap-search?page=1&type=2&aggregateUnitForBoundary=A&toukeiCode=00200521&toukeiYear=2020&serveyId=A002005212020&datum=2000 から都道府県ごとにダウンロード(形式: shapefile、座標系: 世界測地系緯度経度)
  - ダウンロードしたzip(リネーム不要)をリポジトリ直下の`shapefile/`に配置してから`./scripts/build_geojson.sh municipality`を実行する(`shapefile/`は`.gitignore`対象でコミットしない)
```

に変更する。

- [ ] **Step 2: コミットする**

```bash
git add README.md
git commit -m "chore: READMEを市区町村対応に更新"
```

- [ ] **Step 3: バックエンド・フロントエンドを起動する**

```bash
# ターミナル1
cd backend
export VIZ_S3_BUCKET=spike-llm-canvas-viz
uv run uvicorn main:app --reload

# ターミナル2
cd frontend
npm run dev
```

- [ ] **Step 4: Playwrightでチャット画面を操作し、以下を確認する**

`http://localhost:5173`をPlaywrightで開き、チャット欄から以下をそれぞれ送信し、右ペインに地図が表示され、市区町村単位/都道府県単位で正しく塗り分け・流動線が描画されることをスクリーンショットで確認する。

この時点で`shapefile/`には動作確認用に北海道分のみ配置されている想定のため、市区町村レベルの確認は北海道内の市区町村(政令指定都市札幌市の区を含む)で行う。全都道府県分が揃ったら、他地域でも同様に確認すること(このタスクの範囲外の後日作業でよい)。

1. 「北海道札幌市中央区、札幌市北区、旭川市の人口をそれぞれ100、80、200としてコロプレスマップで表示して」→ 市区町村単位(政令指定都市の区を含む)で塗り分けられ、指定した3地域以外の行政境界は表示されないこと(絞り込み挙動の確認)
2. 「札幌駅(緯度43.0686、経度141.3507)を起点に、札幌市中央区へ10、札幌市北区へ20の値でスパイダーマップを描いて」→ 起点マーカーが札幌駅付近に表示され、各区へ線が引かれること
3. 「北海道、東京都、大阪府、沖縄県の人口をそれぞれ500、1400、880、150としてコロプレスマップで表示して」→ 都道府県レベルが既存通り動作すること(回帰確認)。全国47都道府県の境界が表示され、沖縄県のポリゴンが正しい位置(南西諸島)に表示されていることを確認する

Expected: 3ケースすべてで地図が正しく描画され、コンソールエラーが出ていないこと。問題があれば該当タスクに戻って修正する。

---

## Self-Review Notes

- 設計書の各セクション(ビルドスクリプト共通化・`MapPoint`拡張・`origin`の緯度経度化・levelごとのデータ読み込み・テンプレート汎用化・スコープ外項目)はTask 1〜5でそれぞれカバーしている
- 型・関数名の一貫性: `LevelName`, `MapPoint`, `_point_key`, `_validate_map_points`, `_regions_geojson`, `_render_map_html`, `_point_config`はTask 3で定義し、Task 4はそれをそのまま再利用している(シグネチャの齟齬なし)
- データソース変更(N03→e-Stat)・GeoJSON絞り込み・50件上限は会話の途中で追加された決定であり、当初の設計書(`docs/superpowers/specs/2026-09-10-municipality-level-map-design.md`)を更新した上で本計画に反映している
- テストはCLAUDE.mdの方針と異なり本機能でも追加しない(ユーザー承認済み)。代わりに各タスクに具体的な手動確認コマンド・Playwrightでの確認手順を明記した
