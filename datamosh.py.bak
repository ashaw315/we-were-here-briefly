"""
True datamosh via ffmpeg + I-frame stripping.

How it works:
  1. Get all video URLs (from Postgres, falling back to log.json)
  2. Download any remote videos (R2 URLs) to temp dir
  3. Convert ALL source clips to mpeg2
  4. Concatenate them in shuffled order
  5. Strip all I-frames after the first from the raw bytes —
     this forces the decoder to apply earlier clips' motion
     vectors across every subsequent clip's pixel data
  6. Convert the mangled mpeg2 back to mp4
  7. Upload result to R2 if configured

The result is the real datamosh effect: ghostly smeared
figures bleeding across the entire video timeline.

After generating datamosh.mp4 we convert it to HLS (chunked .ts
segments + an .m3u8 playlist) and serve THAT to the site, so the
browser streams ~6s chunks on demand instead of loading one 268MB
file. The mp4 is still uploaded too (kept for admin download).

# IMPORTANT: R2 bucket requires CORS configuration for HLS.
# In Cloudflare R2 dashboard → we-were-here-briefly →
# Settings → CORS Policy → add:
# [
#   {
#     "AllowedOrigins": ["*"],
#     "AllowedMethods": ["GET", "HEAD"],
#     "AllowedHeaders": ["*"],
#     "ExposeHeaders": ["Content-Length"],
#     "MaxAgeSeconds": 3600
#   }
# ]
"""

import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

import requests

# Paths relative to this script's location (project root)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_FILE = os.path.join(OUTPUT_DIR, "log.json")
DATAMOSH_OUTPUT = os.path.join(OUTPUT_DIR, "datamosh.mp4")
HLS_DIR = os.path.join(OUTPUT_DIR, "hls")


def get_all_videos():
    """
    Get all video URLs/paths. Tries Postgres first, falls back to log.json.
    Never combines both sources. Deduplicates by URL.

    Returns a list of (url_or_path, is_remote) tuples.
    """
    raw_urls = []
    source = None

    # Try Postgres first — only source if it works
    try:
        sys.path.insert(0, BASE_DIR)
        from db.database import get_all_runs
        runs = get_all_runs()
        if runs:
            entries = [r for r in runs if r.get("video_url")]
            if entries:
                raw_urls = [e["video_url"] for e in entries]
                source = "Postgres"
    except Exception as e:
        print(f"  Postgres unavailable: {e}")

    # Fall back to log.json ONLY if Postgres didn't provide videos
    if not raw_urls:
        if not os.path.exists(LOG_FILE):
            print("No log.json found")
            sys.exit(1)

        with open(LOG_FILE, "r") as f:
            log = json.load(f)

        for entry in log:
            url = entry.get("video_url") or entry.get("video")
            if url:
                raw_urls.append(url)
        source = "log.json"

    # Deduplicate by URL
    seen = set()
    unique_urls = []
    for url in raw_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    dupes = len(raw_urls) - len(unique_urls)
    if dupes:
        print(f"  Removed {dupes} duplicate(s)")

    if len(unique_urls) < 2:
        print(f"Need at least 2 unique videos, found {len(unique_urls)}")
        sys.exit(1)

    # Print full list before processing
    print(f"\n  Source: {source}")
    print(f"  Processing {len(unique_urls)} unique videos:")
    for url in unique_urls:
        print(f"    → {url}")

    random.shuffle(unique_urls)

    result = []
    for url in unique_urls:
        is_remote = url.startswith("http")
        if not is_remote:
            url = os.path.join(OUTPUT_DIR, url)
        result.append((url, is_remote))

    return result


def download_remote(url, dest_path):
    """Download a remote video URL to a local file."""
    print(f"  Downloading: {os.path.basename(url)}...")
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    size_mb = os.path.getsize(dest_path) / (1024 * 1024)
    print(f"    Downloaded: {size_mb:.1f} MB")


def run_ffmpeg(args):
    """Run an ffmpeg command, exit on failure."""
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ffmpeg failed:\n{result.stderr}")
        sys.exit(1)


