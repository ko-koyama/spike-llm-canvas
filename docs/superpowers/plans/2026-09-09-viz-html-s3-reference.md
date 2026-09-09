# 可視化HTMLのS3参照化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tool(render_chart/render_choropleth/render_spider)が生成するHTMLをS3に一時保存し、LLM/会話履歴には軽量なS3オブジェクトキーのみを持たせることで、コンテキストウィンドウ消費を削減する。

**Architecture:** バックエンドのtoolはHTMLをS3にPutObjectしてオブジェクトキーを返す(agent.messagesにはこのキーだけが残る)。フロントへのレスポンスを組み立てる`blocks.py`が、そのキーから都度署名付きURLを発行してフロントに渡す。フロントのiframeはその署名付きURLからHTMLを直接取得して描画する。

**Tech Stack:** Python 3.12 / FastAPI / Strands Agents / boto3(S3) / React 19 + TypeScript / Terraform(AWSプロバイダ)

**Spec:** `docs/superpowers/specs/2026-09-09-viz-html-s3-reference-design.md`

## Global Constraints

- 作業ブランチ`feat/viz-html-s3-reference`上で作業する(mainには直接コミットしない)
- コミットメッセージは`<type>: <説明>`形式、1行、40字程度(本文なし)
- 本リポジトリは技術検証用のため、本機能についてテストは追加しない(仕様書「テスト」節参照)
- S3バケット名(データ用): `spike-llm-canvas-viz`
- S3バケット名(tfstate用、Terraform管理外・手動作成): `spike-llm-canvas-viz-tfstate`
- リージョン: `ap-northeast-1`(Bedrock呼び出し用のデフォルトリージョンとは独立して明示指定する)
- ライフサイクル: データ用バケットのオブジェクトは7日後に自動削除
- 環境変数: `VIZ_S3_BUCKET`(必須)、`VIZ_URL_EXPIRES_SECONDS`(任意、デフォルト`3600`)
- Terraformリソースブロックには目的を1行コメントで記載する(CLAUDE.md規約)
- AWS上に実リソースを作成/変更するコマンド(`aws s3api create-bucket`、`terraform apply`)を実行する前に、必ずユーザーに実行内容を提示し確認を取ること

---

### Task 1: Terraformでデータ用S3バケットを作成する

**Files:**
- Create: `terraform/backend.tf`
- Create: `terraform/main.tf`
- Create: `terraform/outputs.tf`
- Modify: `README.md`(インフラセットアップ手順を追記)

**Interfaces:**
- Produces: S3バケット`spike-llm-canvas-viz`(ap-northeast-1、非公開、7日ライフサイクル、CORS設定済み)。以降のタスクはこのバケット名を`VIZ_S3_BUCKET`環境変数に設定して使う

- [ ] **Step 1: tfstate用バケットを手動作成する(ユーザーに確認の上で実行)**

以下のコマンドを実行する前に、ユーザーに実行内容(バケット新規作成)を提示し確認を取ること。

```bash
aws s3api create-bucket \
  --bucket spike-llm-canvas-viz-tfstate \
  --region ap-northeast-1 \
  --create-bucket-configuration LocationConstraint=ap-northeast-1
```

- [ ] **Step 2: `terraform/backend.tf`を作成する**

```hcl
# Terraform本体とAWSプロバイダのバージョン制約、tfstateの保存先を定義する
terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "spike-llm-canvas-viz-tfstate"
    key    = "spike-llm-canvas-viz/terraform.tfstate"
    region = "ap-northeast-1"
  }
}

# リソースの作成先リージョンを指定する
provider "aws" {
  region = "ap-northeast-1"
}
```

- [ ] **Step 3: `terraform/main.tf`を作成する**

```hcl
# 可視化HTMLの一時保存先バケット
resource "aws_s3_bucket" "viz" {
  bucket = "spike-llm-canvas-viz"
}

# 非公開バケットとし、署名付きURL経由でのみアクセス可能にする
resource "aws_s3_bucket_public_access_block" "viz" {
  bucket = aws_s3_bucket.viz.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 一時保存の位置づけのため、オブジェクトを7日後に自動削除する
resource "aws_s3_bucket_lifecycle_configuration" "viz" {
  bucket = aws_s3_bucket.viz.id

  rule {
    id     = "expire-after-7-days"
    status = "Enabled"

    filter {}

    expiration {
      days = 7
    }
  }
}

# フロントエンドのダウンロード機能がfetchでHTMLを取得できるようGETを許可する
resource "aws_s3_bucket_cors_configuration" "viz" {
  bucket = aws_s3_bucket.viz.id

  cors_rule {
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    allowed_headers = ["*"]
  }
}
```

