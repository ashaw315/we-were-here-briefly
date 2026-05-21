"""
Final video assembler — stitches clips + transitions into the loop.

This replaces datamosh as the delivery-video builder. It reads every run
in chronological order and interleaves each clip with the Kling O1
transition that follows it:

    [clip_1, transition_1, clip_2, transition_2, ..., clip_N, transition_N]

transition_N is the loop-closing transition (last run → first run), so
the HLS stream plays as a seamless infinite loop.

The sequence is concatenated with ffmpeg's concat demuxer. We try
`-c copy` first (fast, lossless) since Kling videos are all 1920×1080
h264 — but the original clips (Kling 1.6) and transitions (Kling O1) are
not guaranteed to be byte-compatible, so if `-c copy` fails or produces
an invalid file we fall back to re-encoding (normalizing every input to
1920×1080 h264 + aac).

The result is chunked into HLS and uploaded to R2 at hls/datamosh.m3u8 —
the same key the frontend already plays, so app.js/index.html are
unchanged. All runs' datamosh_url is repointed at the playlist.
"""

import os
import shutil
import subprocess
import sys
import tempfile

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import config
from db.database import get_all_runs_ordered, update_all_datamosh_urls
from uploader.r2_upload import upload_hls_dir

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
HLS_DIR = os.path.join(OUTPUT_DIR, "hls")
PLAYLIST_NAME = "datamosh.m3u8"  # keep the existing key so the site is unchanged


def _run_ffmpeg(args):
    """Run an ffmpeg command; return CompletedProcess (does not raise)."""
    cmd = ["ffmpeg", "-y"] + args
    return subprocess.run(cmd, capture_output=True, text=True)


def _ffmpeg_or_raise(args):
    """Run ffmpeg, raising with stderr on failure."""
    result = _run_ffmpeg(args)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")


def _download(url, dest_path):
    """Stream a remote video URL to a local file."""
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def _probe_duration(path):
    """Return a file's duration in seconds via ffprobe, or None if invalid."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _probe_dimensions(path):
    """Return (width, height) of a video's first stream, or None if invalid."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        w, h = result.stdout.strip().split("x")
        return (int(w), int(h))
    except (ValueError, IndexError):
        return None


def _all_same_dimensions(local_files):
    """
    True only if every input shares one resolution. ffmpeg's concat
    demuxer with -c copy does NOT rescale — it inherits the first input's
    dimensions, so mismatched sizes (e.g. 720p source clips + 1080p
    transitions) produce a stream that probes fine but plays back garbled
    at the boundaries. When sizes differ we must re-encode.
    """
    dims = {_probe_dimensions(p) for p in local_files}
    return len(dims) == 1 and None not in dims


def _build_sequence(runs):
    """
    Build the ordered list of (label, url) parts to concatenate:
    each clip followed by its transition. A run missing a transition_url
    (e.g. backfill not yet complete) contributes its clip only, with a
    warning — the video still assembles, just with a cut there.
    """
    parts = []
    for run in runs:
        if run.get("video_url"):
            parts.append((f"clip[{run['seed']}]", run["video_url"]))
        else:
            print(f"  ! run {run['id']} ({run.get('seed')}) has no video_url — skipping")
        if run.get("transition_url"):
            parts.append((f"transition[{run['seed']}→]", run["transition_url"]))
        else:
            print(f"  ! run {run['id']} ({run.get('seed')}) has no transition_url "
                  f"— sequence will have a cut here")
    return parts


def _concat_copy(local_files, concat_list, out_path):
    """Concatenate with stream copy (fast, lossless). Returns True on success."""
    with open(concat_list, "w") as f:
        for path in local_files:
            # Escape single quotes per ffmpeg concat syntax.
            safe = path.replace("'", "'\\''")
            f.write(f"file '{safe}'\n")
    result = _run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", out_path,
    ])
    if result.returncode != 0:
        print("  -c copy concat failed; will re-encode")
        print(f"    {result.stderr.strip().splitlines()[-1] if result.stderr else ''}")
        return False
    # Validate: concat copy can 'succeed' but produce an unplayable file
    # when stream params differ. Confirm a probeable duration.
    if _probe_duration(out_path) is None:
        print("  -c copy produced an invalid file; will re-encode")
        return False
    return True


