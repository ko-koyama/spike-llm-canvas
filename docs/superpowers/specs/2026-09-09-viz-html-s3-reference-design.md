# 可視化HTMLのS3参照化によるコンテキストウィンドウ削減 設計書

## 背景・目的

- 現状、`render_chart`/`render_choropleth`/`render_spider`は生成したHTML文字列をそのままToolResultとして返している
- StrandsのAgentはセッションごとに会話履歴(`agent.messages`)をメモリ上に保持し続けるため、生成されたHTML(特に地図はGeoJSONを埋め込むため大きい)がそのまま履歴に残り、以降の全ターンでLLMへの入力として再送信され続け、コンテキストウィンドウとトークンコストを圧迫している
- 本設計では、生成したHTMLをS3に一時保存し、LLM/会話履歴には軽量な参照(S3オブジェクトキー)のみを持たせることでこれを解消する
- 本リポジトリは技術検証用であり、ここでの検証結果は将来的に会話履歴管理を備えた別のAIチャットアプリへ移植予定

## アーキテクチャ

### `backend/storage.py`(新規)

- `upload_html(html: str) -> str`: HTMLをS3にPutObjectし、オブジェクトキー(例: `viz/<uuid4>.html`)を返す
  - アップロード時に`ContentType: text/html`、`ContentDisposition: attachment; filename="..."`を設定する(フロントのダウンロード機能で利用)
- `presign(key: str) -> str`: 指定キーに対する署名付きGET URLをその場で生成して返す
- 環境変数
  - `VIZ_S3_BUCKET`(必須): 保存先バケット名。未設定時はモジュールimport時に`RuntimeError`(既存のテンプレート読み込みと同じfail-fast方針)
  - `VIZ_URL_EXPIRES_SECONDS`(任意、デフォルト`3600`): 署名付きURLの有効期限。都度発行するURLは「今の応答を表示するのに十分な時間」であればよく、S3のオブジェクト保持期間と一致させる必要はない
- S3クライアントは`region_name="ap-northeast-1"`を明示指定する(Bedrock呼び出しに使うデフォルトリージョンとは独立)

### `backend/tools.py`

- `render_chart`/`render_choropleth`/`render_spider`の戻り値を、HTML文字列から`storage.upload_html()`が返す**S3オブジェクトキー**に変更する
- HTML生成ロジック自体(テンプレート埋め込み)は変更しない

### `backend/blocks.py`

- `Block.html`フィールドを`Block.url`にリネーム
- `messages_to_blocks`内で、ToolResultから取り出した値(S3オブジェクトキー)を`storage.presign(key)`に渡し、署名付きURLに変換してから`Block.url`にセットする
  - つまり、署名付きURLは「会話履歴には残らず、そのターンのレスポンスを組み立てる際に都度その場で発行される」

### `frontend/src/App.tsx`

- `Visualization.html`を`Visualization.url`にリネーム
- `CanvasPanel`のiframeを`srcDoc={activeViz.html}`から`src={activeViz.url}`に変更(`sandbox="allow-scripts"`は維持)
- ダウンロード機能: クライアント側での`Blob`生成ロジックを廃止し、`url`への遷移(新規タブで開く、または`<a href={url}>`)に置き換える。ダウンロードとして扱われるかはS3オブジェクトの`ContentDisposition: attachment`ヘッダに委ねる

## データフロー

1. ユーザー発言を`agent.invoke_async`で送信
2. LLMが`render_chart`等を呼び出し、既存ロジックでHTML文字列を生成
3. `storage.upload_html(html)`でS3にPutObjectし、オブジェクトキーを返す
4. toolの戻り値(オブジェクトキー、短い文字列)が`agent.messages`に記録される。以降のターンでLLMに再送信されるのはこの短い文字列のみ
5. `blocks.py`の`messages_to_blocks`が今回ターンの新規メッセージからToolResult(オブジェクトキー)を取り出し、`storage.presign(key)`で署名付きURLを都度生成して`Block(type, variant, url)`を作る
6. `main.py`が`ChatResponse(blocks=...)`としてフロントエンドに返す
7. フロントエンドは`iframe src={url}`でS3から直接HTMLを取得して描画する

## インフラ(Terraform)

- `terraform/`配下にデータ保存用S3バケット(`spike-llm-canvas-viz`、リージョン`ap-northeast-1`)のみを定義する
  - パブリックアクセスブロックを有効化(非公開バケット。アクセスは署名付きURL経由のみ)
  - ライフサイクルルールで7日後にオブジェクトを自動削除する
  - 各リソースブロックには目的を1行コメントで記載する(CLAUDE.mdのTerraform規約)
- tfstate用バケット(`spike-llm-canvas-viz-tfstate`、リージョン`ap-northeast-1`)はTerraform管理対象外とし、aws CLIで手動作成する。作成手順はREADMEに記載する
  - Terraformの`backend "s3"`ブロックでこの手動作成済みバケットを参照する
  - bootstrap用の別Terraform構成は作らない

## 設定・依存関係

- `backend/pyproject.toml`に`boto3`を直接依存として追加する(`uv add boto3`)
- 環境変数: `VIZ_S3_BUCKET`(必須)、`VIZ_URL_EXPIRES_SECONDS`(任意、デフォルト`3600`)
- READMEに以下を追記する
  - tfstateバケットの手動作成コマンド例
  - `terraform apply`の実行手順
  - `VIZ_S3_BUCKET`等の環境変数の設定方法

## エラーハンドリング

- `VIZ_S3_BUCKET`未設定時はモジュールimport時に`RuntimeError`を送出する(fail-fast)
- S3アップロード/署名付きURL生成に失敗した場合は例外をそのまま送出する。strandsが既存の入力検証エラー(例: 未知の都道府県名)と同様にtoolエラーとしてLLMに返す

## テスト

- 本リポジトリは技術検証用のため、本機能についてもテストは追加しない

## スコープ外(将来の移植先アプリで検討する事項)

- 会話履歴を永続化した場合の、古いメッセージ再表示時における「キー→署名付きURLの再発行」の実装
- S3署名に使う認証情報の長期化(専用IAMユーザーの導入など)の要否。本リポジトリでは`aws login`済みのSSOプロファイルをそのまま利用し、その有効期限は考慮しない
