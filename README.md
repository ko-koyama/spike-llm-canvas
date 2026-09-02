# python-template

Pythonプロジェクトのテンプレートリポジトリ

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
├── .python-version         # Pythonバージョン指定
├── pyproject.toml          # プロジェクト設定・パッケージ管理
├── uv.lock                 # パッケージのロックファイル
├── src/                    # ソースコード
│   └── main.py
└── tests/                  # テストコード
    └── test_main.py
```

## 各ディレクトリ・ファイルの役割

### `.devcontainer/`

- 役割
  - VSCode Dev Containers用の開発環境定義
  - `devcontainer.json`でPython 3.12・Node 24・aws-cli・terraform・gh cli・claude-codeをfeaturesとして導入
  - コンテナ作成後に`post-create.sh`が実行され、uv・gitleaksのインストール、依存パッケージの同期（`uv sync`）、pre-commitフックの有効化を行う
  - `features`にはdevcontainers公式・各ソフトウェア公式が提供するものだけを使う方針（uv・gitleaksのように公式featureがないツールは`post-create.sh`側でインストール）
  - `mounts`でaws-cli・Claude Code・gh cliの認証情報をnamed volumeとしてマウントし、コンテナを作り直しても再ログイン不要になるようにしている
- プロジェクトごとに変更すべき箇所
  - `name`をプロジェクト名に変更
  - 不要な`features`（aws-cli、terraformなど、インフラを扱わないプロジェクトでは不要）を削除
  - 使わない`features`を削除した場合は対応する`mounts`（aws-config、gh-configなど）も削除
  - 使用するVSCode拡張機能（`customizations.vscode.extensions`）をプロジェクトの技術スタックに合わせて取捨選択
  - Pythonのバージョンを変える場合は`features`内のバージョン指定と`.python-version`を揃えて変更

### `.github/workflows/ci.yml`

- 役割
  - push・PR時にruffによるlint/フォーマットチェックとpytestを実行するCI
- プロジェクトごとに変更すべき箇所
  - デプロイなど追加のジョブが必要な場合は追記

### `.pre-commit-config.yaml`

- 役割
  - gitleaksによるコミット前の機密情報スキャン
- プロジェクトごとに変更すべき箇所
  - 他のpre-commitフック（例: ruff）を追加する場合はここに追記

### `.vscode/`

- 役割
  - VSCode用のワークスペース設定
  - 保存時のruff自動整形、pytestをテストランナーとして使う設定、`src/`をインポート解決に追加する設定が入っている
- プロジェクトごとに変更すべき箇所
  - `src/`ディレクトリ名を変更・廃止した場合は`python.analysis.extraPaths`のパスも合わせて変更

### `.claude/` / `CLAUDE.md`

- 役割
  - Claude Code向けの設定・開発ルール一式
  - `.claude/settings.json`: 実際の設定（権限・フック）
    - `permissions.ask`: `git push`・`terraform apply/destroy`・`gh pr merge`など取り消しにくい操作は実行前に確認
    - `permissions.deny`: `.env`・`.tfstate`・`.tfvars`など機密情報を含むファイルの読み取りを禁止
    - `hooks.PostToolUse`: Pythonファイル編集後に自動で`ruff format`＋`ruff check --fix`
    - `hooks.PreToolUse`: `git commit`前にサブエージェントがステージ差分の機密情報混入をチェック
    - `enabledPlugins`: `aws-core`・`superpowers`プラグインを有効化（`post-create.sh`でマーケットプレイス登録・インストールを実行）
  - `CLAUDE.md`: 開発原則（YAGNI/KISS/DRY）、日本語での会話、ブランチ/コミット運用ルール、テスト方針を定義
- プロジェクトごとに変更すべき箇所
  - インフラを扱わないプロジェクトでは`terraform apply/destroy`の`ask`設定や`.tfstate`/`.tfvars`の`deny`設定を削除可
  - 不要な`enabledPlugins`があれば削除し、`post-create.sh`側の対応するインストール処理も削除
  - `CLAUDE.md`にプロジェクト固有のルールがあれば追記（ブランチ戦略など）

### `.python-version` / `pyproject.toml` / `uv.lock`

- 役割
  - `uv`によるPythonバージョン・パッケージ管理
  - `pyproject.toml`にはプロジェクトのメタ情報（`name`など）、依存パッケージ、ruff/pytestの設定が入っている
- プロジェクトごとに変更すべき箇所
  - `[project]`の`name`をプロジェクト名に変更
  - 依存パッケージの追加・削除は`pyproject.toml`を直接編集せず`uv add`/`uv remove`を使う（CLAUDE.md参照）
  - Pythonバージョンを変える場合は`.python-version`と`requires-python`を揃えて変更