- [ ] **Step 4: `terraform/outputs.tf`を作成する**

```hcl
# backendの環境変数VIZ_S3_BUCKETに設定する値
output "bucket_name" {
  value = aws_s3_bucket.viz.bucket
}
```

- [ ] **Step 5: `terraform init`を実行する**

Run: `cd terraform && terraform init`
Expected: `Terraform has been successfully initialized!`と表示される(S3バックエンドの初期化に成功)

- [ ] **Step 6: `terraform plan`で作成内容を確認する**

Run: `terraform plan`
Expected: `aws_s3_bucket.viz`、`aws_s3_bucket_public_access_block.viz`、`aws_s3_bucket_lifecycle_configuration.viz`、`aws_s3_bucket_cors_configuration.viz`の4リソースが新規作成(`+ create`)予定として表示される

- [ ] **Step 7: `terraform apply`を実行する(ユーザーに確認の上で実行)**

実行前に、上記planの内容(4リソースの新規作成)をユーザーに提示し確認を取ること。

Run: `terraform apply`
Expected: `Apply complete! Resources: 4 added, 0 changed, 0 destroyed.`、`bucket_name = "spike-llm-canvas-viz"`が出力される

- [ ] **Step 8: バケットが実在することを確認する**

Run: `aws s3 ls | grep spike-llm-canvas-viz`
Expected: `spike-llm-canvas-viz`と`spike-llm-canvas-viz-tfstate`の2つが表示される

- [ ] **Step 9: READMEにインフラセットアップ手順を追記する**

`README.md`の「ディレクトリ構成」のツリーに`terraform/`の行を追加し、「使い方」セクションの後に以下のセクションを追加する。

```markdown
## インフラのセットアップ(S3)

- 可視化HTMLの一時保存に使うS3バケットはTerraformで管理する(`terraform/`)
- tfstate用バケットはTerraform管理外。初回のみ以下のコマンドで手動作成する

  \`\`\`sh
  aws s3api create-bucket \
    --bucket spike-llm-canvas-viz-tfstate \
    --region ap-northeast-1 \
    --create-bucket-configuration LocationConstraint=ap-northeast-1
  \`\`\`

- データ用バケットの作成・更新

  \`\`\`sh
  cd terraform
  terraform init
  terraform apply
  \`\`\`

- backend起動前に、作成したバケット名を環境変数に設定する

  \`\`\`sh
  export VIZ_S3_BUCKET=spike-llm-canvas-viz
  \`\`\`
```

- [ ] **Step 10: コミットする**

```bash
git add terraform/ README.md
git commit -m "feat: 可視化HTML保存用S3バケットを追加"
```

---

### Task 2: `backend/storage.py`を追加し、S3アップロード/署名付きURL発行を実装する

**Files:**
- Create: `backend/storage.py`
- Modify: `backend/pyproject.toml`(`uv add boto3`で追加)

**Interfaces:**
- Consumes: 環境変数`VIZ_S3_BUCKET`(必須)、`VIZ_URL_EXPIRES_SECONDS`(任意、デフォルト`3600`)。Task 1で作成したバケット`spike-llm-canvas-viz`
- Produces:
  - `upload_html(html: str) -> str`: HTMLをS3にアップロードし、オブジェクトキー(`viz/<uuid4>.html`形式)を返す
  - `presign(key: str) -> str`: オブジェクトキーから署名付きGET URLを発行して返す
  - これら2関数はTask 3(`tools.py`)とTask 4(`blocks.py`)から利用される

- [ ] **Step 1: boto3を依存に追加する**

Run: `cd backend && uv add boto3`
Expected: `pyproject.toml`の`dependencies`に`boto3`が追加され、`uv.lock`が更新される

- [ ] **Step 2: `backend/storage.py`を実装する**

