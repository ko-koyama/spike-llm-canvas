# 市区町村レベル地図可視化 対応 設計書

## 背景・目的

- 現状、`render_choropleth`/`render_spider`は都道府県単位のみに対応している
- 市区町村単位でも同様の可視化を行いたい。将来的には町丁目単位にも拡張予定
- 拡張のたびにツールを増やすのではなく、既存ツールを`level`パラメータで一般化することでDRY/YAGNIに沿った拡張を可能にする

## アーキテクチャ

### データ生成(`scripts/build_geojson.sh`、既存の`build_prefecture_geojson.sh`を置き換え)

第1引数で`level`(`prefecture`|`municipality`)を受け取る。levelごとにデータソースと生成経路が異なる。

**`prefecture`(現行どおり、MLIT N03を使用)**

- MLIT国土数値情報(N03、行政区域データ)を`curl`でダウンロードし、`N03_001`(都道府県名)で`dissolve2`する
- simplifyは`-clean`をdissolve直後・simplify後の2箇所で行い、`-simplify dp 0.02% keep-shapes`で簡略化する(実装時の検証で、`-clean`をsimplifyの後だけに置くとmapshaperの自己交差解消が失敗し出力が肥大化する不具合を確認済みのため、この順序を必須とする)
- 出力: `backend/data/japan_prefectures.geojson`(47件、目安数十KB)

**`municipality`(e-Statの小地域(町丁・字等)境界データを使用。N03には政令指定都市の区の境界が含まれていないため)**

- MLIT N03には政令指定都市の区(例: 横浜市中区)の境界が独立したポリゴンとして存在しない(実データで確認済み: `N03_004`が区によらず市名のまま)ため、区を区別できるデータソースに切り替える
- データソース: 「令和2年国勢調査 小地域集計」の境界データ(e-Stat 統計地理情報システム、都道府県ごとにshapefile形式・世界測地系緯度経度でダウンロード)。属性に`PREF_NAME`(都道府県名)・`CITY_NAME`(市区町村名。政令指定都市は区名まで含む。例: `"札幌市中央区"`)を持つ
- このデータは本来、町丁目(`S_NAME`)単位の細かい境界データだが、`PREF_NAME`+`CITY_NAME`で`dissolve2`することで市区町村(区を含む)レベルのポリゴンが得られる。将来の町丁目レベル対応でも同じデータソースをそのまま(集約せずに)使える想定
- 取得方法: e-Statの境界データダウンロードは公式APIがなく認証不要の手動ダウンロードのみのため、**ユーザーが手動で47都道府県分をダウンロードし、`shapefile/`配下にzipのまま(リネーム不要)配置する**。このディレクトリはビルド時の入力素材のみでサイズが大きいため`.gitignore`対象とし、コミットしない
- ビルドスクリプトは`shapefile/*.zip`(または展開済みディレクトリ)をすべて展開し、`combine-files`で1レイヤーに結合してから`dissolve2 fields=PREF_NAME,CITY_NAME`する。ファイル名から都道府県を判定する必要はない(`PREF_NAME`属性で判別できるため)
- 出力: `backend/data/japan_municipalities.geojson`(政令指定都市の区を含む市区町村単位、目安数MB)

**共通(levelによらず)**

- 結合後の地域名(`name`プロパティ)は、dissolveに使ったフィールドを連結した文字列(`prefecture`は`N03_001`そのもの、`municipality`は`PREF_NAME`+`CITY_NAME`。例: `"東京都府中市"`, `"神奈川県横浜市中区"`)。この文字列が`tools.py`側の検索キーと一致する
- 生成したポリゴンから各地域の代表点(重心)を計算し、`backend/data/prefecture_points.json` / `municipality_points.json`として出力する
  - 従来手打ちだった`prefecture_points.json`もこの自動生成に置き換える
  - 離島を含む都道府県(沖縄県、東京都、長崎県、鹿児島県など)で重心がポリゴン外や不自然な位置にならないか実装時に確認する。問題があれば該当地域のみ個別に座標を上書きする対応を検討する

### `backend/tools.py`

- `LevelName = Literal["prefecture", "municipality"]`を定義
- `MapPoint`を拡張する
  ```python
  class MapPoint(BaseModel):
      prefecture: str  # 都道府県名(例: "東京都")
      municipality: str | None = Field(
          default=None,
          description=(
              "市区町村名。levelが'municipality'の場合のみ指定する(例: '府中市')。"
              "政令指定都市の区を指定する場合は区名まで含める(例: '横浜市中区')"
          ),
      )
      value: float | None = None
  ```
