"""
Configuration — loads API keys from environment variables.

Uses python-dotenv locally (reads .env file), but in production
(GitHub Actions) these come from GitHub Secrets.
"""

import os

# dotenv.load_dotenv() reads key=value pairs from a .env file
# and sets them as environment variables. No-ops if .env doesn't exist.
from dotenv import load_dotenv
load_dotenv()

# os.environ["KEY"] would crash if missing — os.getenv() returns None instead
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")

# __file__ is a built-in variable holding this file's path.
# os.path.dirname() gets the folder it lives in — the project root.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SEED_WORDS_FILE = os.path.join(BASE_DIR, "seeds", "words.txt")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_LOG = os.path.join(BASE_DIR, "output", "log.json")
VIDEO_OUTPUT_DIR = os.path.join(BASE_DIR, "output", "videos")
