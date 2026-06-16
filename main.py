"""
Orchestrator — runs each stage of the pipeline in order.

This is the entry point. GitHub Actions calls `python main.py` daily.
Each stage is wrapped in try/except so one failure doesn't kill the whole run.

Pipeline:
  1. Pick a random seed word
  2. TRACK A: Scrape images for that word → Claude Vision reads the vibe
  3. TRACK B: Scrape text for the same word → 3x telephone game via Claude
  4. Merge both tracks into one surreal composite sentence
  5. Kling 1.6 generates a 5-second video via fal.ai
  6. Upload video to R2, save metadata to Postgres + log.json
  7. Generate Kling O1 transitions (previous → new, new → first/loop)
  8. Reassemble the full clips+transitions loop, republish as HLS
  9. Clean up temp files
"""

import json
import os
import random
import shutil
import sys
from datetime import datetime, timezone

import config
from scraper.text_scraper import scrape_text
from scraper.image_scraper import scrape_images
from pipeline.image_analyzer import analyze_images
from pipeline.text_synthesizer import synthesize_text
from pipeline.merger import merge
from generator.video_gen import generate_video
from generator.transition_gen import generate_transition
from assembler.assemble import assemble_final_video
from uploader.r2_upload import upload_video, get_unique_filename
from db.database import (
    init_db, insert_run, update_transition_url,
    get_all_runs_ordered, get_first_run, count_runs,
)


# Temp directory used by image_scraper for downloads
TEMP_DIR = os.path.join(config.OUTPUT_DIR, "temp")

# Hard cap on the total number of runs. Once the database holds this many
# entries, the project is considered complete and the pipeline exits cleanly.
MAX_RUNS = 100


def pick_seed_word():
    """
    Read the seed words file and pick one at random.

    open() with "r" returns a file object. Using `with` (a context manager)
    automatically closes the file when the block ends — no need to call
    f.close() manually. This is the Pythonic way to handle files.
    """
    with open(config.SEED_WORDS_FILE, "r") as f:
        # .read().splitlines() splits on newlines without keeping the \n
        # (unlike .readlines() which keeps trailing newlines)
        words = [w.strip() for w in f.read().splitlines() if w.strip()]
    return random.choice(words)


def run_stage(name, fn):
    """
    Run a pipeline stage with logging and error handling.

    In Python, functions are first-class — you can pass them around
    like any other value. `fn` here is a callable (a function).
    """
    print(f"\nRunning: {name}")
    print("-" * 40)
    try:
        result = fn()
        print(f"  ✓ {name} complete")
        return result
    except Exception as e:
        # f-strings: Python's template literals. The {e} inserts the
        # exception's string representation.
        print(f"  ✗ {name} failed: {e}")
        return None


def save_log_entry(seed_word, sentence, video_url, date_str, style_mode=None):
    """
    Append a new entry to output/log.json (local backup).

    This is kept as a fallback and debugging aid even though
    Postgres is the source of truth. The video field now stores
    either an R2 URL or a local path depending on configuration.
    """
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    if os.path.exists(config.OUTPUT_LOG):
        with open(config.OUTPUT_LOG, "r") as f:
            log = json.load(f)
    else:
        log = []

    log.append({
        "date": date_str,
        "seed": seed_word,
        "sentence": sentence,
        "video_url": video_url,
        "style_mode": style_mode,
    })

    with open(config.OUTPUT_LOG, "w") as f:
        json.dump(log, f, indent=2)


def cleanup_temp():
    """
    Remove the temp directory and everything in it.

    shutil.rmtree() is like `rm -rf` — removes a directory and all
    its contents recursively. We use it to clean up scraped images
    after the pipeline is done with them. output/videos/ is left intact.
    """
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        print("  Cleaned up temp directory")
    else:
        print("  No temp directory to clean")


