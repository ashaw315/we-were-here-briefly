"""
Video generator — sends the merged sentence to Kling 1.6
via fal.ai and saves the result.

This is the final step: the composite prompt becomes a 5-second video.
The video is proof that someone passed through. A trace of traces,
briefly moving.

fal.ai works differently from OpenAI:
  - You submit a job and get a request ID back
  - The job runs asynchronously on fal's GPU cluster
  - You poll for completion (or use subscribe() which does this for you)
  - When done, you get a URL to the generated video
  - Download and save before the URL expires

The fal_client library wraps all of this into a single subscribe() call
that blocks until the result is ready — similar to a Promise that
auto-resolves. Under the hood it's polling, but you don't have to
manage that yourself.
"""

import os
import traceback

import requests

import fal_client

import config

print("video_gen loaded")


def on_queue_update(update):
    """
    Callback for fal_client.subscribe() — called each time
    the job's queue position changes.

    fal_client.subscribe() accepts an optional on_queue_update
    callback. The `update` object has a `.status` field and
    sometimes a `.position` field (your place in the queue).

    This is a "callback pattern" — you pass a function to another
    function, and it gets called later when something happens.
    Same idea as addEventListener() in JS.
    """
    if isinstance(update, fal_client.InProgress):
        # Job is running — log any partial output (usually empty for video)
        print(f"  Generating... {update.logs if hasattr(update, 'logs') else ''}")


def generate_video(prompt, output_path):
    """
    Generate a 5-second video via Kling 1.6 on fal.ai.

    Uses fal_client.subscribe() which:
      1. Submits the generation request to fal's API
      2. Automatically polls for completion
      3. Returns the result when the video is ready

    This is a blocking call — it won't return until the video
    is generated (typically 1-3 minutes). Think of it like
    `await fetch()` in JS, but it's doing repeated polling
    under the hood instead of a single HTTP request.

    Args:
        prompt: The composite surreal sentence to visualize.
        output_path: Where to save the video (e.g., output/videos/2026-03-18.mp4).

    Returns the output_path on success, None on failure.
    """
    if not prompt or not prompt.strip():
        print("  No prompt — skipping video generation")
        return None

    if not config.FAL_KEY:
        print("  No FAL_KEY — skipping video generation")
        return None

    # Set the FAL_KEY environment variable — fal_client reads it
    # automatically for authentication (similar to how the Anthropic
    # client reads ANTHROPIC_API_KEY, but fal uses an env var directly
    # instead of a constructor parameter).
    os.environ["FAL_KEY"] = config.FAL_KEY

    print(f"  Generating video with Kling 1.6 via fal.ai...")
    print(f"  Prompt: {prompt}")
    print(f"  This may take 1-3 minutes...")

    # fal_client.subscribe() is the main way to run a model on fal.ai.
    #
    # How it works:
    #   1. Sends a POST to fal's API with your model ID and arguments
    #   2. Gets back a request_id (the job is now queued on their GPUs)
    #   3. Polls GET /requests/{id}/status every few seconds
    #   4. When status is "completed", fetches the result
    #   5. Returns the result dict
    #
    # The `arguments` dict is model-specific — each model on fal.ai
    # has its own schema. For Kling text-to-video, the key fields are
    # prompt, duration, and aspect_ratio.
    # Wrap the entire fal API call + download in try/except so we
    # can surface the full error details. fal_client can throw several
    # different exception types depending on what went wrong:
    #   - Authentication errors (bad FAL_KEY)
    #   - Validation errors (bad model ID or arguments)
    #   - Queue errors (job timed out or was cancelled)
    #   - HTTP errors (fal's servers are down)
    #
    # type(e).__name__ gives us the class name of the exception
    # (like error.constructor.name in JS). traceback.format_exc()
    # gives us the full stack trace as a string.
    try:
        result = fal_client.subscribe(
            "fal-ai/kling-video/v1.6/standard/text-to-video",
            arguments={
                "prompt": prompt,
                "duration": "5",          # 5-second video
                "aspect_ratio": "16:9",   # Widescreen — fills the viewport
            },
            with_logs=True,
            on_queue_update=on_queue_update,
        )
    except Exception as e:
        # Print the exception type and message
        print(f"  ✗ fal.ai API call failed")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {e}")

        # Some fal exceptions carry extra context — check for common
        # attributes that might contain the raw API response.
        # hasattr() checks if an object has a named attribute
        # (like 'status' in error or error.hasOwnProperty('status') in JS).
        if hasattr(e, "status"):
            print(f"  HTTP status: {e.status}")
        if hasattr(e, "body"):
            print(f"  Response body: {e.body}")
        if hasattr(e, "response"):
            resp = e.response
            # The response object might be an httpx Response or similar
            if hasattr(resp, "status_code"):
                print(f"  Response status: {resp.status_code}")
            if hasattr(resp, "text"):
                print(f"  Response text: {resp.text}")
            elif hasattr(resp, "content"):
                print(f"  Response content: {resp.content}")

        # Print the full traceback for debugging.
        # traceback.format_exc() captures the current exception's
        # stack trace as a string — equivalent to printing the full
        # Error.stack in JS.
        print(f"\n  Full traceback:")
        print(f"  {traceback.format_exc()}")

        return None

    # --- Download the generated video ---

    # The result dict contains a "video" key with a "url" field
    # pointing to the generated video on fal's CDN.
    # These URLs are temporary — download immediately.
    video_url = result.get("video", {}).get("url")
    if not video_url:
        print(f"  ✗ No video URL in response")
        print(f"  Full result: {result}")
        return None

    print(f"  Video ready: {video_url}")
    print(f"  Downloading...")

    try:
        # Download the video file — same pattern as downloading an image,
        # but videos are larger so we stream in chunks.
        video_response = requests.get(video_url, timeout=120, stream=True)
        video_response.raise_for_status()

        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Write video bytes to disk in chunks.
        # "wb" = write + binary mode.
        # iter_content(chunk_size) yields the response body in pieces
        # so we don't load the entire video into memory at once.
        with open(output_path, "wb") as f:
            for chunk in video_response.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size = os.path.getsize(output_path)
        print(f"  Saved: {output_path} ({file_size:,} bytes)")

        return output_path

    except Exception as e:
        print(f"  ✗ Video download failed")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {e}")
        print(f"  Video URL was: {video_url}")
        print(f"\n  Full traceback:")
        print(f"  {traceback.format_exc()}")
        return None


# Quick test when running directly
if __name__ == "__main__":
    from datetime import datetime, timezone

    test_prompt = (
        "A thermostat reading 72 degrees in a building that has been "
        "empty for eleven years, the display still glowing green next "
        "to a vending machine full of expired receipts."
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(config.VIDEO_OUTPUT_DIR, f"{today}-test.mp4")

    result = generate_video(test_prompt, path)
    if result:
        print(f"\nGenerated: {result}")
    else:
        print("\nGeneration failed or skipped.")
