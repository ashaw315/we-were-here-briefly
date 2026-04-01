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
"""

import json
import os
import random
import subprocess
import sys
import tempfile

import requests

# Paths relative to this script's location (project root)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_FILE = os.path.join(OUTPUT_DIR, "log.json")
DATAMOSH_OUTPUT = os.path.join(OUTPUT_DIR, "datamosh.mp4")


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

    # Upload to R2 if configured
    try:
        sys.path.insert(0, BASE_DIR)
        from uploader.r2_upload import upload_datamosh
        datamosh_url = upload_datamosh(DATAMOSH_OUTPUT)
        if datamosh_url:
            print(f"  R2 URL: {datamosh_url}")
            # Delete local file after successful upload
            os.remove(DATAMOSH_OUTPUT)
            print(f"  Deleted local datamosh file")
    except Exception as e:
        print(f"  R2 upload skipped: {e}")


if __name__ == "__main__":
    main()
