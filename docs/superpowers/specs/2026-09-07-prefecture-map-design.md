# 都道府県マップ可視化(コロプレス+スパイダー) 設計

## 背景・目的

- 本リポジトリは、AIチャットからグラフ描画を行うtoolの技術検証(スパイク)である
- これまで折れ線・棒・散布図・円グラフ(`render_chart`)を実装済み
- 位置情報系データの可視化として、地図上での可視化(コロプレスマップ・スパイダーマップ)を追加する
- 参考イメージ: `reference/spider_map_tokyo.html`(市区町村単位・東京都内の来訪者居住地分析)。ただし今回はまず**都道府県単位**から着手する

## スコープ

**やること**

- 都道府県単位のGeoJSONを用意し、値に応じた塗り分け(コロプレスマップ)を行う
- 起点(`origin`)を指定した場合、そこから各都道府県への流動線(スパイダーマップ)を重ねて表示する
- 既存の`render_chart`と同じ設計思想(Pydanticモデル + テンプレートHTML埋め込み)で`render_map`という1つのtoolとして実装する

**やらないこと(YAGNI、将来拡張候補)**

- 市区町村単位への対応
- 複数起点のスパイダーマップ
- 参考実装にあったランキングパネルや詳細な凡例UIの作り込み(地図そのものが主役のため)
- GeoJSON埋め込みによるレスポンスサイズ増大への対策(キャッシュ・別配信など)
- テストコード(本リポジトリは検証用のため、今回のtoolについてはテスト作成を省略する)

## データパイプライン(ビルド時の前処理、実行時には関与しない)

1. MLIT国土数値情報から N03(行政区域, shapefile)をダウンロード(手動、更新頻度は低い想定)
2. mapshaperで都道府県単位に統合・軽量化する

   ```
   npx mapshaper N03-*.shp \
     -dissolve2 fields=N03_001 \
     -simplify dp 5% keep-shapes \
     -o format=geojson backend/data/japan_prefectures.geojson
   ```

   - `-dissolve2`: 市区町村ポリゴンを都道府県単位に統合
   - `-simplify ... keep-shapes`: 小さい県(香川など)や離島が消えないよう保護しつつ軽量化
3. 同じ元データから、都道府県名→代表点(緯度経度)の対応表 `backend/data/prefecture_points.json` を作成する
   - スパイダーマップの起点・終点座標に使う代表点(県庁所在地など)であり、ポリゴンの重心ではなく実際の都市座標を使う(参考実装と同じ考え方)
   - これにより実行時にshapelyなどの幾何ライブラリを追加する必要がなくなる
   - このJSONのキー(47都道府県名)が、`render_map`への入力バリデーションの正解データにもなる
4. 前処理の手順は`scripts/`配下にドキュメント化する(スクリプト化は実装時に判断)

## tool設計

`render_chart`と同じ構造(Pydanticモデル + `@tool`関数)で、`render_map`という新規toolを追加する。

```python
class MapPoint(BaseModel):
    """地図上の1地点(都道府県名で指定)。"""

    prefecture: str  # 都道府県名(例: "東京都")。47都道府県のリストと照合する
    value: float | None = None  # 塗り分けの濃淡、および流動線の太さに使う数値


@tool
def render_map(
    points: list[MapPoint],
    origin: str | None = None,  # 指定すると、originから各pointへの流動線レイヤーを重ねて表示する
    title: str | None = None,
) -> str:
    """都道府県単位の数値を地図上に塗り分け表示する。originを指定すると流動線も重ねて表示する。"""
```

### 振る舞い

- `origin`未指定 → 塗り分け(コロプレス)のみのシンプルな地図
- `origin`指定 → 塗り分け + 流動線(スパイダー)を1枚のEChartsマップに重ねて表示
  - `origin`から各`points`への線を引き、`value`が大きいほど線を太くする(線幅はmin-max線形補間、参考実装の`wScale`と同等の計算をPython側で行う)
- 色分け(コロプレス)は自前でスケール計算せず、EChartsの`visualMap`コンポーネント(値→色の連続グラデーション)に任せる
- 塗り分け・流動線の両レイヤーの表示/非表示切り替えは、ECharts標準の凡例(legend)クリックで行う(カスタムJS・チェックボックスUIは実装しない)

### バリデーション

- `points`または`origin`に未知の都道府県名が指定された場合、明示的なエラーとする(`prefecture_points.json`の47件のキーと照合)
- 準正常系: 未知の都道府県名、`points`が空リストなど

## 実装構成

- `backend/data/japan_prefectures.geojson` — 前処理済み都道府県ポリゴン(dissolve+simplify済み)
- `backend/data/prefecture_points.json` — 47都道府県名→代表点(緯度経度)の対応表
- `backend/templates/map.html` — `chart.html`と同構成の新規テンプレート。ECharts CDN読み込み + `{{map_config}}`(EChartsのoption)と`{{prefectures_geojson}}`(GeoJSON文字列)をプレースホルダ置換
- `backend/tools.py` — `MapPoint`モデルと`render_map`関数を追加。geojson/pointsのJSONはモジュールロード時に1回だけ読み込む(`_CHART_TEMPLATE`と同じパターン)
- `backend/blocks.py` — HTML化されるtool名の判定を`"render_chart"`固定から`{"render_chart", "render_map"}`のような集合に一般化する。`Block.type`は既存の`"chart"`をそのまま流用し、フロントエンド(`App.tsx`)は変更不要
- `backend/main.py` — `Agent(tools=[render_chart, render_map])`に追加

## 既知の制約(今回は対応しない)

- GeoJSONを応答ごとに毎回埋め込むため、地図を出すたびにHTMLサイズが増える(概算で数百KB程度を想定)。キャッシュ/別配信は必要になった時点で検討する
- 市区町村レベル、複数起点のスパイダーマップは将来拡張として見送る
