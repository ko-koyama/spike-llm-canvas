# spike-llm-canvas

Strands Agentのtool useを使った、チャット上でのグラフ描画などを検証するリポジトリ

## ディレクトリ構成

```
.
├── .devcontainer/          # Dev Container設定
├── .github/
│   └── workflows/          # CI
├── .pre-commit-config.yaml # pre-commitフック設定
├── .vscode/                # VSCode設定
├── .claude/                # Claude Code設定
├── CLAUDE.md               # Claude Code向けの開発ルール
├── backend/                # FastAPI + Strands Agent
├── frontend/               # React + Vite製のチャット画面
├── scripts/                # 都道府県GeoJSONデータの生成スクリプト(ビルド時のみ使用)
└── terraform/              # S3バケットなどのインフラ定義
```

## 使い方

```sh
# backend (http://localhost:8000)
cd backend
export VIZ_S3_BUCKET=spike-llm-canvas-viz
uv run uvicorn main:app --reload

# frontend (http://localhost:5173)
cd frontend
npm run dev
```

- AWS認証はローカルの認証情報(`aws login`済みのプロファイル)をそのまま利用する
- 会話履歴はプロセス内メモリのみで保持し、永続化しない(サーバー再起動で消える)
- MCP接続・外部サービス認証は無し。Bedrock経由のClaude Sonnetとの会話に、以下のツールを追加している
  - `render_chart`: Chart.jsによる棒グラフ・円グラフなどの描画
  - `render_choropleth`: Leafletによる都道府県/市区町村単位の塗り分け地図(コロプレスマップ)の描画
  - `render_spider`: Leafletによる任意地点(緯度経度)を起点とした流動線地図(スパイダーマップ)の描画
- これらのツールが生成したグラフ・地図は、発言の流れの中でチャット画面にそのまま表示される
- 生成したHTMLはコンテキストの肥大化を防ぐためS3に一時保存し、表示時に署名付きURLを発行する(バケット名は`VIZ_S3_BUCKET`で指定。セットアップ手順は後述)
- `backend/data/japan_{prefectures,municipalities}.geojson`・`{prefecture,municipality}_points.json`は`scripts/build_geojson.sh <level>`で生成した行政区画ポリゴン・代表点データ(生成手順はスクリプト内コメント参照)
- 市区町村レベル(`municipality`)のデータ生成には、e-Stat「令和2年国勢調査 小地域集計」境界データが必要
  - https://www.e-stat.go.jp/gis/statmap-search?page=1&type=2&aggregateUnitForBoundary=A&toukeiCode=00200521&toukeiYear=2020&serveyId=A002005212020&datum=2000 から都道府県ごとにダウンロード(形式: shapefile、座標系: 世界測地系緯度経度)
  - ダウンロードしたzip(リネーム不要)をリポジトリ直下の`shapefile/`に配置してから`./scripts/build_geojson.sh municipality`を実行する(`shapefile/`は`.gitignore`対象でコミットしない)

## セットアップ(インフラ)

- 生成したHTMLの一時保存に使うS3バケットはTerraformで管理する(`terraform/`)
- tfstate用バケットは以下コマンドで手動作成する

  ```sh
  aws s3api create-bucket \
    --bucket spike-llm-canvas-viz-tfstate \
    --region ap-northeast-1 \
    --create-bucket-configuration LocationConstraint=ap-northeast-1
  ```
- backend起動前に、作成したバケット名を環境変数に設定する

  ```sh
  export VIZ_S3_BUCKET=spike-llm-canvas-viz
  ```