"""
Image analyzer — sends scraped images to Claude Vision
to read the vibe.

Each image is a fragment left behind by someone. Claude doesn't
describe what it sees — it describes what it feels like as a
faint human trace. The residue of presence.
"""

import base64
import mimetypes
import os

from anthropic import Anthropic

import config

print("image_analyzer loaded")

SYSTEM_PROMPT = """You are perceiving fragments left behind by people.
Describe not what you see, but what it feels like as a faint human
trace. One sentence per image. Be strange. Stay grounded in the
mundane — offices, parking lots, waiting rooms, receipts.
No poetry. No metaphors about time or the cosmos.
Just the residue of someone having been here."""


def encode_image(filepath):
    """
    Read an image file and return it as a base64-encoded string
    along with its MIME type.

    base64 encoding converts binary data (the raw image bytes) into
    a text string that can be sent in a JSON API request. It's like
    btoa() in JS but for arbitrary binary data.

    Returns a tuple: (base64_string, mime_type)
    """
    # mimetypes.guess_type() looks at the file extension to determine
    # the MIME type (e.g., ".jpg" → "image/jpeg"). Returns (type, encoding).
    mime_type, _ = mimetypes.guess_type(filepath)
    # Default to JPEG if we can't determine the type
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"

    # "rb" = read + binary mode. Images are binary files, not text.
    with open(filepath, "rb") as f:
        raw_bytes = f.read()

    # base64.b64encode() returns bytes, .decode("utf-8") converts
    # those bytes to a regular string for JSON serialization.
    encoded = base64.b64encode(raw_bytes).decode("utf-8")

    return encoded, mime_type


def analyze_images(image_paths):
    """
    Send all images to Claude Vision in a single API call.

    Claude's vision capability accepts images as base64-encoded data
    in the message content. We send all images at once so Claude can
    perceive them as a collection of fragments.

    Returns a string: all impressions joined by " / "
    """
    if not image_paths:
        print("  No images to analyze")
        return ""

    if not config.ANTHROPIC_API_KEY:
        print("  No ANTHROPIC_API_KEY — skipping analysis")
        return ""

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Build the message content: alternating images and text prompts.
    # Claude's API accepts a list of "content blocks" — each can be
    # text or an image. This is different from OpenAI where images
    # go in a separate field.
    content_blocks = []

    # Keep track of how many images we successfully encode
    loaded_count = 0

    for filepath in image_paths:
        if not os.path.exists(filepath):
            print(f"  Skipping missing file: {filepath}")
            continue

        try:
            encoded, mime_type = encode_image(filepath)

            # Each image is a content block with type "image" and
            # source type "base64". This tells Claude it's inline
            # binary data, not a URL to fetch.
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": encoded,
                },
            })
            loaded_count += 1
        except Exception as e:
            print(f"  Failed to encode {filepath}: {e}")
            continue

    if not content_blocks:
        print("  No images could be encoded")
        return ""

    # Add a text prompt after all the images
    content_blocks.append({
        "type": "text",
        "text": (
            f"You are looking at {loaded_count} fragments scraped "
            f"from the internet. For each image, write one sentence "
            f"about what it feels like as a trace of human presence. "
            f"Number them 1 through {loaded_count}."
        ),
    })

    print(f"  Sending {loaded_count} images to Claude Vision...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": content_blocks}
        ],
    )

    raw_response = response.content[0].text.strip()
    print(f"  Raw response:\n    {raw_response}")

    # Split numbered lines and rejoin with " / " separator.
    # The response comes back as "1. ...\n2. ...\n3. ..." etc.
    # We strip the numbers and join with slashes.
    lines = [line.strip() for line in raw_response.split("\n") if line.strip()]
    # Remove numbering prefixes like "1. " or "1) "
    cleaned = []
    for line in lines:
        # lstrip("0123456789") removes leading digits,
        # then we strip ". " or ") " prefixes
        stripped = line.lstrip("0123456789").lstrip(".)" ).strip()
        if stripped:
            cleaned.append(stripped)

    result = " / ".join(cleaned) if cleaned else raw_response
    print(f"\n  Image impressions: {result}")

    return result


# Quick test when running directly
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # Pass image paths as command line arguments
        paths = sys.argv[1:]
    else:
        # Look for any images in output/temp/
        temp_dir = os.path.join(config.OUTPUT_DIR, "temp")
        if os.path.exists(temp_dir):
            paths = [
                os.path.join(temp_dir, f)
                for f in os.listdir(temp_dir)
                if f.endswith((".jpg", ".jpeg", ".png", ".webp"))
            ]
        else:
            paths = []

    if paths:
        result = analyze_images(paths)
        print(f"\nResult: {result}")
    else:
        print("No images found. Run image_scraper.py first.")