```python
"""可視化HTMLをS3に一時保存し、署名付きURLで参照するためのモジュール。"""

import os
import uuid

import boto3

# Bedrock呼び出し用のデフォルトリージョンとは独立して固定する
_REGION = "ap-northeast-1"
_DEFAULT_EXPIRES_SECONDS = 3600

_BUCKET = os.environ.get("VIZ_S3_BUCKET")
if not _BUCKET:
    raise RuntimeError("環境変数VIZ_S3_BUCKETが設定されていません")

_EXPIRES_SECONDS = int(os.environ.get("VIZ_URL_EXPIRES_SECONDS", _DEFAULT_EXPIRES_SECONDS))

_s3 = boto3.client("s3", region_name=_REGION)


def upload_html(html: str) -> str:
    """HTMLをS3にアップロードし、オブジェクトキーを返す。"""
    key = f"viz/{uuid.uuid4()}.html"
    _s3.put_object(
        Bucket=_BUCKET,
        Key=key,
        Body=html.encode("utf-8"),
        ContentType="text/html",
    )
    return key


def presign(key: str) -> str:
    """指定したオブジェクトキーの署名付きGET URLをその場で発行する。"""
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": key},
        ExpiresIn=_EXPIRES_SECONDS,
    )
```

- [ ] **Step 3: ruffでlintを確認する**

Run: `cd backend && uv run ruff check storage.py`
Expected: `All checks passed!`

- [ ] **Step 4: 実際にS3へアップロード・署名URL発行できることを手動確認する**

Run:

```bash
cd backend
export VIZ_S3_BUCKET=spike-llm-canvas-viz
uv run python -c "
import storage
key = storage.upload_html('<html><body>hello</body></html>')
print('key:', key)
url = storage.presign(key)
print('url:', url)
"
```

Expected: `key:`にオブジェクトキー(`viz/....html`)、`url:`に`https://spike-llm-canvas-viz.s3.ap-northeast-1.amazonaws.com/...`形式の署名付きURLが出力される。さらに、出力された`url`をブラウザで開き、`hello`という文字が表示されることを確認する

- [ ] **Step 5: コミットする**

```bash
git add backend/storage.py backend/pyproject.toml backend/uv.lock
git commit -m "feat: S3アップロード/署名付きURL発行を追加"
```

---

### Task 3: `backend/tools.py`の戻り値をHTMLからS3オブジェクトキーに変更する

**Files:**
- Modify: `backend/tools.py:125`(`render_chart`の戻り値)
- Modify: `backend/tools.py:188-189`(`_render_map_html`の戻り値)

**Interfaces:**
- Consumes: Task 2の`storage.upload_html(html: str) -> str`
- Produces: `render_chart`/`render_choropleth`/`render_spider`の戻り値が、HTML文字列から`storage.upload_html()`が返すS3オブジェクトキーに変わる。Task 4の`blocks.py`はこの戻り値(=ToolResultのtext)をS3オブジェクトキーとして扱う

- [ ] **Step 1: `storage`のimportを追加する**

`backend/tools.py`の先頭付近(既存の`from strands import tool`の下)に追加する。

```python
from storage import upload_html
```

- [ ] **Step 2: `render_chart`の戻り値を変更する**

`backend/tools.py:125`を変更する。

```python
# 変更前
    return _CHART_TEMPLATE.replace("{{chart_config}}", json.dumps(config))
```

```python
# 変更後
    html = _CHART_TEMPLATE.replace("{{chart_config}}", json.dumps(config))
    return upload_html(html)
```

- [ ] **Step 3: `_render_map_html`の戻り値を変更する**

`backend/tools.py:188-189`を変更する。

```python
# 変更前
    html = _MAP_TEMPLATE.replace("{{prefectures_geojson}}", _PREFECTURES_GEOJSON)
    return html.replace("{{map_config}}", json.dumps(config))
```

```python
# 変更後
    html = _MAP_TEMPLATE.replace("{{prefectures_geojson}}", _PREFECTURES_GEOJSON)
    html = html.replace("{{map_config}}", json.dumps(config))
    return upload_html(html)
```

- [ ] **Step 4: ruffでlintを確認する**

Run: `cd backend && uv run ruff check tools.py`
Expected: `All checks passed!`

- [ ] **Step 5: コミットする**

```bash
git add backend/tools.py
git commit -m "feat: tool戻り値をS3オブジェクトキーに変更"
```

---

### Task 4: `backend/blocks.py`でS3オブジェクトキーを署名付きURLに変換する

**Files:**
- Modify: `backend/blocks.py`

**Interfaces:**
- Consumes: Task 2の`storage.presign(key: str) -> str`。Task 3で変更した`render_*`ツールの戻り値(S3オブジェクトキー)
- Produces: `Block`モデルの`url`フィールド(旧`html`フィールドから改名)。`main.py`は`messages_to_blocks`の呼び出し方自体は変更不要(戻り値の型は`list[Block]`のまま)

- [ ] **Step 1: `storage`のimportを追加する**

`backend/blocks.py`の先頭付近に追加する。

