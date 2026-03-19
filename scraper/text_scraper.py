"""
Text scraper — fetches a Wikipedia page for a random seed word
and returns clean plaintext.

Wikipedia is used because it's freely accessible, doesn't require
authentication, and contains dense human-written text on almost
any topic. The mundanity of an encyclopedia entry about "hinge" or
"fluorescent" is exactly the kind of trace this project feeds on.
"""

import random
import requests
from bs4 import BeautifulSoup

import config

print("text_scraper loaded")

# Shared headers — Wikipedia blocks requests without a User-Agent
HEADERS = {
    "User-Agent": "WeWereHereBriefly/1.0 (art project; no scraping at scale)"
}


def pick_seed_word():
    """
    Read the seed words file and pick one at random.

    Returns a single word/phrase stripped of whitespace.
    """
    with open(config.SEED_WORDS_FILE, "r") as f:
        # List comprehension — Python's compact way to transform a list.
        # This is equivalent to:
        #   words = []
        #   for line in f.read().splitlines():
        #       stripped = line.strip()
        #       if stripped:
        #           words.append(stripped)
        words = [w.strip() for w in f.read().splitlines() if w.strip()]
    return random.choice(words)


def is_disambiguation_page(html):
    """
    Check if a Wikipedia HTML page is a disambiguation page.

    Disambiguation pages are lists of links ("X may refer to...")
    rather than real articles. They produce thin, list-heavy text
    that the synthesizer can't do much with.

    We detect them two ways:
      1. The page has a <div> with class "dmbox-disambig" (Wikipedia's
         internal marker for disambiguation boxes)
      2. The extracted text starts with "may refer to" — the classic
         disambiguation opener
    """
    soup = BeautifulSoup(html, "html.parser")

    # Check for the disambiguation box CSS class
    if soup.find("div", class_="dmbox-disambig"):
        return True

    # Check for the "may refer to" phrase in the first paragraph.
    # .find("p") grabs the first <p> tag in the document.
    first_p = soup.find("p")
    if first_p:
        text = first_p.get_text().lower()
        if "may refer to" in text or "can refer to" in text:
            return True

    return False


def get_first_linked_article(html):
    """
    From a disambiguation page, grab the URL of the first real article link.

    Disambiguation pages are basically lists of links. We grab the first
    one that points to an actual article (not a section link, not a
    special page, not another disambiguation page).

    Returns a URL string, or None if nothing suitable is found.
    """
    soup = BeautifulSoup(html, "html.parser")
    content_div = soup.find("div", {"id": "mw-content-text"})
    if not content_div:
        return None

    # Look through all <li> tags in the content area — these are
    # the disambiguation list items.
    for li in content_div.find_all("li"):
        link = li.find("a", href=True)
        if not link:
            continue

        href = link["href"]

        # We want links to real articles: /wiki/Something
        # Skip anchors (#), special pages, files, categories, etc.
        if not href.startswith("/wiki/"):
            continue
        if ":" in href.split("/wiki/")[1]:  # Skips File:, Category:, etc.
            continue
        if "#" in href:
            continue

        full_url = "https://en.wikipedia.org" + href
        return full_url

    return None


