# 都道府県マップ可視化(render_map) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 都道府県単位の数値データを地図で可視化する`render_map`toolを追加し、`origin`指定時は流動線(スパイダー)を、未指定時は塗り分け(コロプレス)のみを表示できるようにする。

**Architecture:** 既存の`render_chart`(Pydanticモデル + テンプレートHTML埋め込み)と同じ設計を踏襲する。地図描画はApache EChartsを使い、`map`系列(コロプレス)と`lines`系列(流動線)を1つの`option`に載せ、ECharts標準の凡例クリックでレイヤーの表示/非表示を切り替える。都道府県ポリゴンGeoJSONと代表点座標は、MLIT(国土交通省)一次ソースのN03データから事前に生成し、`backend/data/`配下に静的ファイルとして持つ(実行時にはこれを読み込むだけ)。

**Tech Stack:** Python 3.12 / FastAPI / Pydantic / strands-agents(既存)、Apache ECharts 5(新規、CDN経由・追加の実行時依存なし)、mapshaper(ビルド時のみ、npxで実行・実行時依存にはしない)

**Spec:** `docs/superpowers/specs/2026-09-07-prefecture-map-design.md`

## Global Constraints

- 新しいtoolは`render_chart`と同じ設計(Pydanticモデル + `@tool`関数 + テンプレートHTML文字列置換)に統一すること
- 都道府県ポリゴンGeoJSONはMLIT国土数値情報(N03)の一次ソースから取得すること(GitHub等のミラー・加工済みデータは使わない)。一次ソースURL: `https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2026/N03-20260101_GML.zip`
- 生のshapefile/zip(数百MB)はリポジトリにコミットしない。加工後の`backend/data/japan_prefectures.geojson`のみコミットする(本タスクでは一旦コミットする方針で進めるが、サイズが大きすぎる場合は次のタスクに進む前にユーザーに確認する)
- 本リポジトリは検証用(スパイク)のため、本機能について新規のpytestテストは書かない。その代わり各タスクで手動検証(`uv run python -c "..."`やサーバー起動確認)を行う
- バックエンドの実行時依存(`pyproject.toml`の`dependencies`)は増やさない。パッケージ追加が必要な場合は`uv add`を使うこと
- コミットメッセージは`<type>: <説明>`形式・1行(例: `feat: render_mapツールを追加`)
- コードコメント・関数のdocstringは日本語で簡潔に(結論のみ、経緯は書かない)

---

## Task 1: 都道府県ポリゴンGeoJSONの生成(データパイプライン)

**Files:**
- Create: `scripts/build_prefecture_geojson.sh`
- Create: `backend/data/japan_prefectures.geojson`(スクリプト実行による生成物)

**Interfaces:**
- Produces: `backend/data/japan_prefectures.geojson` — `FeatureCollection`。各`Feature.properties.name`に都道府県名(例: `"東京都"`)を持つ。後続タスクの`render_map`・Task 2の代表点データはこの`name`の値(47件)と完全一致させる

- [ ] **Step 1: ビルドスクリプトを作成する**

`scripts/build_prefecture_geojson.sh`を作成する:

```bash
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

SHP="$(find "${WORKDIR}/N03" -name '*.shp' | head -1)"
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
  -simplify dp 5% keep-shapes \
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
```

- [ ] **Step 2: 実行権限を付与する**

```bash
chmod +x scripts/build_prefecture_geojson.sh
```

- [ ] **Step 3: スクリプトを実行する**

```bash
./scripts/build_prefecture_geojson.sh
```

ダウンロードに数百MB・数分かかる可能性がある。`mapshaper`が未インストールでも`npx`が自動取得する(要インターネット接続、本環境では到達可能なことを確認済み)。

- [ ] **Step 4: 生成結果を検証する**

Step 3の出力で以下を確認する:
- `features: 47`と表示されること(都道府県数と一致)
- 都道府県名の一覧に文字化けがないこと(文字化けしていた場合は、スクリプトの`npx --yes mapshaper "$SHP"`の直後に`encoding=sjis`オプションを追加して再実行する: `npx --yes mapshaper "$SHP" encoding=sjis -proj wgs84 ...`)
- ファイルサイズ(`wc -c`)を確認する。数MBを超えて大きい場合は、`-simplify dp 5% keep-shapes`の`5%`を`2%`など小さい値に変更して再実行し、サイズと見た目のバランスを取る

- [ ] **Step 5: コミットする**