```python
from storage import presign
```

- [ ] **Step 2: `Block`モデルの`html`フィールドを`url`に変更する**

```python
# 変更前
class Block(BaseModel):
    """チャット表示用の1ブロック(テキストまたはツール結果のHTML)。"""

    type: Literal["text", "chart", "map"]
    variant: str | None = None
    text: str | None = None
    html: str | None = None
```

```python
# 変更後
class Block(BaseModel):
    """チャット表示用の1ブロック(テキストまたはツール結果の可視化URL)。"""

    type: Literal["text", "chart", "map"]
    variant: str | None = None
    text: str | None = None
    url: str | None = None
```

- [ ] **Step 3: `messages_to_blocks`内でオブジェクトキーを署名付きURLに変換する**

```python
# 変更前
            elif "toolResult" in content:
                tool_use_id = content["toolResult"]["toolUseId"]
                info = tool_info_by_id.get(tool_use_id)
                if info:
                    block_type, variant = info
                    html = _extract_text(content["toolResult"])
                    if html:
                        block = Block(type=block_type, variant=variant, html=html)
                        blocks.append(block)
```

```python
# 変更後
            elif "toolResult" in content:
                tool_use_id = content["toolResult"]["toolUseId"]
                info = tool_info_by_id.get(tool_use_id)
                if info:
                    block_type, variant = info
                    key = _extract_key(content["toolResult"])
                    if key:
                        block = Block(type=block_type, variant=variant, url=presign(key))
                        blocks.append(block)
```

- [ ] **Step 4: `_extract_text`を`_extract_key`にリネームする**

```python
# 変更前
def _extract_text(tool_result: ToolResult) -> str | None:
    """ToolResultのcontentからtextを取り出す。"""
    for item in tool_result["content"]:
        if "text" in item:
            return item["text"]
    return None
```

```python
# 変更後
def _extract_key(tool_result: ToolResult) -> str | None:
    """ToolResultのcontentからS3オブジェクトキーを取り出す。"""
    for item in tool_result["content"]:
        if "text" in item:
            return item["text"]
    return None
```

- [ ] **Step 5: ruffでlintを確認する**

Run: `cd backend && uv run ruff check blocks.py`
Expected: `All checks passed!`

- [ ] **Step 6: コミットする**

```bash
git add backend/blocks.py
git commit -m "feat: Blockのhtmlを署名付きURLのurlに変更"
```

---

### Task 5: フロントエンドをURL参照方式に対応させる

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `/api/chat`のレスポンスで、chart/mapブロックが`html`ではなく`url`フィールドを持つようになる(Task 4)

- [ ] **Step 1: `ApiBlock`型を変更する**

`frontend/src/App.tsx:3-6`を変更する。

```tsx
// 変更前
type ApiBlock =
  | { type: 'text'; text: string }
  | { type: 'chart'; variant: string | null; html: string }
  | { type: 'map'; variant: string | null; html: string }
```

```tsx
// 変更後
type ApiBlock =
  | { type: 'text'; text: string }
  | { type: 'chart'; variant: string | null; url: string }
  | { type: 'map'; variant: string | null; url: string }
```

- [ ] **Step 2: `Visualization`型を変更する**

`frontend/src/App.tsx:19-24`を変更する。

```tsx
// 変更前
type Visualization = {
  id: string
  type: VizType
  variant: string | null
  html: string
}
```

```tsx
// 変更後
type Visualization = {
  id: string
  type: VizType
  variant: string | null
  url: string
}
```

- [ ] **Step 3: `splitVisualizations`を変更する**

`frontend/src/App.tsx:159`を変更する。

```tsx
// 変更前
    const viz: Visualization = { id: crypto.randomUUID(), type: b.type, variant: b.variant, html: b.html }
```

```tsx
// 変更後
    const viz: Visualization = { id: crypto.randomUUID(), type: b.type, variant: b.variant, url: b.url }
```

- [ ] **Step 4: `CanvasPanel`のiframeを変更する**

`frontend/src/App.tsx:213`を変更する。

```tsx
// 変更前
        <iframe className="canvas-frame" srcDoc={activeViz.html} sandbox="allow-scripts" />
```

```tsx
// 変更後
        <iframe className="canvas-frame" src={activeViz.url} sandbox="allow-scripts" />
```

- [ ] **Step 5: ダウンロードボタンの呼び出しを非同期対応にする**

`frontend/src/App.tsx:204`を変更する。

```tsx
// 変更前
          <button type="button" className="canvas-panel-download" onClick={() => downloadViz(activeViz, activeIndex)}>
```

