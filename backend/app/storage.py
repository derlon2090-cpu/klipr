from pathlib import Path
import boto3
from botocore.config import Config
from .config import get_settings


class StorageUnavailable(RuntimeError):
    """Raised when the media object store has not been configured."""


def r2_client():
    s = get_settings()
    if not all([s.r2_endpoint_url, s.r2_access_key_id, s.r2_secret_access_key]):
        raise StorageUnavailable("S3-compatible storage credentials are not configured")
    return boto3.client("s3", endpoint_url=s.r2_endpoint_url, region_name=s.r2_region,
        aws_access_key_id=s.r2_access_key_id, aws_secret_access_key=s.r2_secret_access_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))


def upload_file(path: Path, key: str, content_type: str = "video/mp2t") -> None:
    r2_client().upload_file(str(path), get_settings().r2_bucket, key, ExtraArgs={"ContentType": content_type})


def download_file(key: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    r2_client().download_file(get_settings().r2_bucket, key, str(destination))


def copy_file(source_key: str, destination_key: str) -> None:
    """Create an independent R2 snapshot so later preset changes stay isolated."""
    settings = get_settings()
    r2_client().copy_object(
        Bucket=settings.r2_bucket,
        CopySource={"Bucket": settings.r2_bucket, "Key": source_key},
        Key=destination_key,
    )


def presigned_download_url(key: str) -> str:
    settings = get_settings()
    return r2_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket, "Key": key},
        ExpiresIn=settings.r2_presigned_url_ttl_seconds,
    )

def delete_files(keys: list[str]) -> None:
    """R2 batch deletion; caller filters null keys before this point."""
    if keys: r2_client().delete_objects(Bucket=get_settings().r2_bucket, Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True})
