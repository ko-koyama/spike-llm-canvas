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
