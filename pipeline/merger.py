"""
Merger — combines the image vibe and the text synthesis
into one surreal composite sentence.

This is where the two tracks meet. The telephone-game sentence
(from text) and the image impressions (from vision) get folded
together into a single prompt for video generation. The style
mode — randomly chosen each run — shapes HOW Claude combines
them, not WHAT goes in. The raw human material from both tracks
is always present.

Style spectrum (weighted random):
  REPRESENTATIONAL (30%) → concrete scene with people/objects/narrative
  LIMINAL (25%)          → in-between spaces, transitional moments
  SENSORY/TEXTURAL (20%) → pure material/surface/light description
  ABSTRACT (15%)         → form, color, movement, no recognizable objects
  GLITCH/SYSTEM (10%)    → corrupted data, transmission errors, system noise
"""

import random

from anthropic import Anthropic

import config

print("merger loaded")

# --- Style modes ---
# Each mode has a name (for logging), a weight (selection probability),
# and a system prompt that tells Claude HOW to merge the two tracks.
#
# The user prompt (which contains the actual track content) stays the
# same across all modes. Only the system prompt changes.
#
# random.choices() uses the weights to pick — higher weight = more likely.
# Weights don't need to sum to 100, but we use percentages for clarity.

STYLE_MODES = [
    {
        "name": "REPRESENTATIONAL",
        "weight": 30,
        "prompt": """You are the last thought before sleep. Given two
fragments of human residue, combine them into one surreal video
generation prompt describing a CONCRETE SCENE.

Rules:
- Include specific people, objects, and places
- Imply a narrative — something is happening or just happened
- Use details from BOTH inputs, rearranged into one scene
- Max 2 sentences
- No metaphors about dreams or the subconscious
- Avoid offices, filing cabinets, fluorescent lights, and bureaucratic
  settings unless they arrive completely naturally from the source
  material. Surprise yourself.""",
    },
    {
        "name": "LIMINAL",
        "weight": 25,
        "prompt": """You are the pause between two floors in an elevator.
Given two fragments of human residue, combine them into one surreal
video generation prompt describing a LIMINAL MOMENT.

Rules:
- Focus on in-between spaces: hallways, doorways, parking lots at dusk,
  empty waiting areas, the moment before arrival or after departure
- Things should be mid-motion, half-formed, transitional
- Describe a place that feels half-remembered — neither here nor there
- Use details from BOTH inputs, but place them in a space of passage
- No resolution. Nothing completes. The scene is permanently mid-transit.
- Max 2 sentences
- No metaphors about dreams. Stay spatial and physical.""",
    },
    {
        "name": "SENSORY/TEXTURAL",
        "weight": 20,
        "prompt": """You are a surface that remembers every hand that
touched it. Given two fragments of human residue, combine them into
one surreal video generation prompt describing PURE SENSATION.

Rules:
- Describe texture, light, material, surface, temperature, weight
- How things FEEL visually — rough, wet, translucent, granular, warm
- No characters. No narrative. No people visible.
- The human traces from both inputs become material properties —
  stains, wear patterns, warmth, indentations, residue
- Think: extreme close-up of a surface that tells a story through
  its physical state alone
- Max 2 sentences
- No metaphors about time or memory. Stay tactile.""",
    },
    {
        "name": "ABSTRACT",
        "weight": 15,
        "prompt": """You are a color that has forgotten what object it
belonged to. Given two fragments of human residue, combine them
into one surreal video generation prompt describing PURE FORM.

Rules:
- Describe only color, movement, rhythm, geometric behavior
- No recognizable objects, people, or places
- The human traces from both inputs should be FELT but not SEEN —
  translated into motion, repetition, interference patterns, gradients
- Think: what would this feel like as a slow animation of shapes
  and light, if all the nouns were removed
- Max 2 sentences
- No metaphors. Describe what is literally visible: colors moving.""",
    },
    {
        "name": "GLITCH/SYSTEM",
        "weight": 10,
        "prompt": """You are a video file that was corrupted during
transfer. Given two fragments of human residue, combine them into
one surreal video generation prompt describing a SYSTEM ERROR.

Rules:
- The human content from both inputs should be visible but BREAKING
  DOWN — partially rendered, mislabeled, duplicated, offset
- Include digital artifacts: pixel smear, color banding, frozen frames,
  text overlays from error messages, progress bars, loading states
- The scene looks like a normal image that is failing to display —
  recognizable elements dissolving into system noise
- Mix the visual language of software errors (dialogs, hex addresses,
  file extensions, buffer states) with the human content
- Max 2 sentences
- Make the corruption beautiful. Glitch as aesthetic.""",
    },
]


def pick_style():
    """
    Pick a weighted random style mode for this run.

    random.choices() returns a list (even for k=1), so we grab [0].
    The `weights` param makes some options more likely than others —
    like a weighted Math.random() in JS. Higher weight = higher
    probability of being selected.
    """
    # Extract the weight values into a separate list.
    # List comprehension: [mode["weight"] for mode in STYLE_MODES]
    # creates [30, 25, 20, 15, 10] — one weight per mode.
    weights = [mode["weight"] for mode in STYLE_MODES]

    # random.choices() with weights returns a weighted random selection.
    # k=1 means pick one item. Returns a list, so [0] gets the single result.
    style = random.choices(STYLE_MODES, weights=weights, k=1)[0]

    print(f"  Style mode: {style['name']}")
    return style


def merge(image_vibe, text_synthesis):
    """
    Combine the image impressions and text synthesis into
    a single composite prompt for video generation.

    Takes:
      - image_vibe: string of image impressions (from image_analyzer)
      - text_synthesis: the final telephone-game sentence (from text_synthesizer)

    The style mode (randomly chosen) changes the INSTRUCTIONS to Claude
    for how to combine them. The raw human material from both tracks
    is always present in the user prompt — style only shapes what
    Claude does with it.

    Returns a tuple of (composite_prompt, style_mode_name).
    The style_mode_name is a string like "ABSTRACT" or "LIMINAL"
    that gets stored in the database for the admin page.
    """
    # Handle cases where one or both tracks are empty.
    # If we only have one track, we can still produce something.
    if not image_vibe and not text_synthesis:
        print("  Nothing to merge — both tracks empty")
        return ("", None)

    if not config.ANTHROPIC_API_KEY:
        print("  No ANTHROPIC_API_KEY — skipping merge")
        # Return whatever we have as a fallback
        return (text_synthesis or image_vibe or "", None)

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Pick a random style mode — this determines the system prompt
    style = pick_style()

    # Build the user message with whatever tracks we have.
    # The user prompt is identical regardless of style mode —
    # it just presents the raw material. The system prompt (above)
    # is what changes the output character.
    parts = []
    if text_synthesis:
        parts.append(f"TEXT TRACK (telephone game result):\n{text_synthesis}")
    if image_vibe:
        parts.append(f"IMAGE TRACK (visual impressions):\n{image_vibe}")

    # "\n\n".join() concatenates list items with double newlines between them —
    # like parts.join("\n\n") in JS.
    user_msg = (
        "Combine these fragments into one surreal video generation prompt. "
        "Max 2 sentences.\n\n"
        + "\n\n".join(parts)
    )

    print("  Merging tracks via Claude...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        system=style["prompt"],
        messages=[
            {"role": "user", "content": user_msg}
        ],
    )

    result = response.content[0].text.strip()
    print(f"  Composite prompt: {result}")

    return (result, style["name"])


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

    # Run several times to see style variety
    for i in range(5):
        print(f"\n{'=' * 40}")
        result = merge(test_vibe, test_synthesis)
        print(f"Result: {result}")
