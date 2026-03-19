"""
Merger — combines the image vibe and the text synthesis
into one surreal composite sentence.

This is where the two tracks meet. The telephone-game sentence
(from text) and the image impressions (from vision) get folded
together into a single prompt for DALL-E. The result should feel
like something left running overnight — not a description,
but a residue.
"""

from anthropic import Anthropic

import config

print("merger loaded")

SYSTEM_PROMPT = """You are the last thought before sleep. Given two
fragments of human residue, combine them into one surreal image
generation prompt. It should feel like something left running
overnight. Max 2 sentences. No metaphors about dreams or the
subconscious. Stay concrete.

Avoid offices, filing cabinets, fluorescent lights, and bureaucratic
settings unless they arrive completely naturally from the source
material. Surprise yourself. Think: a photograph taken by a security
camera that became sentient for one frame."""


def merge(image_vibe, text_synthesis):
    """
    Combine the image impressions and text synthesis into
    a single composite prompt for image generation.

    Takes:
      - image_vibe: string of image impressions (from image_analyzer)
      - text_synthesis: the final telephone-game sentence (from text_synthesizer)

    Returns a composite prompt string (1-2 sentences).
    """
    # Handle cases where one or both tracks are empty.
    # If we only have one track, we can still produce something.
    if not image_vibe and not text_synthesis:
        print("  Nothing to merge — both tracks empty")
        return ""

    if not config.ANTHROPIC_API_KEY:
        print("  No ANTHROPIC_API_KEY — skipping merge")
        # Return whatever we have as a fallback
        return text_synthesis or image_vibe or ""

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Build the user message with whatever tracks we have.
    # f-strings with triple quotes let you write multi-line strings
    # with embedded variables — like JS template literals but with
    # Python's indentation rules.
    parts = []
    if text_synthesis:
        parts.append(f"TEXT TRACK (telephone game result):\n{text_synthesis}")
    if image_vibe:
        parts.append(f"IMAGE TRACK (visual impressions):\n{image_vibe}")

    # "\n\n".join() concatenates list items with double newlines between them —
    # like parts.join("\n\n") in JS.
    user_msg = (
        "Combine these fragments into one surreal image generation prompt. "
        "Max 2 sentences.\n\n"
        + "\n\n".join(parts)
    )

    print("  Merging tracks via Claude...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_msg}
        ],
    )

    result = response.content[0].text.strip()
    print(f"  Composite prompt: {result}")

    return result


# Quick test when running directly
if __name__ == "__main__":
    # Example inputs for testing
    test_vibe = (
        "A clipboard left on a folding chair in a room that smells "
        "like new carpet / The hum of a vending machine at 3am in a "
        "hospital corridor nobody visits"
    )
    test_synthesis = (
        "The thermostat in the condemned building was still set to "
        "72 degrees when they found the forwarding address taped "
        "to the inside of the elevator panel."
    )

    result = merge(test_vibe, test_synthesis)
    print(f"\nResult: {result}")
