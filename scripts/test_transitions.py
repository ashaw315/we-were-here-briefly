"""
Test two fal.ai models for generating seamless transition videos
between consecutive clips.

For each of the first N consecutive run-pairs (ordered by date ASC),
this:
  1. Downloads both clips' videos from R2
  2. Extracts the LAST frame of clip A and the FIRST frame of clip B
  3. Uploads both frames to fal.ai file storage (temporary URLs)
  4. Generates a transition with KLING O1 (start + tail image)
  5. Generates the same transition with PIXVERSE V3.5 (first + last image)
  6. Saves outputs to output/test_transitions/pair_K_{model}.mp4
  7. Cleans up the temp frames for that pair

This is a TEST ONLY. Nothing is written to Postgres or the main R2
bucket — outputs land in output/test_transitions/ on local disk.

Each pair runs 2 paid fal.ai generations, so by default it does 3 pairs
(6 generations, ~10-20 min). Use --pairs N to limit (e.g. --pairs 1 for
a smoke test). Failures in one generation are reported at the end and
don't stop the rest.

Usage:
  python scripts/test_transitions.py            # 3 pairs (full)
  python scripts/test_transitions.py --pairs 1  # smoke test, 1 pair
"""

import argparse
import os
import subprocess
import sys
import tempfile

import requests

import fal_client

# Project root is the parent of scripts/. Put it on sys.path so we can
# import config and the db package the same way the rest of the repo does.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import config
from db.database import get_all_runs

OUTPUT_DIR = os.path.join(BASE_DIR, "output", "test_transitions")

KLING_MODEL = "fal-ai/kling-video/o1/image-to-video"
PIXVERSE_MODEL = "fal-ai/pixverse/v3.5/transition"

TRANSITION_PROMPT = (
    "seamless morphing transition, one scene flowing into another, "
    "dreamlike and continuous"
)


def on_queue_update(update):
    """Log progress while a fal.ai job runs (matches generator/video_gen.py)."""
    if isinstance(update, fal_client.InProgress):
        print(f"      generating... {getattr(update, 'logs', '') or ''}")


def get_pairs(num_pairs, start_index=1):
    """
    Fetch runs ordered by date ASC and return consecutive
    (pair_number, run_a, run_b) tuples.

    Pairs are numbered from 1 (pair K is run K → run K+1). `start_index`
    selects the first pair number to return, and `num_pairs` how many.
    So start_index=2, num_pairs=2 yields pairs 2 and 3 — letting us run
    later pairs without re-billing earlier ones.

    get_all_runs() returns newest-first, so we reverse to date-ASC.
    Only runs that have a usable video URL are considered.
    """
    runs = get_all_runs()
    if not runs:
        print("No runs from Postgres (not configured or empty).")
        sys.exit(1)

    # Oldest-first. get_all_runs() is created_at DESC; reverse it.
    runs_asc = list(reversed(runs))

    # Keep only runs with a source video URL to transition between.
    usable = [r for r in runs_asc if r.get("video_url")]

    last_pair = start_index + num_pairs - 1
    # Pair `last_pair` needs runs at indices last_pair-1 and last_pair
    # (0-based), so we need last_pair + 1 usable runs.
    if len(usable) < last_pair + 1:
        print(f"Need at least {last_pair + 1} runs with video_url to reach "
              f"pair {last_pair}, found {len(usable)}.")
        sys.exit(1)

    pairs = []
    for pair_num in range(start_index, start_index + num_pairs):
        a = usable[pair_num - 1]
        b = usable[pair_num]
        pairs.append((pair_num, a, b))
    return pairs


def download_video(url, dest_path):
    """Stream a remote video URL to a local file."""
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def run_ffmpeg(args):
    """Run an ffmpeg command; raise with stderr on failure."""
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")


def extract_last_frame(clip_path, out_path):
    """Extract the last frame of a clip (seek 0.1s from end)."""
    run_ffmpeg([
        "-sseof", "-0.1", "-i", clip_path,
        "-frames:v", "1", "-f", "image2", out_path,
    ])


def extract_first_frame(clip_path, out_path):
    """Extract the first frame of a clip."""
    run_ffmpeg([
        "-i", clip_path,
        "-frames:v", "1", "-f", "image2", out_path,
    ])


def download_result_video(result, dest_path):
    """
    Pull the video URL out of a fal.ai result dict and download it.

    fal video models return {"video": {"url": ...}}. Download
    immediately — these CDN URLs are temporary.
    """
    video_url = result.get("video", {}).get("url")
    if not video_url:
        raise RuntimeError(f"No video URL in result: {result}")
    download_video(video_url, dest_path)
    return dest_path