```bash
git add scripts/build_prefecture_geojson.sh backend/data/japan_prefectures.geojson
git commit -m "feat: 都道府県ポリゴンGeoJSONを追加"
```

生成物のファイルサイズが大きすぎる(目安: 1MBを大きく超える)場合は、コミット前にユーザーに一度確認すること(specの「保留事項」を参照)。

---

## Task 2: 都道府県代表点データの作成

**Files:**
- Create: `backend/data/prefecture_points.json`

**Interfaces:**
- Consumes: Task 1で生成した`backend/data/japan_prefectures.geojson`の`properties.name`一覧(47件、キーの突き合わせ用)
- Produces: `backend/data/prefecture_points.json` — `{"都道府県名": [経度, 緯度], ...}`という47件のJSON。後続タスクの`render_map`はこのキー(都道府県名)を入力バリデーションの正解データとして使い、値([経度, 緯度])を流動線の起点・終点座標として使う

- [ ] **Step 1: 代表点データ(県庁所在地の座標)を作成する**

`backend/data/prefecture_points.json`を作成する(県庁所在地の代表点、WGS84 経度・緯度):

```json
{
  "北海道": [141.3469, 43.0642],
  "青森県": [140.7400, 40.8244],
  "岩手県": [141.1527, 39.7036],
  "宮城県": [140.8694, 38.2688],
  "秋田県": [140.1023, 39.7186],
  "山形県": [140.3634, 38.2404],
  "福島県": [140.4676, 37.7500],
  "茨城県": [140.4467, 36.3418],
  "栃木県": [139.8836, 36.5658],
  "群馬県": [139.0608, 36.3912],
  "埼玉県": [139.6489, 35.8569],
  "千葉県": [140.1233, 35.6047],
  "東京都": [139.6917, 35.6895],
  "神奈川県": [139.6425, 35.4478],
  "新潟県": [139.0236, 37.9026],
  "富山県": [137.2114, 36.6953],
  "石川県": [136.6256, 36.5947],
  "福井県": [136.2216, 36.0652],
  "山梨県": [138.5684, 35.6642],
  "長野県": [138.1810, 36.6513],
  "岐阜県": [136.7223, 35.3912],
  "静岡県": [138.3831, 34.9769],
  "愛知県": [136.9066, 35.1802],
  "三重県": [136.5086, 34.7303],
  "滋賀県": [135.8686, 35.0045],
  "京都府": [135.7681, 35.0212],
  "大阪府": [135.5200, 34.6863],
  "兵庫県": [135.1830, 34.6913],
  "奈良県": [135.8325, 34.6851],
  "和歌山県": [135.1675, 34.2261],
  "鳥取県": [134.2380, 35.5039],
  "島根県": [133.0505, 35.4723],
  "岡山県": [133.9345, 34.6618],
  "広島県": [132.4596, 34.3966],
  "山口県": [131.4714, 34.1859],
  "徳島県": [134.5593, 34.0658],
  "香川県": [134.0434, 34.3401],
  "愛媛県": [132.7657, 33.8417],
  "高知県": [133.5311, 33.5597],
  "福岡県": [130.4017, 33.6064],
  "佐賀県": [130.2988, 33.2494],
  "長崎県": [129.8737, 32.7448],
  "熊本県": [130.7417, 32.7898],
  "大分県": [131.6126, 33.2382],
  "宮崎県": [131.4239, 31.9111],
  "鹿児島県": [130.5581, 31.5602],
  "沖縄県": [127.6809, 26.2124]
}
```

- [ ] **Step 2: Task 1の生成物とキーが一致するか検証する**

```bash
uv run --project backend python3 -c "
import json
geojson = json.load(open('backend/data/japan_prefectures.geojson'))
points = json.load(open('backend/data/prefecture_points.json'))
geo_names = {f['properties']['name'] for f in geojson['features']}
point_names = set(points.keys())
assert geo_names == point_names, geo_names.symmetric_difference(point_names)
print('OK: 47都道府県のキーが完全一致')
"
```

差分が出た場合は、`japan_prefectures.geojson`側の表記(全角/半角、旧字体など)に`prefecture_points.json`のキーを合わせる。

- [ ] **Step 3: コミットする**

```bash
git add backend/data/prefecture_points.json
git commit -m "feat: 都道府県代表点データを追加"
```

---

## Task 3: 地図用HTMLテンプレートの作成

**Files:**
- Create: `backend/templates/map.html`

**Interfaces:**
- Consumes: なし(静的テンプレート)
- Produces: `{{prefectures_geojson}}`と`{{map_config}}`という2つのプレースホルダを持つHTML文字列。Task 4の`render_map`がこの2箇所を実際のGeoJSON文字列・EChartsのoption(JSON)で置換する

