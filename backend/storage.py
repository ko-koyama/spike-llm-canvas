"""可視化HTMLをS3に一時保存し、署名付きURLで参照するためのモジュール。"""

import os
import uuid

import boto3
from botocore.config import Config

# Bedrock呼び出し用のデフォルトリージョンとは独立して固定する
_REGION = "ap-northeast-1"
_DEFAULT_EXPIRES_SECONDS = 3600

_BUCKET = os.environ.get("VIZ_S3_BUCKET")
if not _BUCKET:
    raise RuntimeError("環境変数VIZ_S3_BUCKETが設定されていません")

_EXPIRES_SECONDS = int(
    os.environ.get("VIZ_URL_EXPIRES_SECONDS", _DEFAULT_EXPIRES_SECONDS)
)

_s3 = boto3.client(
    "s3",
    region_name=_REGION,
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)


def upload_html(html: str) -> str:
    """HTMLをS3にアップロードし、オブジェクトキーを返す。"""
    key = f"viz/{uuid.uuid4()}.html"
    try:
        _s3.put_object(
            Bucket=_BUCKET,
            Key=key,
            Body=html.encode("utf-8"),
            ContentType="text/html; charset=utf-8",
        )
    except Exception as e:
        # AWSのエラー詳細をLLM/ユーザーに渡さないよう汎用メッセージに変換する
        raise ValueError("データの可視化に失敗しました") from e
    return key


def presign(key: str) -> str:
    """指定したオブジェクトキーの署名付きGET URLをその場で発行する。"""
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": key},
        ExpiresIn=_EXPIRES_SECONDS,
    )
