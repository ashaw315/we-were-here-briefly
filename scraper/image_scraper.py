"""
Image scraper — fetches images from the web based on a seed word.

Tries three sources in order:
  1. Bing Image search (best variety, no API key needed)
  2. Wikimedia Commons API (reliable, freely licensed images)
  3. Flickr public search (HTML scraping fallback)

Downloads images to output/temp/ and returns a list of local file paths.
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote

import config

print("image_scraper loaded")

# output/temp/ is our scratch space — cleaned up after each run
TEMP_DIR = os.path.join(config.OUTPUT_DIR, "temp")

# Browser-like headers for Bing and Flickr.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Wikimedia needs a polite user-agent, not a browser spoof
WIKI_HEADERS = {
    "User-Agent": "WeWereHereBriefly/1.0 (art project; no scraping at scale)"
}


def scrape_bing_images(word, count=5):
    """
    Fetch image URLs from Bing Image search results.

    Bing embeds full-size image URLs in the HTML as "murl" (media URL)
    values inside HTML-encoded JSON. This is more reliable than Google
    (which blocks scrapers) or DuckDuckGo (which rate-limits the API).

    No API key needed — we just parse the public search results page.

    Returns a list of image URL strings.
    """
    url = "https://www.bing.com/images/search"
    params = {
        "q": word,
        "form": "HDRSC2",
        "first": "1",
    }

    print(f"  Searching Bing Images for: {word}")
    response = requests.get(url, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()

    # Bing embeds full-size image URLs in the page HTML as "murl" values.
    # They appear in HTML-encoded JSON like:  murl&quot;:&quot;https://...&quot;
    # &quot; is the HTML entity for a double quote character.
    # re.findall() extracts all matching URLs from the raw HTML string.
    murls = re.findall(
        r'murl&quot;:&quot;(https?://[^&]+?)&quot;',
        response.text,
    )

    # Deduplicate while preserving order.
    # dict.fromkeys() creates a dict with the URLs as keys (which are
    # unique by definition), then list() extracts just the keys.
    # This is a Python idiom for deduplicating a list in insertion order.
    image_urls = list(dict.fromkeys(murls))

    print(f"  Found {len(image_urls)} image URLs from Bing")
    return image_urls[:count]


def scrape_wikimedia_images(word, count=5):
    """
    Fetch image URLs from Wikimedia Commons using their public API.

    Wikimedia Commons has millions of freely-licensed images and
    a proper API — no scraping needed. This is the most reliable
    source since it won't block us.

    Returns a list of image URL strings.
    """
    # The Wikimedia API lets us search for images by keyword.
    # We use the `query` action with `generator=search` to find
    # files in the "File:" namespace (namespace 6 = files/images).
    api_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",       # Use search as the page generator
        "gsrsearch": word,            # The search query
        "gsrnamespace": 6,            # Namespace 6 = File: (images)
        "gsrlimit": count * 2,        # Request extra in case some aren't images
        "prop": "imageinfo",          # We want info about each image
        "iiprop": "url|size|mime",    # Specifically: the URL, size, and MIME type
        "iiurlwidth": 640,            # Request a thumbnail max 640px wide (less likely to be rate-limited)
    }

    print(f"  Searching Wikimedia Commons for: {word}")
    response = requests.get(api_url, params=params, headers=WIKI_HEADERS, timeout=15)
    response.raise_for_status()

    data = response.json()

    # The API returns pages nested under query.pages.
    # Each page has an imageinfo list with URL details.
    pages = data.get("query", {}).get("pages", {})

    image_urls = []
    for page_id, page in pages.items():
        imageinfo = page.get("imageinfo", [])
        if not imageinfo:
            continue

        info = imageinfo[0]
        mime = info.get("mime", "")

        # Only keep actual images, not PDFs or SVGs
        if not mime.startswith("image/") or mime in ("image/svg+xml",):
            continue

        # Prefer the thumbnail URL (pre-sized to 640px width)
        # Fall back to the original URL if no thumbnail
        url = info.get("thumburl") or info.get("url")
        if url:
            image_urls.append(url)

        if len(image_urls) >= count:
            break

    print(f"  Found {len(image_urls)} image URLs from Wikimedia Commons")
    return image_urls[:count]


def scrape_flickr_images(word, count=5):
    """
    Fallback: scrape image URLs from Flickr's public search.

    Flickr's search page is more scraper-friendly than most.
    We look for image URLs in the page's HTML.

    Returns a list of image URL strings.
    """
    url = "https://www.flickr.com/search/"
    params = {"text": word}

    print(f"  Falling back to Flickr for: {word}")
    response = requests.get(url, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    image_urls = []

    # Flickr embeds image URLs in the page's JavaScript as JSON data.
    # Look for the "live" photo URLs in script tags.
    scripts = soup.find_all("script")
    for script in scripts:
        if not script.string:
            continue
        # Flickr uses //live.staticflickr.com/ for photo URLs
        urls = re.findall(
            r'((?:https?:)?//live\.staticflickr\.com/[^"\'\\]+\.(?:jpg|jpeg|png))',
            script.string,
        )
        for found_url in urls:
            clean = unquote(found_url)
            if clean not in image_urls:
                image_urls.append(clean)
            if len(image_urls) >= count:
                break
        if len(image_urls) >= count:
            break

    # Also check <img> tags directly.
    # Flickr serves most image src as protocol-relative (//live.staticflickr...)
    # so we check for the domain and prepend https: if needed.
    if len(image_urls) < count:
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "live.staticflickr.com" in src:
                if src.startswith("//"):
                    src = "https:" + src
                if src not in image_urls:
                    image_urls.append(src)
                if len(image_urls) >= count:
                    break

    print(f"  Found {len(image_urls)} image URLs from Flickr")
    return image_urls[:count]


def download_images(urls):
    """
    Download a list of image URLs to output/temp/.

    Returns a list of local file paths for images that
    were successfully downloaded.
    """
    # os.makedirs with exist_ok=True is like `mkdir -p`
    os.makedirs(TEMP_DIR, exist_ok=True)

    paths = []
    for i, url in enumerate(urls):
        # enumerate() gives you (index, value) pairs — like
        # urls.forEach((url, i) => ...) in JS but as a loop.

        # Delay between downloads to avoid rate limiting.
        # Wikimedia throttles rapid-fire requests aggressively.
        if i > 0:
            time.sleep(3)

        try:
            print(f"  Downloading image {i + 1}/{len(urls)}...")
            # Use polite wiki headers for Wikimedia URLs, browser headers for others
            dl_headers = WIKI_HEADERS if "wikimedia.org" in url or "wikipedia.org" in url else HEADERS

            # Try up to 2 times with exponential backoff on 429 (rate limit).
            # This is a common pattern for dealing with rate-limited APIs.
            resp = None
            for attempt in range(2):
                resp = requests.get(url, headers=dl_headers, timeout=15, stream=True)
                if resp.status_code == 429:
                    wait = 5 * (attempt + 1)  # 5s, then 10s
                    print(f"    Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                break

            resp.raise_for_status()

            # Determine file extension from the URL or content type.
            # Default to .jpg if we can't figure it out.
            content_type = resp.headers.get("Content-Type", "")
            if "png" in content_type or url.lower().endswith(".png"):
                ext = ".png"
            elif "webp" in content_type or url.lower().endswith(".webp"):
                ext = ".webp"
            else:
                ext = ".jpg"

            filepath = os.path.join(TEMP_DIR, f"img_{i}{ext}")

            # Write binary data to file.
            # "wb" = write + binary mode (not text mode).
            # We use iter_content to stream in chunks instead of
            # loading the whole image into memory at once.
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify the file isn't empty or suspiciously tiny
            # (could be a 1x1 tracking pixel or error page)
            size = os.path.getsize(filepath)
            if size < 5000:  # less than 5KB is probably not a real photo
                print(f"    Skipped (too small: {size} bytes)")
                os.remove(filepath)
                continue

            paths.append(filepath)
            print(f"    Saved: {filepath} ({size:,} bytes)")

        except Exception as e:
            print(f"    Failed: {e}")
            continue

    return paths


def scrape_images(seed_word, count=5):
    """
    Main entry point: scrape images for the given seed word.

    Tries sources in order: Bing → Wikimedia Commons → Flickr.
    Downloads and returns local file paths.

    Returns a list of local file paths to downloaded images.
    """
    image_urls = []

    # Try Bing first (best variety, no API key needed)
    try:
        image_urls = scrape_bing_images(seed_word, count=count)
    except Exception as e:
        print(f"  Bing Images failed: {e}")

    # Fall back to Wikimedia Commons (reliable, API-based)
    if not image_urls:
        try:
            image_urls = scrape_wikimedia_images(seed_word, count=count)
        except Exception as e:
            print(f"  Wikimedia Commons failed: {e}")

    # Last resort: Flickr HTML scraping
    if not image_urls:
        try:
            image_urls = scrape_flickr_images(seed_word, count=count)
        except Exception as e:
            print(f"  Flickr also failed: {e}")
            return []

    if not image_urls:
        print("  No image URLs found from any source")
        return []

    # Download all found images
    paths = download_images(image_urls)
    print(f"  Successfully downloaded {len(paths)} images")

    return paths


# Quick test when running directly
if __name__ == "__main__":
    from scraper.text_scraper import pick_seed_word
    word = pick_seed_word()
    result = scrape_images(word)
    print(f"\nDownloaded {len(result)} images for '{word}':")
    for p in result:
        print(f"  {p}")