- `render_choropleth(level: LevelName, points: list[MapPoint])`
- `render_spider(level: LevelName, origin_lat: float, origin_lon: float, points: list[MapPoint])`
  - `origin`は行政区画に紐づけず緯度経度で直接指定する(施設を起点にしたスパイダーマップなど、行政区画の中心点に限らない任意の地点をサポートするため)
  - 既存の「originと同名のpointを除外する」フィルタは、originが行政区画に紐づかなくなるため不要になり削除する
- levelごとのデータ管理
  - `_LEVEL_FILES: dict[LevelName, tuple[str, str]]`でgeojson/pointsファイル名を定義する
  - `_LevelData`をdataclassで定義し(`geojson: dict`(パース済みFeatureCollection), `points: dict[str, list[float]]`)、モジュールロード時に全level分を読み込む(既存のfail-fast方針を踏襲)
  - `_point_key(level, prefecture, municipality)`で検索キーを生成する(`prefecture`レベルは`prefecture`そのまま、`municipality`レベルは`prefecture`+`municipality`を連結)
- 埋め込むGeoJSONの絞り込み: `municipality`レベルは常に`points`で指定された地域(最大50件)のポリゴンのみをHTMLに埋め込む。全国約1,900件を毎回埋め込むと(政令指定都市の区を含む詳細な境界のため)サイズが大きくブラウザの描画負荷も高いためで、`points`が最大50件までに制限されていることとも整合する。この場合、埋め込んだ地図には指定地域以外の行政境界は表示されない(全国の中でどこにあるかという地理的文脈は失われる)。`prefecture`レベルは47件のみで軽量なため、従来通り全国分をそのまま埋め込み、値のない地域もグレー表示で地図に含める
  - `_validate_map_points(level, points)`、`_render_map_html(mode, level, points, origin)`をlevel対応に更新する

### `backend/templates/map_leaflet.html`

- プレースホルダ`{{prefectures_geojson}}`を`{{regions_geojson}}`に改名する(都道府県専用ではなくなるため)
- `drawPrefectures`/`prefectureLayer`など都道府県前提の命名を汎用的な名前(`drawRegions`/`regionLayer`等)に変更する

### 変更しないもの

- `backend/main.py`: 利用するツール(`render_chart`/`render_choropleth`/`render_spider`)は変わらないため変更不要
- `frontend/`: `level`を意識せず受け取ったviz URLを表示するだけのため変更不要

## データフロー

1. ユーザー発言をもとにLLMが`level`を判断し、`render_choropleth`/`render_spider`を呼び出す
2. `tools.py`が`level`に応じたGeoJSON/座標辞書(`_LEVEL_DATA[level]`)を選び、`MapPoint`を検証・座標解決する
3. 以降のHTML生成・S3アップロード・フロントエンド表示は既存フローと同じ

## スコープ

- 今回対応するのは市区町村レベルまで。町丁目レベルは対象外(将来、同じ仕組みで`level`に`"town"`を追加する形で拡張する想定)
- 政令指定都市の区は市区町村レベルの一区分として扱う(`municipality`フィールドに区名まで含めて指定する)
- 市区町村レベルの`points`は最大50件までとする。超える場合は`_validate_map_points`が`ValueError`を送出する(市区町村数が多く、地図上に大量表示すると視認性・描画負荷の両面で実用に耐えないため)。都道府県レベルは47件で収まるため上限を設けない

## テスト

- 本リポジトリは技術検証用のため自動テストは追加しない
- 実装時、Playwrightでの動作確認(コロプレス・スパイダーそれぞれ都道府県/市区町村レベル、離島を含む地域の座標の妥当性)を行う

## スコープ外(将来検討)

- 町丁目レベルへの対応
- `origin`を行政区画名でも指定できるようにする拡張(LLMが緯度経度をうまく設定できない場合に検討する)
- 重心計算で座標がおかしくなる地域が見つかった場合の、個別対応の仕組み化
- 都道府県レベルのデータソースをMLIT N03からe-Statの境界データに統一すること。市区町村レベルと同じソース・同じ緩い簡略化率に揃えることで一貫性を持たせる狙いだが、今回はMLIT N03ベース(修正済みで動作している)のまま据え置き、次のステップとして別途対応する
