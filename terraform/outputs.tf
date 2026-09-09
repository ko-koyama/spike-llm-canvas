# backendの環境変数VIZ_S3_BUCKETに設定する値
output "bucket_name" {
  value = aws_s3_bucket.viz.bucket
}