def generate_kling(start_url, end_url, dest_path):
    """
    Generate a transition with Kling O1.

    Field names per the fal.ai schema: start_image_url (the last frame
    of clip A) and end_image_url (the first frame of clip B). This model
    has no aspect_ratio parameter.
    """
    result = fal_client.subscribe(
        KLING_MODEL,
        arguments={
            "start_image_url": start_url,  # start frame (last frame of A)
            "end_image_url": end_url,      # end frame (first frame of B)
            "duration": "5",
            "prompt": TRANSITION_PROMPT,
        },
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    return download_result_video(result, dest_path)


def generate_pixverse(start_url, end_url, dest_path):
    """
    Generate a transition with PixVerse V3.5.

    Field names per the fal.ai schema: first_image_url + end_image_url,
    a required prompt, duration as a string enum, and resolution (not
    "quality") for 1080p.
    """
    result = fal_client.subscribe(
        PIXVERSE_MODEL,
        arguments={
            "first_image_url": start_url,  # last frame of A
            "end_image_url": end_url,      # first frame of B
            "prompt": TRANSITION_PROMPT,
            "duration": "5",
            "resolution": "1080p",
        },
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    return download_result_video(result, dest_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pairs", type=int, default=3,
        help="Number of consecutive pairs to test (default 3).",
    )
    parser.add_argument(
        "--start", type=int, default=1,
        help="First pair number to run (default 1). Use --start 2 to "
             "resume at pair 2 without re-billing earlier pairs.",
    )
    args = parser.parse_args()

    if not config.FAL_KEY:
        print("No FAL_KEY configured — cannot generate. Aborting.")
        sys.exit(1)
    # fal_client reads FAL_KEY from the environment.
    os.environ["FAL_KEY"] = config.FAL_KEY

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print(f"TRANSITION TEST — {args.pairs} pair(s) from pair {args.start}, "
          f"2 models each")
    print("=" * 60)

    pairs = get_pairs(args.pairs, start_index=args.start)

    # Collected for the end-of-run summary. Each entry:
    #   (pair_index, seed_a, seed_b, kling_status, pixverse_status)
    summary = []

    for idx, run_a, run_b in pairs:
        seed_a = run_a.get("seed", "?")
        seed_b = run_b.get("seed", "?")
        print(f"\n{'-' * 60}")
        print(f"Pair {idx}: {seed_a} → {seed_b}")
        print(f"{'-' * 60}")

        kling_status = "skipped"
        pixverse_status = "skipped"

        # Per-pair temp dir for downloaded clips + extracted frames.
        # Cleaned up automatically when the with-block exits.
        with tempfile.TemporaryDirectory() as tmp:
            try:
                clip_a = os.path.join(tmp, "clip_a.mp4")
                clip_b = os.path.join(tmp, "clip_b.mp4")
                print(f"  Downloading clip A: {run_a['video_url']}")
                download_video(run_a["video_url"], clip_a)
                print(f"  Downloading clip B: {run_b['video_url']}")
                download_video(run_b["video_url"], clip_b)

                last_frame = os.path.join(tmp, "last_frame.jpg")
                first_frame = os.path.join(tmp, "first_frame.jpg")
                print("  Extracting last frame of A and first frame of B...")
                extract_last_frame(clip_a, last_frame)
                extract_first_frame(clip_b, first_frame)

                print("  Uploading frames to fal.ai storage...")
                start_url = fal_client.upload_file(last_frame)
                end_url = fal_client.upload_file(first_frame)
            except Exception as e:
                # If we can't even prep the frames, both models fail for
                # this pair — record and move on.
                msg = f"frame prep failed: {type(e).__name__}: {e}"
                print(f"  ✗ {msg}")
                summary.append((idx, seed_a, seed_b, msg, msg))
                continue

            # --- Kling O1 ---
            kling_path = os.path.join(OUTPUT_DIR, f"pair_{idx}_kling.mp4")
            try:
                print(f"  [Kling O1] generating (this may take 1-3 min)...")
                generate_kling(start_url, end_url, kling_path)
                size = os.path.getsize(kling_path)
                kling_status = f"saved to pair_{idx}_kling.mp4 ({size:,} bytes)"
                print(f"  ✓ Kling O1: {kling_status}")
            except Exception as e:
                kling_status = f"FAILED: {type(e).__name__}: {e}"
                print(f"  ✗ Kling O1 {kling_status}")

            # --- PixVerse V3.5 ---
            pixverse_path = os.path.join(OUTPUT_DIR, f"pair_{idx}_pixverse.mp4")
            try:
                print(f"  [PixVerse V3.5] generating (this may take 1-3 min)...")
                generate_pixverse(start_url, end_url, pixverse_path)
                size = os.path.getsize(pixverse_path)
                pixverse_status = (
                    f"saved to pair_{idx}_pixverse.mp4 ({size:,} bytes)"
                )
                print(f"  ✓ PixVerse: {pixverse_status}")
            except Exception as e:
                pixverse_status = f"FAILED: {type(e).__name__}: {e}"
                print(f"  ✗ PixVerse {pixverse_status}")

        # tmp (clips + frames) is cleaned up here, after each pair.
        summary.append((idx, seed_a, seed_b, kling_status, pixverse_status))

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for idx, seed_a, seed_b, kling_status, pixverse_status in summary:
        print(f"Pair {idx}: {seed_a} → {seed_b}")
        print(f"  Kling O1: {kling_status}")
        print(f"  PixVerse: {pixverse_status}")
    print(f"\nOutputs in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
