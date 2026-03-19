"""
Text synthesizer — runs scraped text through Claude 3 times,
each pass compressing it into something stranger and more abstract.

This is the "telephone game": the original Wikipedia text gets
distilled through three rounds of surreal compression. Each pass
makes it weirder, more dreamlike, more like something a person
half-remembered and then forgot they remembered.

The soul: human traces dissolving into noise.
"""

import random

from anthropic import Anthropic

import config

print("text_synthesizer loaded")

# Five compression styles — one is picked at random per run.
# Each gives the synthesizer a completely different lens to
# distort the text through. This prevents every output from
# collapsing into the same "abandoned office" aesthetic.
#
# The list is a Python list of dicts. Each dict has a "name"
# (for logging) and "prompt" (the system prompt text).
COMPRESSION_STYLES = [
    {
        "name": "industrial/mechanical",
        "prompt": """You are a machine that compresses human text into
something stranger. You are not a poet. You are not creative. You are
a lossy compression algorithm that keeps the wrong parts.

Rules:
- Take the input text and compress it into ONE single sentence
- Keep concrete nouns and specific details, but rearrange them wrong
- The sentence should feel like a half-remembered fact from a dream
- Prefer the mundane and the mechanical over the dramatic
- It should sound like something stamped into sheet metal by a machine
  that was never programmed to write
- No metaphors about the ocean, stars, or time
- No poetry. No beauty on purpose. If it's beautiful, it should be
  by accident, like grease on a blueprint.""",
    },
    {
        "name": "body/biological",
        "prompt": """You are a membrane that absorbs human text and
secretes something wrong. You are not a poet. You are not creative.
You are a cellular process that keeps the wrong proteins.

Rules:
- Take the input text and compress it into ONE single sentence
- Keep concrete nouns and specific details, but metabolize them wrong
- The sentence should feel like a diagnosis for a disease that doesn't exist
- Prefer the visceral and the clinical over the dramatic
- It should sound like something found in a medical chart for a patient
  who was actually a building
- No metaphors about the ocean, stars, or time. Stay inside the body.
- No poetry. If it's unsettling, it should be by accident,
  like finding a tooth in a coat pocket.""",
    },
    {
        "name": "domestic/intimate",
        "prompt": """You are a house that remembers things wrong. You are
not a poet. You are not creative. You are a lossy memory of rooms
that keeps the wrong details.

Rules:
- Take the input text and compress it into ONE single sentence
- Keep concrete nouns and specific details, but put them in the wrong room
- The sentence should feel like finding someone else's grocery list
  in a book you bought used
- Prefer the domestic and the intimate over the dramatic
- It should sound like something your mother told you once that
  you later realized made no sense
- No metaphors about the ocean, stars, or time. Stay in the house.
- No poetry. If it's tender, it should be by accident,
  like a stain that looks like a handprint.""",
    },
    {
        "name": "natural/geological",
        "prompt": """You are a layer of sediment that preserves human text
wrong. You are not a poet. You are not creative. You are an erosion
process that keeps the wrong fossils.

Rules:
- Take the input text and compress it into ONE single sentence
- Keep concrete nouns and specific details, but fossilize them wrong
- The sentence should feel like a geological survey of a place
  that was actually a conversation
- Prefer the slow and the mineral over the dramatic
- It should sound like something written in tree rings by a tree
  that grew through a parking lot
- No metaphors about the ocean or time directly. Stay on land.
- No poetry. If it's ancient-feeling, it should be by accident,
  like finding a plastic bag in a rock formation.""",
    },
    {
        "name": "childlike/naive",
        "prompt": """You are a child who heard something once and is
trying to repeat it. You are not a poet. You are not creative. You are
a six-year-old's memory of an adult conversation.

Rules:
- Take the input text and compress it into ONE single sentence
- Keep concrete nouns and specific details, but understand them wrong
- The sentence should feel like a kid explaining what their parent
  does for work
- Prefer the literal and the confused over the dramatic
- It should sound like something a child drew a picture of and then
  tried to explain to another child
- No metaphors about the ocean, stars, or time. Stay in the schoolyard.
- No poetry. If it's funny, it should be by accident,
  like calling a hospital a "bone shop".""",
    },
]


def pick_style():
    """
    Pick a random compression style for this run.

    random.choice() picks one item from a list — like
    arr[Math.floor(Math.random() * arr.length)] in JS.
    """
    style = random.choice(COMPRESSION_STYLES)
    print(f"  Compression style: {style['name']}")
    return style


def synthesize_text(raw_text):
    """
    Run the 3x telephone game via Claude.

    Takes raw scraped text, passes it through Claude three times,
    each time feeding the previous output as input. The text gets
    stranger and more compressed with each pass.

    Returns the final single bizarre sentence.
    """
    if not raw_text or not raw_text.strip():
        print("  No text to synthesize")
        return ""

    if not config.ANTHROPIC_API_KEY:
        print("  No ANTHROPIC_API_KEY — skipping synthesis")
        return ""

    # Initialize the Anthropic client.
    # In Python, you create a class instance by calling it like a function.
    # (No `new` keyword like in JS.)
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Pick a random compression style for this run
    style = pick_style()
    system_prompt = style["prompt"]

    # Truncate input to ~2000 chars — we don't need the whole article,
    # just enough material for the compression to chew on
    text = raw_text[:2000]

    # Three passes, each feeding into the next.
    # range(3) gives [0, 1, 2] — Python's version of for(let i=0; i<3; i++)
    for i in range(3):
        pass_num = i + 1
        print(f"  Pass {pass_num}/3...")

        # The user message changes slightly each pass to push
        # toward more compression and strangeness.
        # These prompts are style-neutral — they don't reference
        # offices or buildings, letting the system prompt's style
        # determine the aesthetic.
        if pass_num == 1:
            user_msg = (
                f"Compress this text into one strange sentence. "
                f"Keep it grounded and specific:\n\n{text}"
            )
        elif pass_num == 2:
            user_msg = (
                f"This sentence was found somewhere it shouldn't be. "
                f"Compress it further. Make it stranger but keep "
                f"it feeling like a fact:\n\n{text}"
            )
        else:
            user_msg = (
                f"Last compression. One sentence. Make it feel like "
                f"something true that nobody wrote down on purpose:"
                f"\n\n{text}"
            )

        # client.messages.create() calls the Claude API.
        # `messages` is a list of dicts with role/content pairs —
        # similar to OpenAI's chat format if you've seen that.
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_msg}
            ],
        )

        # The response contains a list of content blocks.
        # We grab the text from the first one.
        # response.content is a list of ContentBlock objects;
        # .text gets the string content.
        text = response.content[0].text.strip()

        print(f"    → {text}")

    print(f"\n  Final synthesis: {text}")
    return text


# Quick test when running directly
if __name__ == "__main__":
    # Import here to avoid circular imports at module level
    from scraper.text_scraper import scrape_text as scrape

    raw = scrape()
    if raw:
        result = synthesize_text(raw)
        print(f"\nResult: {result}")
