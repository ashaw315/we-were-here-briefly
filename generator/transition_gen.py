"""
Transition generator — Kling O1 morphs between consecutive clips.

For a pair of runs A → B, this builds a 5-second transition video that
flows from the LAST frame of A into the FIRST frame of B, so the final
assembled loop has no hard cuts. The transition is uploaded to R2 under
the transitions/ prefix and its public URL is returned.

This replaces the old datamosh effect. fal.ai is used the same way as
generator/video_gen.py: set FAL_KEY in the env, call
fal_client.subscribe() (which polls until the GPU job finishes), then
download the result immediately (the CDN URL is temporary).

The Kling O1 parameter names (start_image_url / end_image_url) were
verified against the fal.ai schema — see scripts/test_transitions.py for
the discovery of those names.
"""

import os
import subprocess
import sys
import tempfile

import requests

import fal_client

# Project root on sys.path so config / db / uploader import cleanly
# whether this is called as a module or a script.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import config
from uploader.r2_upload import upload_file_with_type

KLING_MODEL = "fal-ai/kling-video/o1/image-to-video"
TRANSITION_PROMPT = (
    "seamless morphing transition, one scene flowing continuously "
    "into another, dreamlike and fluid, no cut"
)


def _on_queue_update(update):
    """Log progress while the fal.ai job runs (matches video_gen.py)."""
    if isinstance(update, fal_client.InProgress):
        print(f"    generating... {getattr(update, 'logs', '') or ''}")


def _download(url, dest_path):
    """Stream a remote video URL to a local file."""
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def _run_ffmpeg(args):
    """Run an ffmpeg command; raise with stderr on failure."""
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")


def generate_transition(from_video_url, to_video_url, run_id, next_run_id,
                        seed_a=None, seed_b=None):
    """
    Generate a Kling O1 transition from one clip to the next.

    Args:
        from_video_url: R2 URL of clip A (transition starts on its last frame)
        to_video_url:   R2 URL of clip B (transition ends on its first frame)
        run_id:         id of run A (used in the R2 key)
        next_run_id:    id of run B (used in the R2 key)
        seed_a, seed_b: seed words, for progress output only

    Returns the R2 public URL of the uploaded transition video.

    Raises on any failure (download, ffmpeg, fal, upload) so the caller
    can decide whether to skip-and-continue or abort.
    """
    label_a = seed_a if seed_a is not None else f"run {run_id}"
    label_b = seed_b if seed_b is not None else f"run {next_run_id}"
    print(f"  Generating transition: {label_a} → {label_b}")

    if not config.FAL_KEY:
        raise RuntimeError("No FAL_KEY configured")
    # fal_client reads FAL_KEY from the environment.
    os.environ["FAL_KEY"] = config.FAL_KEY

    with tempfile.TemporaryDirectory() as tmp:
        clip_a = os.path.join(tmp, "from.mp4")
        clip_b = os.path.join(tmp, "to.mp4")
        _download(from_video_url, clip_a)
        _download(to_video_url, clip_b)

        # Last frame of A (seek 0.1s before end), first frame of B.
        last_frame = os.path.join(tmp, "last_frame.jpg")
        first_frame = os.path.join(tmp, "first_frame.jpg")
        _run_ffmpeg([
            "-sseof", "-0.1", "-i", clip_a,
            "-frames:v", "1", "-f", "image2", last_frame,
        ])
        _run_ffmpeg([
            "-i", clip_b,
            "-frames:v", "1", "-f", "image2", first_frame,
        ])

        # Upload frames to fal storage → temporary URLs for the model.
        start_image_url = fal_client.upload_file(last_frame)
        end_image_url = fal_client.upload_file(first_frame)

        result = fal_client.subscribe(
            KLING_MODEL,
            arguments={
                "start_image_url": start_image_url,
                "end_image_url": end_image_url,
                "duration": "5",
                "prompt": TRANSITION_PROMPT,
            },
            with_logs=True,
            on_queue_update=_on_queue_update,
        )

        video_url = result.get("video", {}).get("url")
        if not video_url:
            raise RuntimeError(f"No video URL in Kling result: {result}")

        transition_path = os.path.join(tmp, "transition.mp4")
        _download(video_url, transition_path)

        # Upload to R2. Key encodes both run ids so the chain is readable.
        key = f"transitions/transition_{run_id}_to_{next_run_id}.mp4"
        r2_url = upload_file_with_type(transition_path, key, "video/mp4")
        if not r2_url:
            raise RuntimeError("R2 not configured — could not upload transition")

    # temp dir (clips + frames + downloaded transition) cleaned up here.
    print(f"  Uploaded: {r2_url}")
    return r2_url