def fetch_wikipedia(word):
    """
    Fetch the Wikipedia page for the given word.

    Uses the Wikipedia API to search for the best matching article,
    then fetches the actual HTML page. If the result is a disambiguation
    page, follows the first linked article to get real content.

    Returns raw HTML string, or None if nothing is found.
    """
    # Step 1: Use Wikipedia's search API to find the best article title.
    # This handles redirects and missing pages gracefully.
    search_url = "https://en.wikipedia.org/w/api.php"
    # `params` is a dict that gets URL-encoded as query string parameters
    # (like new URLSearchParams() in JS)
    params = {
        "action": "opensearch",
        "search": word,
        "limit": 5,          # Request several results in case the first is a disambig
        "format": "json",
    }
    print(f"  Searching Wikipedia for: {word}")
    search_resp = requests.get(search_url, params=params, headers=HEADERS, timeout=15)
    search_resp.raise_for_status()

    # opensearch returns: [query, [titles], [descriptions], [urls]]
    data = search_resp.json()

    # data[1] is the list of matching titles — if empty, no article found
    if not data[1]:
        print(f"  No Wikipedia article found for: {word}")
        return None

    # Try each search result until we find a real article (not a disambig)
    for i, page_url in enumerate(data[3]):
        print(f"  Fetching: {page_url}")

        # requests.get() is like fetch() in JS, but synchronous.
        # The `timeout` param prevents hanging forever on bad connections.
        response = requests.get(page_url, headers=HEADERS, timeout=15)

        # .raise_for_status() throws an exception for 4xx/5xx responses
        # (like throwing on !response.ok in fetch)
        response.raise_for_status()
        html = response.text

        # Check if this is a disambiguation page
        if is_disambiguation_page(html):
            print(f"  Disambiguation page detected — looking for real article...")

            # Try to follow the first linked article from the disambig page
            linked_url = get_first_linked_article(html)
            if linked_url:
                print(f"  Following link: {linked_url}")
                linked_resp = requests.get(linked_url, headers=HEADERS, timeout=15)
                linked_resp.raise_for_status()
                linked_html = linked_resp.text

                # Make sure the linked article isn't ALSO a disambig
                if not is_disambiguation_page(linked_html):
                    return linked_html

            # If the linked article was also a disambig (or no link found),
            # try the next search result
            print(f"  Trying next search result...")
            continue

        # Not a disambig — we have a real article
        return html

    # All search results were disambig pages
    print(f"  All results were disambiguation pages for: {word}")
    return None


def extract_text(html):
    """
    Strip all HTML tags and return clean plaintext from a Wikipedia page.

    BeautifulSoup parses HTML into a tree you can query with CSS-like
    selectors. Think of it as a server-side DOM.
    """
    # "html.parser" is Python's built-in parser — no extra install needed
    soup = BeautifulSoup(html, "html.parser")

    # Wikipedia's main content lives inside <div id="mw-content-text">
    content_div = soup.find("div", {"id": "mw-content-text"})
    if not content_div:
        return ""

    # Remove elements that add noise: tables, navboxes, references, etc.
    # .decompose() removes a tag AND its contents from the tree entirely
    for tag in content_div.find_all(["table", "sup", "style", "script"]):
        tag.decompose()

    # Remove elements with classes that indicate non-article content
    for cls in ["navbox", "mw-editsection", "reference", "reflist", "toc",
                "dmbox-disambig", "hatnote"]:
        for tag in content_div.find_all(class_=cls):
            tag.decompose()

    # .get_text() extracts all remaining text, joining with spaces.
    # separator=" " prevents words from smashing together when tags
    # are removed (e.g., "<b>hello</b><i>world</i>" → "hello world")
    text = content_div.get_text(separator=" ", strip=True)

    return text


def scrape_text(seed_word=None):
    """
    Main entry point: pick a word, fetch Wikipedia, return clean text.

    If no seed_word is provided, picks one at random from the word list.
    Retries up to 3 times with different words if the first pick fails.
    """
    if not seed_word:
        seed_word = pick_seed_word()

    # Try the given word first, then fall back to random picks.
    # range(3) gives [0, 1, 2] — three attempts max.
    attempts = [seed_word] + [pick_seed_word() for _ in range(2)]

    for attempt in attempts:
        print(f"  Seed word: {attempt}")

        html = fetch_wikipedia(attempt)
        if not html:
            print(f"  Retrying with different word...")
            continue

        text = extract_text(html)
        if not text:
            print(f"  No text extracted, retrying...")
            continue

        # Show a preview so we know it worked
        preview = text[:200] + "..." if len(text) > 200 else text
        print(f"  Scraped {len(text)} chars")
        print(f"  Preview: {preview}")

        return text

    print("  All attempts failed")
    return ""


# Quick test when running this file directly
if __name__ == "__main__":
    result = scrape_text()
    print(f"\nFull length: {len(result)} characters")