def _concat_reencode(local_files, out_path):
    """
    Concatenate by re-encoding every input to a uniform 1920×1080 h264 +
    aac stream. Slower but robust against mismatched source params.
    Uses the concat filter so inputs with differing params are normalized.
    """
    inputs = []
    for path in local_files:
        inputs += ["-i", path]

    n = len(local_files)
    # Normalize each input, then concat. scale+sar+fps make every stream
    # identical so the concat filter accepts them.
    filter_parts = []
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_complex = ";".join(filter_parts) + \
        f";{concat_inputs}concat=n={n}:v=1:a=0[outv]"

    _ffmpeg_or_raise(inputs + [
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        out_path,
    ])


def _convert_to_hls(input_path):
    """Chunk an mp4 into HLS (datamosh.m3u8 + chunkNNN.ts) in HLS_DIR."""
    if os.path.isdir(HLS_DIR):
        shutil.rmtree(HLS_DIR)
    os.makedirs(HLS_DIR, exist_ok=True)

    playlist_path = os.path.join(HLS_DIR, PLAYLIST_NAME)
    segment_pattern = os.path.join(HLS_DIR, "chunk%03d.ts")
    _ffmpeg_or_raise([
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
    chunks = [f for f in os.listdir(HLS_DIR) if f.endswith(".ts")]
    return len(chunks)


def assemble_final_video():
    """
    Rebuild the full loop video from all clips + transitions and publish
    it as the HLS stream. Returns the playlist URL, or None on failure.
    """
    print("\n" + "=" * 50)
    print("ASSEMBLE FINAL VIDEO")
    print("=" * 50)

    runs = get_all_runs_ordered()
    if not runs:
        print("No runs from Postgres — nothing to assemble.")
        return None

    parts = _build_sequence(runs)
    clip_count = sum(1 for label, _ in parts if label.startswith("clip"))
    trans_count = sum(1 for label, _ in parts if label.startswith("transition"))
    print(f"\n  Sequence: {clip_count} clips + {trans_count} transitions "
          f"= {len(parts)} parts")

    with tempfile.TemporaryDirectory() as tmp:
        # Download every part to a numbered local file.
        local_files = []
        total = len(parts)
        for i, (label, url) in enumerate(parts, start=1):
            print(f"  Downloading clip {i}/{total}... ({label})")
            dest = os.path.join(tmp, f"part_{i:04d}.mp4")
            _download(url, dest)
            local_files.append(dest)

        # Concatenate: try lossless copy, fall back to re-encode.
        final_mp4 = os.path.join(OUTPUT_DIR, "final.mp4")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        concat_list = os.path.join(tmp, "concat_list.txt")

        # Decide copy vs re-encode by dimensional uniformity. -c copy is
        # only safe when every input is the same resolution; our source
        # clips (Kling 1.6, 720p) and transitions (Kling O1, 1080p) differ,
        # so this normally re-encodes. We still try copy when sizes match
        # (fast, lossless), and fall back to re-encode if copy then fails.
        if _all_same_dimensions(local_files):
            print("\n  All inputs share one resolution — trying -c copy...")
            if not _concat_copy(local_files, concat_list, final_mp4):
                print("  Re-encoding all parts to a uniform stream...")
                _concat_reencode(local_files, final_mp4)
        else:
            print("\n  Mixed input resolutions — re-encoding to uniform "
                  "1920×1080...")
            _concat_reencode(local_files, final_mp4)

        total_duration = _probe_duration(final_mp4) or 0.0
        print(f"  Concatenated: {final_mp4} ({total_duration:.0f}s)")

        # HLS chunk it.
        print("\n  Converting to HLS...")
        chunk_count = _convert_to_hls(final_mp4)
        print(f"  HLS chunks: {chunk_count} segments")

        # Upload the bundle to R2 (overwrites hls/).
        print("\n  Uploading HLS bundle to R2...")
        playlist_url = upload_hls_dir(HLS_DIR)
        if not playlist_url:
            print("  R2 not configured — leaving HLS in output/hls/")
            return None

        # Repoint all runs at the playlist.
        updated = update_all_datamosh_urls(playlist_url)
        if updated is not None:
            print(f"  Updated datamosh_url for {updated} run(s)")

    # Clean up local artifacts.
    shutil.rmtree(HLS_DIR, ignore_errors=True)
    if os.path.exists(final_mp4):
        os.remove(final_mp4)

    print(f"\nAssembled {clip_count} clips + {trans_count} transitions "
          f"= {total_duration:.0f}s total")
    print(f"HLS chunks: {chunk_count} files uploaded")
    print(f"Final video live at: {playlist_url}")
    return playlist_url


if __name__ == "__main__":
    assemble_final_video()