- [ ] **Step 1: テンプレートを作成する**

`backend/templates/map.html`(`backend/templates/chart.html`と同じ構成):

```html
<html>
  <head>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5"></script>
    <style>
      html, body, #map {
        margin: 0;
        height: 100%;
      }
    </style>
  </head>
  <body>
    <div id="map"></div>
    <script>
      echarts.registerMap('japan-prefectures', {{prefectures_geojson}});
      const chart = echarts.init(document.getElementById('map'));
      chart.setOption({{map_config}});
    </script>
  </body>
</html>
```

- [ ] **Step 2: プレースホルダ置換が正しく動くか手動で確認する**

```bash
uv run --project backend python3 -c "
from pathlib import Path
template = Path('backend/templates/map.html').read_text()
html = template.replace('{{prefectures_geojson}}', '{\"type\":\"FeatureCollection\",\"features\":[]}')
html = html.replace('{{map_config}}', '{\"series\":[]}')
assert '{{' not in html
print('OK: プレースホルダが残っていない')
"
```

- [ ] **Step 3: コミットする**

```bash
git add backend/templates/map.html
git commit -m "feat: 地図描画用HTMLテンプレートを追加"
```

---

## Task 4: `render_map` toolの実装

**Files:**
- Modify: `backend/tools.py`

**Interfaces:**
- Consumes:
  - `backend/data/japan_prefectures.geojson`(Task 1)
  - `backend/data/prefecture_points.json`(Task 2)
  - `backend/templates/map.html`(Task 3、プレースホルダ`{{prefectures_geojson}}` `{{map_config}}`)
  - 既存の`_DEFAULT_SERIES_COLORS`(`backend/tools.py`内、既存のデフォルト配色リスト)
- Produces:
  - `MapPoint`(Pydanticモデル): `prefecture: str`, `value: float | None = None`
  - `render_map(points: list[MapPoint], origin: str | None = None, title: str | None = None) -> str`: 完成したHTML文字列を返す`@tool`関数。`backend/main.py`(Task 6)がAgentのtoolsに登録する

- [ ] **Step 1: モジュールレベルのデータ読み込みとモデル・関数を実装する**

`backend/tools.py`の`_CHART_TEMPLATE`の定義の直後に追加:

```python
_MAP_TEMPLATE = (Path(__file__).parent / "templates" / "map.html").read_text()
_PREFECTURES_GEOJSON = (Path(__file__).parent / "data" / "japan_prefectures.geojson").read_text()
_PREFECTURE_POINTS: dict[str, list[float]] = json.loads(
    (Path(__file__).parent / "data" / "prefecture_points.json").read_text()
)

_MAP_NAME = "japan-prefectures"
_LINE_WIDTH_RANGE = (1.0, 12.0)
```

ファイル末尾(`render_chart`関数の後)に追加:

```python
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
                        "lineStyle": {"width": _scale_line_width(p.value, value_min, value_max)},
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
```

- [ ] **Step 2: 手動で正常系を検証する(コロプレスのみ)**

```bash
uv run --project backend python3 -c "
import json
from tools import render_map

html = render_map(
    points=[{'prefecture': '東京都', 'value': 100}, {'prefecture': '大阪府', 'value': 50}],
)
assert 'echarts.registerMap' in html
assert '\"type\": \"map\"' in html.replace(' ', '') or '\"type\":\"map\"' in html.replace(' ', '')
print('OK: choropleth-only HTML生成成功、文字数:', len(html))
"
```

- [ ] **Step 3: 手動で正常系を検証する(流動線あり)**

```bash
uv run --project backend python3 -c "
from tools import render_map

html = render_map(
    points=[{'prefecture': '神奈川県', 'value': 120}, {'prefecture': '埼玉県', 'value': 90}],
    origin='東京都',
    title='テスト地図',
)
assert '\"type\":\"lines\"' in html.replace(' ', '')
assert 'geoIndex' in html
print('OK: 流動線ありHTML生成成功、文字数:', len(html))
"
```

- [ ] **Step 4: 手動で準正常系(未知の都道府県名)を検証する**

```bash
uv run --project backend python3 -c "
from tools import render_map

try:
    render_map(points=[{'prefecture': '東京都(誤記)', 'value': 1}])
    raise SystemExit('エラーが発生しなかった')
except ValueError as e:
    print('OK: ValueErrorが発生:', e)
"
```

