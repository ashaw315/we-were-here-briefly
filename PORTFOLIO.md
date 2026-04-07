TITLE: We Were Here, Briefly

TAGLINE: An automated system that scrapes human traces from the internet daily, compresses them through AI into surreal sentences, and renders them as a continuously datamoshing video loop that nobody curates.

DESCRIPTION:

Every day, a program searches the internet for evidence that people were here — a Wikipedia article about hinges, a photograph of a receipt on Flickr, a Wikimedia image of a parking lot. It collects these fragments and processes them through two parallel tracks: images are sent to Claude Vision, which describes not what it sees but what each image feels like as a residue of human presence; text is scraped from Wikipedia and run through a three-pass "telephone game" where Claude compresses it into something stranger with each round, like a fact half-remembered and then forgotten. The two tracks merge into a single surreal sentence. That sentence becomes a 5-second video. The videos accumulate.

Every time a new video is generated, all existing videos are concatenated and datamoshed — I-frames are stripped from the raw MPEG-2 bytes, forcing the decoder to smear motion vectors across clip boundaries. The result is a single looping video where figures bleed into landscapes into text into nothing. The site plays this loop fullscreen, with no interface. It updates itself. The pile grows. The artifacts compound.

The project exists at the intersection of conceptual art practice and automated systems. The pipeline makes every aesthetic decision — which word to start from, which compression style to apply, how to merge the tracks, which visual mode to render in. The human role is authorship of the system, not curation of its output.

TECHNICAL NOTE:

The pipeline is a seven-stage Python system orchestrated by a single entry point and triggered daily by GitHub Actions cron. A seed word is selected at random from a curated list that mixes mundane objects, art-world references, and systems language. Two parallel tracks process this word: the image track scrapes Bing, Wikimedia Commons, and Flickr with cascading fallback, downloads images to a temp directory, and sends them to Claude Vision as base64 content blocks in a single multimodal API call. The text track fetches Wikipedia (with disambiguation page detection and link-following), strips the HTML, and runs the plaintext through three sequential Claude calls, each compressing the previous output through a randomly selected stylistic lens — five modes ranging from industrial/mechanical to childlike/naive.

The merge stage combines both tracks through a weighted random style system — five modes (representational, liminal, sensory/textural, abstract, glitch/system) with probability weights that bias toward figurative output while keeping abstract and corrupted results possible. The composite prompt is sent to Kling 1.6 via fal.ai for video generation. R2 filename collision is handled by checking for existing keys before upload, appending suffixes when the pipeline runs multiple times per day.

The datamosh stage is the most architecturally specific: all accumulated videos are downloaded from R2, converted to MPEG-2 with a high GOP length (`-g 1000`), concatenated in shuffled order, then processed at the byte level — the code locates MPEG-2 picture start codes (`0x00 0x00 0x01 0x00`), identifies I-frames by reading the picture coding type bits at offset+5, and rewrites them as P-frames. This is not a filter or an approximation. The decoder receives corrupted data and does what decoders do with corrupted data.

The system degrades gracefully at every boundary — R2, Postgres, and all API keys can be absent without crashing the pipeline. Metadata is stored in Vercel Postgres with log.json as a local backup. The frontend is a single `<video>` element with no UI.

STACK: Python, Claude Sonnet 4 (Vision + text), Kling 1.6, fal.ai, ffmpeg, Cloudflare R2, Vercel, Vercel Postgres, GitHub Actions, boto3, BeautifulSoup, psycopg2

LIVE URL: https://we-were-here-briefly.vercel.app

GITHUB URL: https://github.com/ashaw315/we-were-here-briefly

SECTION: lab
