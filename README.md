# We Were Here, Briefly

Every day, a program scrapes the internet for traces of human activity — images, text, fragments nobody meant to leave behind. AI compresses them into a single surreal sentence. That sentence becomes a video. The videos datamosh together into one continuous loop. It runs automatically. Nobody curates it.

**Live:** [we-were-here-briefly.vercel.app](https://we-were-here-briefly.vercel.app)

---

## How it works

The pipeline runs daily via GitHub Actions. Each run follows the same sequence:

### 1. Seed word

A word is picked at random from a curated list of ~130 terms — mundane objects (`thermostat`, `receipt`, `hinge`), conceptual art references (`On Kawara`, `Felix Gonzalez-Torres`), and system language (`latency`, `entropy`, `protocol`). Both tracks use the same seed so they stay thematically linked.

### 2. Track A — Images

The image scraper searches Bing, Wikimedia Commons, and Flickr (in fallback order) for the seed word. It downloads up to 5 images to a temp directory, filtering out tracking pixels and sub-5KB files. These are sent to Claude Vision as base64-encoded content blocks in a single API call. The prompt asks Claude not to describe what it sees, but what each image *feels like as a faint human trace*.

### 3. Track B — Text

The text scraper fetches the Wikipedia article for the seed word, handling disambiguation pages by following the first linked article. Raw HTML is stripped to plaintext. This text is then run through a 3-pass "telephone game" via Claude — each pass compresses the previous output into something stranger. One of five compression styles is randomly selected per run: industrial/mechanical, body/biological, domestic/intimate, natural/geological, or childlike/naive.

### 4. Merge

The two tracks — image impressions and telephone-game sentence — are merged by Claude into a single composite video generation prompt. A weighted random style mode shapes the merge: representational (30%), liminal (25%), sensory/textural (20%), abstract (15%), or glitch/system (10%). The style mode changes the system prompt, not the content.

### 5. Video generation

The merged prompt is sent to Kling 1.6 via fal.ai, which generates a 5-second 16:9 video. The fal client handles job submission, queue polling, and result retrieval. The video is downloaded and uploaded to Cloudflare R2.

### 6. Datamosh

After each new video, datamosh.py pulls every video from Postgres (falling back to log.json), downloads them from R2, converts each to MPEG-2, concatenates them in shuffled order, then strips all I-frames after the first by directly manipulating the raw bytes. This forces the decoder to apply motion vectors from earlier clips across every subsequent frame — producing the characteristic smeared, bleeding effect. The result is re-encoded to H.264 and uploaded to R2 as `datamosh.mp4`, overwriting the previous version.

### 7. Frontend

The site is a single fullscreen `<video>` element that autoplays and loops the latest datamosh. No UI, no text, no controls. A password-gated admin page at `/admin.html` shows a grid of all individual runs with their seed words, generated sentences, and style modes.

---

## Pipeline architecture

```
seeds/words.txt
       |
  [random pick]
       |
   seed word ─────────────────────────┐
       |                              |
  TRACK A: images                TRACK B: text
       |                              |
  Bing/Wikimedia/Flickr          Wikipedia API
       |                              |
  Claude Vision                  3x Claude compression
  (image impressions)            (telephone game)
       |                              |
       └──────── merge ───────────────┘
                   |
           composite prompt
                   |
          Kling 1.6 via fal.ai
                   |
              5-second video
                   |
          upload to R2 + Postgres
                   |
              datamosh.py
          (I-frame stripping)
                   |
           datamosh.mp4 → R2
                   |
         Vercel frontend (loop)
```

---

## Running locally

### Prerequisites

- Python 3.11+
- Node.js (for the Vercel serverless function)
- ffmpeg (for datamosh)

### Setup

```bash
git clone https://github.com/ashaw315/we-were-here-briefly.git
cd we-were-here-briefly

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

- `ANTHROPIC_API_KEY` — Claude API access (scraping, synthesis, merge)
- `FAL_KEY` — fal.ai access (video generation)
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL` — Cloudflare R2 (video storage)
- `POSTGRES_URL` — Vercel Postgres (metadata)

### Run

```bash
# Full pipeline
python main.py

# Datamosh only (requires existing videos)
python datamosh.py

# Tests
python tests/run_tests.py
```

The pipeline degrades gracefully — if R2 or Postgres aren't configured, it falls back to local file storage and log.json.

---

## Tech stack

- **Python** — pipeline orchestration, scraping, AI calls, datamosh
- **Claude Sonnet 4** — image analysis (Vision), text compression (3-pass telephone game), track merging
- **Kling 1.6 via fal.ai** — text-to-video generation
- **ffmpeg** — MPEG-2 conversion for datamosh
- **Cloudflare R2** — video storage (S3-compatible, via boto3)
- **Vercel Postgres** — run metadata (psycopg2)
- **Vercel** — static frontend hosting + serverless API
- **GitHub Actions** — daily cron trigger, test gating

---

## Deployment

The site is deployed on Vercel with `framework: null` (static files from `public/`). The serverless function at `api/runs.js` connects to Vercel Postgres to serve run metadata.

The pipeline itself runs on GitHub Actions (`ubuntu-latest`) on a daily cron at midnight UTC. It installs Python dependencies and ffmpeg, runs tests, then executes the full pipeline. The bot commits `output/log.json` as a local backup after each run.

All secrets (API keys, R2 credentials, Postgres URL) are stored as GitHub Secrets and injected as environment variables.

---

## Project structure

```
main.py                  # Pipeline orchestrator
config.py                # Environment variable loader
datamosh.py              # I-frame stripping + video concatenation
scraper/
  text_scraper.py        # Wikipedia scraping + disambiguation handling
  image_scraper.py       # Bing/Wikimedia/Flickr image search + download
pipeline/
  text_synthesizer.py    # 3-pass Claude compression (telephone game)
  image_analyzer.py      # Claude Vision image impressions
  merger.py              # Weighted style mode merge
generator/
  video_gen.py           # Kling 1.6 via fal.ai
uploader/
  r2_upload.py           # Cloudflare R2 upload (boto3)
db/
  database.py            # Vercel Postgres (psycopg2)
api/
  runs.js                # Vercel serverless function
public/
  index.html             # Fullscreen video player
  admin.html             # Password-gated archive view
  app.js                 # Datamosh loader with API fallback
  style.css              # Fullscreen video styles
seeds/
  words.txt              # Seed word list
tests/
  run_tests.py           # Test runner
  test_pipeline.py       # Pipeline component tests
  test_datamosh.py       # Datamosh tests
  test_database.py       # Database tests
  test_r2_upload.py      # R2 upload tests
```