def strip_iframes(input_path, output_path):
    """
    Read an mpeg2 file as raw bytes and convert ALL I-frames
    after the first into P-frames.

    MPEG2 picture start code: 0x00 0x00 0x01 0x00
    The byte at offset+5 contains picture_coding_type in bits 5-3:
      001 = I-frame, 010 = P-frame, 011 = B-frame

    We flip I-frame type bits to P-frame, forcing the decoder
    to reuse motion vectors instead of resetting. No I-frames
    are retained — the decoder never gets a clean reset.
    """
    with open(input_path, "rb") as f:
        data = bytearray(f.read())

    picture_start = b'\x00\x00\x01\x00'
    positions = []
    offset = 0
    while True:
        pos = data.find(picture_start, offset)
        if pos == -1:
            break
        positions.append(pos)
        offset = pos + 4

    if not positions:
        print("  No picture start codes found — copying file as-is")
        with open(output_path, "wb") as f:
            f.write(data)
        return

    iframe_positions = []
    for pos in positions:
        if pos + 5 < len(data):
            pic_type = (data[pos + 5] >> 3) & 0x07
            if pic_type == 1:
                iframe_positions.append(pos)

    print(f"  Found {len(positions)} pictures, {len(iframe_positions)} I-frames")

    if len(iframe_positions) <= 1:
        print("  Only 0-1 I-frames — nothing to strip")
        with open(output_path, "wb") as f:
            f.write(data)
        return

    stripped = 0
    for iframe_pos in iframe_positions[1:]:
        if iframe_pos + 5 < len(data):
            byte_val = data[iframe_pos + 5]
            byte_val = (byte_val & 0xC7) | (2 << 3)
            data[iframe_pos + 5] = byte_val
            stripped += 1

    print(f"  Converted {stripped} I-frames to P-frames (kept first only)")

    with open(output_path, "wb") as f:
        f.write(data)


def convert_to_hls(input_path):
    """
    Convert a datamosh mp4 into an HLS bundle and upload it to R2.

    Splits the mp4 into ~6s .ts chunks plus an .m3u8 playlist, uploads
    every file to R2 under the hls/ prefix, repoints every Postgres run
    at the new playlist URL, and cleans up the local hls dir.

    Returns the public .m3u8 URL, or None if R2 isn't configured.
    """
    print("\n" + "=" * 50)
    print("HLS CONVERSION")
    print("=" * 50)

    # Fresh output/hls/ — clear any stale chunks from a previous run.
    if os.path.isdir(HLS_DIR):
        shutil.rmtree(HLS_DIR)
    os.makedirs(HLS_DIR, exist_ok=True)

    playlist_path = os.path.join(HLS_DIR, "datamosh.m3u8")
    segment_pattern = os.path.join(HLS_DIR, "chunk%03d.ts")

    print("\nStep 1: Split into HLS chunks")
    run_ffmpeg([
        "-i", input_path,
        "-codec:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-codec:a", "aac",
        "-hls_time", "6",
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", segment_pattern,
        "-hls_flags", "independent_segments",
        playlist_path,
    ])

    chunks = sorted(f for f in os.listdir(HLS_DIR) if f.endswith(".ts"))
    total_size = sum(
        os.path.getsize(os.path.join(HLS_DIR, f)) for f in os.listdir(HLS_DIR)
    )
    print(f"  Created {len(chunks)} chunks "
          f"({total_size / 1024 / 1024:.1f} MB total)")

    # Step 2 — Upload the whole bundle to R2.
    print("\nStep 2: Upload HLS bundle to R2")
    try:
        sys.path.insert(0, BASE_DIR)
        from uploader.r2_upload import upload_hls_dir
        playlist_url = upload_hls_dir(HLS_DIR)
    except Exception as e:
        print(f"  HLS upload skipped: {e}")
        shutil.rmtree(HLS_DIR, ignore_errors=True)
        return None

    if not playlist_url:
        print("  R2 not configured — HLS bundle left in output/hls/")
        return None

    print(f"  Playlist URL: {playlist_url}")

    # Step 3 — Repoint every run at the new playlist.
    print("\nStep 3: Update Postgres datamosh_url for all runs")
    try:
        from db.database import update_all_datamosh_urls
        updated = update_all_datamosh_urls(playlist_url)
        if updated is None:
            print("  Postgres not configured — skipped")
        else:
            print(f"  Updated {updated} run(s)")
    except Exception as e:
        print(f"  Postgres update skipped: {e}")

    # Step 4 — Clean up local hls dir.
    shutil.rmtree(HLS_DIR, ignore_errors=True)
    print("  Cleaned up output/hls/")

    return playlist_url


