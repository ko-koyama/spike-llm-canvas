# spike-llm-canvas

Strands Agent を使ったシンプルなAIチャットの検証用リポジトリ

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
└── frontend/               # React + Vite製のチャット画面
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
- ツール・MCP接続・認証は無し。Bedrock経由のClaude Sonnetとの素の会話のみ