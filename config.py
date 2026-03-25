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

# --- Cloudflare R2 (S3-compatible object storage for videos) ---
# R2 stores our video files so they don't bloat the git repo.
# boto3 connects using the S3 API with R2's custom endpoint.
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")  # e.g. https://pub-xxx.r2.dev

# --- Vercel Postgres (metadata database) ---
# Replaces log.json as the source of truth for run metadata.
# Vercel provides this connection string automatically when you
# link a Postgres database to your project.
POSTGRES_URL = os.getenv("POSTGRES_URL")

# __file__ is a built-in variable holding this file's path.
# os.path.dirname() gets the folder it lives in — the project root.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SEED_WORDS_FILE = os.path.join(BASE_DIR, "seeds", "words.txt")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_LOG = os.path.join(BASE_DIR, "output", "log.json")
VIDEO_OUTPUT_DIR = os.path.join(BASE_DIR, "output", "videos")