def hls_only():
    """
    Standalone entry: download the existing datamosh.mp4 from R2 and
    convert it to HLS — without re-running the mosh pipeline.

    Used by `python datamosh.py --hls-only` to chunk the mp4 that's
    already live (the local copy is deleted after each pipeline run).
    """
    print("=" * 50)
    print("DATAMOSH — HLS ONLY (from existing R2 mp4)")
    print("=" * 50)

    import config
    source_url = f"{config.R2_PUBLIC_URL}/datamosh.mp4"

    with tempfile.TemporaryDirectory() as tmp:
        local_mp4 = os.path.join(tmp, "datamosh.mp4")
        print(f"\n  Source: {source_url}")
        download_remote(source_url, local_mp4)
        playlist_url = convert_to_hls(local_mp4)

    if playlist_url:
        print(f"\nDone. Site playlist: {playlist_url}")
        print(f"HLS_URL:{playlist_url}")


def main():
    print("=" * 50)
    print("DATAMOSH")
    print("=" * 50)

    videos = get_all_videos()
    total = len(videos)
    print(f"\n  Found {total} clips")

    with tempfile.TemporaryDirectory() as tmp:
        # Step 0 — Download remote videos if needed
        local_clips = []
        for i, (url, is_remote) in enumerate(videos):
            if is_remote:
                local_path = os.path.join(tmp, f"src_{i}.mp4")
                download_remote(url, local_path)
                local_clips.append(local_path)
            else:
                if not os.path.exists(url):
                    print(f"  Video not found: {url}")
                    sys.exit(1)
                local_clips.append(url)

        order = " → ".join(os.path.basename(c) for c in local_clips)
        print(f"  Video order: {order}")

        # Step 1 — Convert each clip to mpeg2
        print("\nStep 1: Convert to mpeg2")
        temp_mpgs = []
        for i, clip in enumerate(local_clips):
            print(f"  Processing clip {i + 1}/{total}: {os.path.basename(clip)}")
            temp_path = os.path.join(tmp, f"{i}.mpg")
            run_ffmpeg([
                "-i", clip,
                "-codec:v", "mpeg2video",
                "-q:v", "1",
                "-bf", "0",
                "-g", "1000",
                "-colorspace", "bt709",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-pix_fmt", "yuv420p",
                "-an", temp_path,
            ])
            temp_mpgs.append(temp_path)

        # Step 2 — Concatenate all clips
        print("\nStep 2: Concatenate")
        concat_str = "|".join(temp_mpgs)
        temp_concat = os.path.join(tmp, "concat.mpg")
        run_ffmpeg(["-i", f"concat:{concat_str}", "-c", "copy", temp_concat])

        # Step 3 — Strip I-frames after the first
        print("\nStep 3: Strip I-frames")
        temp_moshed = os.path.join(tmp, "moshed.mpg")
        strip_iframes(temp_concat, temp_moshed)

        # Step 4 — Convert back to mp4
        print("\nStep 4: Convert to mp4")
        run_ffmpeg([
            "-i", temp_moshed,
            "-codec:v", "libx264",
            "-crf", "16",
            "-preset", "slow",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-pix_fmt", "yuv420p",
            DATAMOSH_OUTPUT,
        ])

    size_mb = os.path.getsize(DATAMOSH_OUTPUT) / (1024 * 1024)
    print(f"\nDatamosh complete: {DATAMOSH_OUTPUT}")
    print(f"  Size: {size_mb:.1f} MB")

    # Upload mp4 to R2 if configured. The mp4 is kept on R2 (for admin
    # download); the site itself streams the HLS playlist built below.
    uploaded = False
    try:
        sys.path.insert(0, BASE_DIR)
        from uploader.r2_upload import upload_datamosh
        datamosh_url = upload_datamosh(DATAMOSH_OUTPUT)
        if datamosh_url:
            uploaded = True
            print(f"  R2 URL (mp4, admin): {datamosh_url}")
            # Machine-readable line for main.py to capture
            print(f"DATAMOSH_URL:{datamosh_url}")
    except Exception as e:
        print(f"  R2 upload skipped: {e}")

    # Convert the mp4 to HLS and point the site at the playlist.
    convert_to_hls(DATAMOSH_OUTPUT)

    # Delete the local mp4 only after a successful R2 upload (it lives
    # on R2 now). If upload was skipped, keep it locally.
    if uploaded:
        os.remove(DATAMOSH_OUTPUT)
        print(f"  Deleted local datamosh file")


if __name__ == "__main__":
    if "--hls-only" in sys.argv:
        hls_only()
    else:
        main()