def main():
    print("=" * 50)
    print("WE WERE HERE, BRIEFLY")
    print("=" * 50)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"\nDate: {today}")

    # --- Initialize database ---
    # Creates the runs table if it doesn't exist.
    # If Postgres isn't configured, this prints a message and continues.
    run_stage("Init database", init_db)

    # --- Enforce the hard cap on total runs ---
    # SELECT COUNT(*) FROM runs. If we've reached MAX_RUNS, the project is
    # complete: print the archive notice and exit cleanly (code 0) so the
    # GitHub Actions run is a success, not a failure.
    #
    # count_runs() returns None when Postgres isn't configured — in that
    # case we can't enforce the cap, so we continue as normal.
    run_count = count_runs()
    if run_count is not None and run_count >= MAX_RUNS:
        print("\n" + "=" * 50)
        print("We Were Here, Briefly is complete.")
        print(f"{MAX_RUNS} entries. The project is archived.")
        print("Disable the GitHub Actions cron to stop future runs.")
        print("=" * 50)
        sys.exit(0)

    # --- Pick a seed word ---
    # Both tracks use the same word so they're thematically linked
    seed_word = run_stage("Pick seed word", pick_seed_word)
    if not seed_word:
        print("No seed word — aborting.")
        return
    print(f"  Seed: {seed_word}")

    # --- TRACK A: Scrape images → Claude Vision ---
    images = run_stage(
        "Scrape images",
        lambda: scrape_images(seed_word)
    )

    image_vibe = run_stage(
        "Analyze images",
        lambda: analyze_images(images or [])
    )

    # --- TRACK B: Scrape text → 3x telephone game ---
    raw_text = run_stage(
        "Scrape text",
        lambda: scrape_text(seed_word)
    )

    synthesized = run_stage(
        "Synthesize text",
        lambda: synthesize_text(raw_text or "")
    )

    # --- Merge both tracks ---
    # merge() returns (sentence, style_mode_name) tuple
    merge_result = run_stage(
        "Merge tracks",
        lambda: merge(image_vibe or "", synthesized or "")
    )

    # Unpack the merge result — it's a tuple of (sentence, style_mode)
    if merge_result and isinstance(merge_result, tuple):
        sentence, style_mode = merge_result
    else:
        sentence = merge_result or ""
        style_mode = None

    # --- Generate video ---
    # Check R2 for existing files with today's date and get a unique name
    base_filename = f"{today}.mp4"
    video_filename = get_unique_filename(base_filename)
    if video_filename != base_filename:
        print(f"  {base_filename} exists in R2, using {video_filename}")
    video_path = os.path.join(config.VIDEO_OUTPUT_DIR, video_filename)

    # Ensure video output directory exists
    os.makedirs(config.VIDEO_OUTPUT_DIR, exist_ok=True)

    generated = run_stage(
        "Generate video",
        lambda: generate_video(sentence or "", video_path)
    )

    # --- Upload to R2 + save metadata ---
    video_url = None
    run_id = None

    if generated and os.path.exists(video_path):
        # Try uploading to R2 — returns public URL or None
        video_url = run_stage(
            "Upload video to R2",
            lambda: upload_video(video_path, video_filename)
        )

        # Insert into Postgres — returns row id or None
        run_id = run_stage(
            "Save to database",
            lambda: insert_run(today, seed_word, sentence or "",
                               video_url, style_mode)
        )

        # Always write to log.json as local backup.
        # Store R2 URL if available, otherwise local path.
        log_video = video_url or f"videos/{video_filename}"
        run_stage(
            "Save log backup",
            lambda: save_log_entry(seed_word, sentence or "",
                                   log_video, today, style_mode)
        )

        # Delete local video after successful R2 upload
        if video_url:
            os.remove(video_path)
            print(f"  Deleted local file: {video_path}")
    else:
        print("\n  Skipping upload/log — no video file on disk")

    # --- Transition stages (replaces datamosh) ---
    # Build the seamless loop: a Kling O1 transition from the PREVIOUS run
    # to this new run, plus a loop-closing transition from this new run
    # back to the very first run. Then reassemble the full HLS stream.
    #
    # These only run if we actually inserted a new run this time.
    if run_id and video_url:
        # Transition: previous run → new run.
        # get_all_runs_ordered() is date/id ASC, so the new run is last
        # and the previous run is second-to-last.
        all_ordered = get_all_runs_ordered() or []
        previous_run = all_ordered[-2] if len(all_ordered) >= 2 else None

        if previous_run:
            transition_url = run_stage(
                "Generate transition (previous → new)",
                lambda: generate_transition(
                    previous_run["video_url"], video_url,
                    previous_run["id"], run_id,
                    seed_a=previous_run.get("seed"), seed_b=seed_word,
                )
            )
            if transition_url:
                run_stage(
                    "Update previous transition URL",
                    lambda: update_transition_url(previous_run["id"],
                                                  transition_url)
                )

        # Loop-closing transition: new run → first run.
        first_run = get_first_run()
        if first_run and first_run["id"] != run_id:
            loop_url = run_stage(
                "Generate loop-closing transition (new → first)",
                lambda: generate_transition(
                    video_url, first_run["video_url"],
                    run_id, first_run["id"],
                    seed_a=seed_word, seed_b=first_run.get("seed"),
                )
            )
            if loop_url:
                run_stage(
                    "Update loop-closing transition URL",
                    lambda: update_transition_url(run_id, loop_url)
                )

        # Reassemble + republish the full HLS stream.
        run_stage("Assemble final video", assemble_final_video)
    else:
        print("\n  Skipping transitions/assembly — no new run this time")

    # --- Clean up temp files ---
    run_stage("Clean up", cleanup_temp)

    print("\n" + "=" * 50)
    print("Done. We were here, briefly.")
    print("=" * 50)


# This is Python's version of `if (require.main === module)` in Node.
# __name__ is "__main__" only when this file is run directly
# (not when imported by another file).
if __name__ == "__main__":
    main()