- [ ] **Step 5: lintを確認する**

```bash
cd backend && uv run ruff check tools.py
```

- [ ] **Step 6: コミットする**

```bash
git add backend/tools.py
git commit -m "feat: render_mapツールを実装"
```

---

## Task 5: `blocks.py`のtool名判定を一般化

**Files:**
- Modify: `backend/blocks.py`

**Interfaces:**
- Consumes: `render_map`という新しいtool名(Task 4で追加)
- Produces: 変更なし(`Block`の`type`は既存の`"chart"`をそのまま流用するため、`messages_to_blocks`の戻り値の型は変わらない)

- [ ] **Step 1: tool名の判定をハードコードされた1つの定数から集合に変更する**

`backend/blocks.py`の`RENDER_CHART_TOOL_NAME = "render_chart"`を以下に置き換える:

```python
HTML_TOOL_NAMES = {"render_chart", "render_map"}
```

`messages_to_blocks`関数内の使用箇所を変更する:

```python
    chart_tool_use_ids: set[str] = set()
```
は
```python
    html_tool_use_ids: set[str] = set()
```
に変更し、以降の`chart_tool_use_ids`という変数名の出現箇所すべてを`html_tool_use_ids`にリネームする。さらに:

```python
                if content["toolUse"]["name"] == RENDER_CHART_TOOL_NAME:
                    chart_tool_use_ids.add(content["toolUse"]["toolUseId"])
```
を
```python
                if content["toolUse"]["name"] in HTML_TOOL_NAMES:
                    html_tool_use_ids.add(content["toolUse"]["toolUseId"])
```
に、
```python
                if content["toolResult"]["toolUseId"] in chart_tool_use_ids:
```
を
```python
                if content["toolResult"]["toolUseId"] in html_tool_use_ids:
```
に変更する。

- [ ] **Step 2: 手動で検証する**

```bash
uv run --project backend python3 -c "
from blocks import HTML_TOOL_NAMES
assert HTML_TOOL_NAMES == {'render_chart', 'render_map'}
print('OK')
"
```

- [ ] **Step 3: lintを確認する**

```bash
cd backend && uv run ruff check blocks.py
```

- [ ] **Step 4: コミットする**

```bash
git add backend/blocks.py
git commit -m "fix: HTML化するtool名の判定を一般化"
```

---

## Task 6: `main.py`への`render_map`登録とE2E動作確認

**Files:**
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `render_map`(Task 4)
- Produces: なし(アプリケーションの配線のみ)

- [ ] **Step 1: importとAgentのtools登録を変更する**

`backend/main.py`の
```python
from tools import render_chart
```
を
```python
from tools import render_chart, render_map
```
に変更し、
```python
    agent = AGENTS.setdefault(req.session_id, Agent(tools=[render_chart]))
```
を
```python
    agent = AGENTS.setdefault(req.session_id, Agent(tools=[render_chart, render_map]))
```
に変更する。

- [ ] **Step 2: lintを確認する**

```bash
cd backend && uv run ruff check main.py
```

- [ ] **Step 3: バックエンドを起動する**

```bash
cd backend && uv run uvicorn main:app --reload --port 8000
```

(バックグラウンドで起動したままにする)

- [ ] **Step 4: `/api/chat`にcurlで直接リクエストし、コロプレスマップが生成されるか確認する**

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "東京都に100、大阪府に50、北海道に30という数値でコロプレスマップを描いて", "session_id": "test-1"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print([b['type'] for b in d['blocks']])"
```

`['chart']`もしくは`['text', 'chart']`のように`chart`タイプのブロックが含まれることを確認する。

- [ ] **Step 5: 流動線ありのスパイダーマップも確認する**

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "東京都を起点に、神奈川県120、埼玉県90への流動線を地図上に描いて", "session_id": "test-2"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print([b['type'] for b in d['blocks']])"
```

- [ ] **Step 6: ブラウザで実際に見た目を確認する**

```bash
npm --prefix frontend run dev
```

ブラウザで`http://localhost:5173`を開き、Step 4・Step 5と同様の依頼をチャットで送信し、以下を目視確認する:
- コロプレスマップ: 都道府県が値に応じて色分けされている
- スパイダーマップ: 起点から各都道府県へ線が引かれ、値が大きいほど太い
- 凡例(塗り分け/流動線)をクリックしてレイヤーの表示/非表示が切り替わる

- [ ] **Step 7: コミットする**

```bash
git add backend/main.py
git commit -m "feat: render_mapをAgentに登録"
```
