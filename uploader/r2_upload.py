"""
Cloudflare R2 uploader — stores videos in cloud object storage.

R2 is Cloudflare's S3-compatible storage service. We use boto3
(the AWS SDK) to talk to it because R2 speaks the S3 API.
The only difference is the endpoint URL.

After uploading, the file is publicly accessible at:
  {R2_PUBLIC_URL}/{filename}

If R2 credentials aren't configured, all functions return None
and print a message — the pipeline continues without uploading.
"""

import os

import config


def _get_client():
    """
    Create a boto3 S3 client configured for Cloudflare R2.

    Returns the client, or None if credentials aren't set.
    boto3 is imported here (not at module level) so the rest
    of the codebase doesn't crash if boto3 isn't installed yet.
    """
    if not all([config.R2_ACCOUNT_ID, config.R2_ACCESS_KEY_ID,
                config.R2_SECRET_ACCESS_KEY, config.R2_BUCKET_NAME]):
        print("  R2 not configured — skipping upload")
        return None

    import boto3

    # R2's S3-compatible endpoint uses your account ID.
    # This is the only difference from regular S3 — everything
    # else (auth, API calls, etc.) works identically.
    endpoint = f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        # R2 doesn't use regions, but boto3 requires one.
        # "auto" tells R2 to figure it out.
        region_name="auto",
    )


def upload_video(local_path, filename):
    """
    Upload a video file to R2 and return its public URL.

    Args:
        local_path: Path to the local .mp4 file
        filename: What to name it in the bucket (e.g. "2026-03-20.mp4")

    Returns:
        Public URL string, or None if upload failed/skipped.
    """
    client = _get_client()
    if not client:
        return None

    print(f"  Uploading {filename} to R2...")
    file_size = os.path.getsize(local_path)

    # upload_file reads from disk and streams to R2.
    # ExtraArgs sets the Content-Type header so browsers
    # know it's a video (not a binary download).
    client.upload_file(
        local_path,
        config.R2_BUCKET_NAME,
        filename,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    public_url = f"{config.R2_PUBLIC_URL}/{filename}"
    print(f"  Uploaded: {public_url} ({file_size / 1024 / 1024:.1f} MB)")
    return public_url


def upload_datamosh(local_path):
    """
    Upload the datamosh composite video to R2.

    Always overwrites the same key ("datamosh.mp4") so the
    frontend always points to the latest version.

    Returns:
        Public URL string, or None if upload failed/skipped.
    """
    return upload_video(local_path, "datamosh.mp4")


def delete_file(filename):
    """
    Delete a file from R2. Used by tests for cleanup.

    Returns True if deleted, False if skipped/failed.
    """
    client = _get_client()
    if not client:
        return False

    client.delete_object(Bucket=config.R2_BUCKET_NAME, Key=filename)
    return True