```tsx
// 変更後
          <button type="button" className="canvas-panel-download" onClick={() => void downloadViz(activeViz, activeIndex)}>
```

- [ ] **Step 6: `downloadViz`をfetchベースに変更する**

`frontend/src/App.tsx:219-228`を変更する。

```tsx
// 変更前
// 選択中の可視化のHTMLをファイルとしてダウンロードさせる
function downloadViz(viz: Visualization, index: number) {
  const blob = new Blob([viz.html], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${index + 1}_${vizLabel(viz)}.html`
  a.click()
  URL.revokeObjectURL(url)
}
```

```tsx
// 変更後
// 選択中の可視化のHTMLをS3から取得し、ファイルとしてダウンロードさせる
async function downloadViz(viz: Visualization, index: number) {
  const res = await fetch(viz.url)
  const html = await res.text()
  const blob = new Blob([html], { type: 'text/html' })
  const blobUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = `${index + 1}_${vizLabel(viz)}.html`
  a.click()
  URL.revokeObjectURL(blobUrl)
}
```

- [ ] **Step 7: 型チェック・ビルドを確認する**

Run: `cd frontend && npm run build`
Expected: エラーなく`tsc -b && vite build`が完了する

- [ ] **Step 8: コミットする**

```bash
git add frontend/src/App.tsx
git commit -m "feat: 可視化の参照をhtmlからurlに変更"
```

---

### Task 6: エンドツーエンドで動作確認する

**Files:** なし(動作確認のみ)

**Interfaces:**
- Consumes: Task 1〜5で構築した一連の仕組み

- [ ] **Step 1: バックエンドを起動する**

```bash
cd backend
export VIZ_S3_BUCKET=spike-llm-canvas-viz
uv run uvicorn main:app --reload
```

Expected: `http://localhost:8000`で起動し、`curl http://localhost:8000/healthz`が`{"status":"ok"}`を返す

- [ ] **Step 2: フロントエンドを起動する**

```bash
cd frontend
npm run dev
```

Expected: `http://localhost:5173`でチャット画面が表示される

- [ ] **Step 3: ブラウザでグラフ生成を依頼し、表示を確認する**

ブラウザで`http://localhost:5173`を開き、「東京都・大阪府・愛知県の人口を棒グラフにして」のようなメッセージを送信する。

Expected:
- チャット欄に「グラフを表示」ボタン(VizCard)が表示される
- クリックすると右ペインにグラフが表示される
- ブラウザの開発者ツールのNetworkタブで、iframeのリクエスト先が`https://spike-llm-canvas-viz.s3.ap-northeast-1.amazonaws.com/...`(署名付きURL)になっていることを確認する

- [ ] **Step 4: ダウンロード機能を確認する**

右ペインの「ダウンロード」ボタンをクリックする。

Expected: `.html`ファイルがダウンロードされ、開くとグラフが正しく表示される(CORS設定が効いていることの確認を兼ねる)

- [ ] **Step 5: 会話履歴にHTMLが含まれていないことを確認する**

グラフ生成後、バックエンドのプロセスに対して以下を実行し、`agent.messages`に含まれるtool結果がHTML本体ではなくS3オブジェクトキー(短い文字列)であることを確認する。

```bash
# バックエンドのログ、またはPythonの対話環境から確認する例
cd backend
export VIZ_S3_BUCKET=spike-llm-canvas-viz
uv run python -c "
import asyncio
from strands import Agent
from tools import render_chart, render_choropleth, render_spider

async def main():
    agent = Agent(tools=[render_chart, render_choropleth, render_spider])
    await agent.invoke_async('東京都と大阪府の人口を棒グラフにして')
    for m in agent.messages:
        for c in m['content']:
            if 'toolResult' in c:
                for item in c['toolResult']['content']:
                    if 'text' in item:
                        print('tool result text:', item['text'], 'length:', len(item['text']))

asyncio.run(main())
"
```

Expected: `tool result text:`に`viz/....html`という短いS3オブジェクトキーが表示され、`length`が高々数十文字程度(以前のようにHTML全体・GeoJSON全体が含まれる数千〜数万文字にならない)であることを確認する

- [ ] **Step 6: 地図描画(choropleth/spider)についても同様に確認する**

「都道府県別の人口を地図に塗り分けて」のようなメッセージを送信し、Step 3〜5と同様に右ペイン表示・ダウンロード・履歴の軽量化を確認する

このタスクはコード変更を伴わないため、コミットは不要。
