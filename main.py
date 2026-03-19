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
  6. Save to output/videos/, update output/log.json
  7. Clean up temp files
"""

import json
import os
import random
import shutil
from datetime import datetime, timezone

import config
from scraper.text_scraper import scrape_text
from scraper.image_scraper import scrape_images
from pipeline.image_analyzer import analyze_images
from pipeline.text_synthesizer import synthesize_text
from pipeline.merger import merge
from generator.video_gen import generate_video


# Temp directory used by image_scraper for downloads
TEMP_DIR = os.path.join(config.OUTPUT_DIR, "temp")


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


def save_log_entry(seed_word, sentence, video_filename, date_str):
    """
    Append a new entry to output/log.json.

    json.load() reads JSON from a file into Python dicts/lists.
    json.dump() writes Python objects back out as JSON.
    """
    # os.makedirs with exist_ok=True is like `mkdir -p` — creates
    # the directory and all parents, no error if it already exists.
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # Load existing log or start fresh
    if os.path.exists(config.OUTPUT_LOG):
        with open(config.OUTPUT_LOG, "r") as f:
            log = json.load(f)
    else:
        log = []

    # Video path is relative — the frontend uses this to build
    # the <video> src. "videos/2026-03-18.mp4" resolves from output/.
    log.append({
        "date": date_str,
        "seed": seed_word,
        "sentence": sentence,
        "video": f"videos/{video_filename}" if video_filename else None,
    })

    with open(config.OUTPUT_LOG, "w") as f:
        # indent=2 pretty-prints the JSON (like JSON.stringify(obj, null, 2))
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
        # lambda creates an anonymous function (like arrow functions in JS).
        # We need it here because scrape_images() takes an argument,
        # but run_stage() expects a zero-argument callable.
        lambda: scrape_images(seed_word)
    )

    image_vibe = run_stage(
        "Analyze images",
        lambda: analyze_images(images or [])
    )

    # --- TRACK B: Scrape text → 3x telephone game ---
    # Pass the same seed_word so both tracks share a theme
    raw_text = run_stage(
        "Scrape text",
        lambda: scrape_text(seed_word)
    )

    synthesized = run_stage(
        "Synthesize text",
        lambda: synthesize_text(raw_text or "")
    )

    # --- Merge both tracks ---
    sentence = run_stage(
        "Merge tracks",
        lambda: merge(image_vibe or "", synthesized or "")
    )

    # --- Generate video ---
    video_filename = f"{today}.mp4"
    video_path = os.path.join(config.VIDEO_OUTPUT_DIR, video_filename)

    # Ensure video output directory exists
    os.makedirs(config.VIDEO_OUTPUT_DIR, exist_ok=True)

    generated = run_stage(
        "Generate video",
        lambda: generate_video(sentence or "", video_path)
    )

    # --- Save log entry ---
    # Only record the video filename if generation succeeded
    final_video = video_filename if generated else None
    run_stage(
        "Save log",
        lambda: save_log_entry(seed_word, sentence or "", final_video, today)
    )

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
