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


def get_unique_filename(filename):
    """
    Check R2 for existing keys and return a unique filename.

    If 2026-04-01.mp4 exists, tries 2026-04-01-1.mp4, 2026-04-01-2.mp4, etc.
    Returns the original filename if R2 isn't configured.
    """
    client = _get_client()
    if not client:
        return filename

    base, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1

    while True:
        try:
            client.head_object(Bucket=config.R2_BUCKET_NAME, Key=candidate)
            # Key exists — try next suffix
            candidate = f"{base}-{counter}{ext}"
            counter += 1
        except client.exceptions.ClientError:
            # Key doesn't exist — this one is free
            return candidate


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


def upload_file_with_type(local_path, key, content_type):
    """
    Upload a single file to R2 under an arbitrary key with an
    explicit Content-Type. Overwrites any existing object at that key.

    Returns the public URL, or None if R2 isn't configured.
    """
    client = _get_client()
    if not client:
        return None

    client.upload_file(
        local_path,
        config.R2_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return f"{config.R2_PUBLIC_URL}/{key}"


def upload_hls_dir(local_dir):
    """
    Upload an HLS bundle (playlist + .ts chunks) from local_dir to R2
    under the "hls/" prefix, with correct content types:
      .m3u8 → application/vnd.apple.mpegurl
      .ts   → video/mp2t

    Prints "Uploading chunk X/Y..." progress for every file (there may
    be 50+). Overwrites the hls/ prefix so the playlist URL is stable.

    Returns the public URL of hls/datamosh.m3u8, or None if R2 isn't
    configured.
    """
    client = _get_client()
    if not client:
        return None

    content_types = {
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/mp2t",
    }

    # Sort so chunk000, chunk001, ... upload in order; playlist included.
    files = sorted(os.listdir(local_dir))
    total = len(files)
    playlist_url = None

    for i, name in enumerate(files, start=1):
        local_path = os.path.join(local_dir, name)
        if not os.path.isfile(local_path):
            continue
        ext = os.path.splitext(name)[1].lower()
        content_type = content_types.get(ext, "application/octet-stream")
        key = f"hls/{name}"

        print(f"  Uploading chunk {i}/{total}: {name}")
        url = upload_file_with_type(local_path, key, content_type)
        if name == "datamosh.m3u8":
            playlist_url = url

    return playlist_url


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
