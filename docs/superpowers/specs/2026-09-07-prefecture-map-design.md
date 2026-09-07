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

1. MLIT国土数値情報から N03(行政区域, shapefile)をダウンロードする
   - 一次ソースから直接取得する(GitHub等のミラー・加工済みデータは使わない)
   - 例: `https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2026/N03-20260101_GML.zip`(令和8年/2026年1月1日時点、全国、約803MB。年ごとにファイル名末尾の日付を変えて配布されており、最新版を使う)
   - 生のshapefile/zipはリポジトリにコミットしない
2. mapshaperで都道府県単位に統合・軽量化する

   ```
   npx mapshaper N03-*.shp \
     -proj wgs84 \
     -dissolve2 fields=N03_001 \
     -rename-fields name=N03_001 \
     -simplify dp 0.3% keep-shapes \
     -simplify dp 2% keep-shapes \
     -clean \
     -o format=geojson precision=0.0001 backend/data/japan_prefectures.geojson
   ```

   - `-proj wgs84`: 座標系をWGS84(緯度経度)に統一
   - `-dissolve2`: 市区町村ポリゴンを都道府県単位に統合
   - `-rename-fields`: 属性名`N03_001`(都道府県名)を`name`に変更
   - `-simplify ... keep-shapes`(2段): 小さい県(香川など)や離島が消えないよう保護しつつ軽量化。simplifyは現在の点数に対する相対的な割合で効くため、同じ値を1回で適用するより2段に分けた方が大きく軽量化できる(実測: 1段目のみで736KB、2段目を追加して27KB。都道府県の輪郭は目視で崩れないことを確認済み)
   - `-clean`: simplify後の不要頂点・ジオメトリ異常を除去
   - `precision=0.0001`: 出力座標の精度を丸めてファイルサイズを削減

   **なぜサイズを詰めたか:** `render_map`の戻り値(GeoJSONを埋め込んだHTML)は、strandsのtool実行結果としてそのままLLMの会話履歴(`agent.messages`)に永続化され、以後のターンでも毎回送信され続ける。736KBのままだと1回の地図生成で約19〜21万トークンをLLM側に消費し、複数回地図を出すセッションではすぐにコンテキスト上限に達する。27KBまで削減することで1回あたり約7千トークンまで抑えられる。なお、この「tool結果が丸ごとLLMコンテキストに残る」という構造自体は解消しておらず、あくまで症状を実用範囲まで軽くする対応である(既知の制約を参照)。
3. 同じ元データから、都道府県名→代表点(緯度経度)の対応表 `backend/data/prefecture_points.json` を作成する
   - スパイダーマップの起点・終点座標に使う代表点(県庁所在地など)であり、ポリゴンの重心ではなく実際の都市座標を使う(参考実装と同じ考え方)
   - これにより実行時にshapelyなどの幾何ライブラリを追加する必要がなくなる
   - このJSONのキー(47都道府県名)が、`render_map`への入力バリデーションの正解データにもなる
4. 前処理の手順は`scripts/`配下にドキュメント化する(スクリプト化は実装時に判断)

**決定事項:** 加工後の`japan_prefectures.geojson`は26,784 bytes(約26KB)となり、リポジトリにコミット済み。当初は752,860 bytes(約735KB)だったが、LLMの会話履歴に毎回乗ってしまう問題(下記「既知の制約」参照)を軽減するため、2段目のsimplifyを追加して縮小した。

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
) -> str:
    """都道府県単位の数値を地図上に塗り分け表示する。originを指定すると流動線も重ねて表示する。"""
```

### 振る舞い

- `origin`未指定 → 塗り分け(コロプレス)のみのシンプルな地図
- `origin`指定 → 塗り分け + 流動線(スパイダー)を1枚のEChartsマップに重ねて表示
  - `origin`から各`points`への線を引き、`value`が大きいほど線を太くする(線幅はmin-max線形補間、参考実装の`wScale`と同等の計算をPython側で行う)
- 色分け(コロプレス)は自前でスケール計算せず、EChartsの`visualMap`コンポーネント(値→色の連続グラデーション)に任せる。ただし色分けの尺度バー(グラデーションの凡例UI)自体は表示しない(`visualMap.show: false`)。地図が主役であり、数値の目盛りは不要という方針のため
- タイトルは表示しない(地図が主役のため、`render_chart`のような`title`引数は持たない)
- 塗り分け・流動線の両レイヤーの表示/非表示切り替えは、ECharts標準の凡例(legend)クリックで行う(カスタムJS・チェックボックスUIは実装しない)

### バリデーション

- `points`または`origin`に未知の都道府県名が指定された場合、明示的なエラーとする(`prefecture_points.json`の47件のキーと照合)
- 準正常系: 未知の都道府県名、`points`が空リストなど

## 実装構成

- `backend/data/japan_prefectures.geojson` — 前処理済み都道府県ポリゴン(dissolve+simplify済み)。26,784 bytes(約26KB)でコミット済み(データパイプライン節を参照)
- `backend/data/prefecture_points.json` — 47都道府県名→代表点(緯度経度)の対応表
- `backend/templates/map.html` — `chart.html`と同構成の新規テンプレート。ECharts CDN読み込み + `{{map_config}}`(EChartsのoption)と`{{prefectures_geojson}}`(GeoJSON文字列)をプレースホルダ置換
- `backend/tools.py` — `MapPoint`モデルと`render_map`関数を追加。geojson/pointsのJSONはモジュールロード時に1回だけ読み込む(`_CHART_TEMPLATE`と同じパターン)
- `backend/blocks.py` — HTML化されるtool名の判定を`"render_chart"`固定から`{"render_chart", "render_map"}`のような集合に一般化する。`Block.type`は既存の`"chart"`をそのまま流用し、フロントエンド(`App.tsx`)は変更不要
- `backend/main.py` — `Agent(tools=[render_chart, render_map])`に追加

## 既知の制約(今回は対応しない)

- `render_map`のtool結果(GeoJSONを埋め込んだHTML)は、strandsの仕組み上そのままLLMの会話履歴(`agent.messages`)に永続化され、以後のターンでも毎回LLMに送信され続ける。GeoJSONを26KBまで軽量化したことで1回あたり約7千トークン程度に抑えているが、構造自体(tool結果が丸ごと履歴に残る)は解消していない。地図を何度も出すセッションでは少しずつ積み重なる点は注意
- 上記と同じ理由で、応答のHTMLサイズ自体も地図を出すたびに大きくなる(フロントエンドのiframe表示にも影響)。キャッシュ/別配信(例: GeoJSONを静的ファイルとして配信し、tool結果には埋め込まない)は必要になった時点で検討する
- 市区町村レベル、複数起点のスパイダーマップは将来拡張として見送る
