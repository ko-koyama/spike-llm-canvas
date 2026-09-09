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
uv run uvicorn main:app --reload

# frontend (http://localhost:5173)
cd frontend
npm run dev
```

- AWS認証はローカルの認証情報(`aws login`済みのプロファイル)をそのまま利用する
- 会話履歴はプロセス内メモリのみで保持し、永続化しない(サーバー再起動で消える)
- MCP接続・外部サービス認証は無し。Bedrock経由のClaude Sonnetとの会話に、以下のツールを追加している
  - `render_chart`: Chart.jsによる棒グラフ・円グラフなどの描画
  - `render_choropleth`: D3.jsによる都道府県単位の塗り分け地図(コロプレスマップ)の描画
  - `render_spider`: D3.jsによる起点都道府県からの流動線地図(スパイダーマップ)の描画
- これらのツールが生成したグラフ・地図は、発言の流れの中でチャット画面にそのまま表示される
- `backend/data/japan_prefectures.geojson`は`scripts/build_prefecture_geojson.sh`で生成した都道府県ポリゴンデータ(生成手順はスクリプト内コメント参照)

## インフラのセットアップ(S3)

- 可視化HTMLの一時保存に使うS3バケットはTerraformで管理する(`terraform/`)
- tfstate用バケットはTerraform管理外。初回のみ以下のコマンドで手動作成する

  ```sh
  aws s3api create-bucket \
    --bucket spike-llm-canvas-viz-tfstate \
    --region ap-northeast-1 \
    --create-bucket-configuration LocationConstraint=ap-northeast-1
  ```

- データ用バケットの作成・更新

  ```sh
  cd terraform
  terraform init
  terraform apply
  ```

- backend起動前に、作成したバケット名を環境変数に設定する

  ```sh
  export VIZ_S3_BUCKET=spike-llm-canvas-viz
  ```