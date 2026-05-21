# Replace datamosh with Kling O1 transition pipeline

**Date:** 2026-05-21
**Status:** Approved (design)

## Goal

Replace the datamosh delivery video with a seamless infinite loop built
from the real clips joined by AI-generated transitions. For each
chronological pair of runs, Kling O1 generates a 5s morph from the last
frame of clip A to the first frame of clip B. A loop-closing transition
joins the last run back to the first. The full sequence
`[clip_1, trans_1, clip_2, trans_2, ..., clip_N, trans_N(loop)]` is
concatenated, converted to HLS, and served at the existing
`hls/datamosh.m3u8` — so the frontend is unchanged.

## Key facts from codebase exploration

- DB currently has **54 runs**, all with `video_url` → **54 transitions**
  (53 consecutive + 1 loop-closing). The spec's "98" is stale; the count
  is computed dynamically.
- Original clips were made by **Kling 1.6**; transitions by **Kling O1**.
  Stream compatibility for `-c copy` is NOT guaranteed.
- Existing HLS plumbing: `r2_upload.upload_hls_dir(dir)` uploads a dir to
  the `hls/` prefix; playlist served as `hls/datamosh.m3u8`; `app.js`
  hardcodes that URL as fallback.
- `convert_to_hls` currently lives in `datamosh.py` (to be removed).

## Approved decisions

1. **HLS logic moves into `assembler/assemble.py`** (self-contained);
   `datamosh.py` → `datamosh.py.bak`. No import from a removed file.
2. **Playlist stays `hls/datamosh.m3u8`.** `app.js`/`index.html`
   unchanged; DB `datamosh_url` keeps pointing there. (Overrides Part 4's
   literal `final.m3u8`.)
3. **Concat: try `-c copy`, auto-fallback to re-encode** (normalize to
   1920×1080 h264 + aac) if copy fails or yields an invalid file.
4. **Autonomy: stop after `--limit 3` live test**; do not launch the full
   54-transition backfill without explicit go-ahead.
5. **Commit locally on `main` as logical units; do not push.** Generated
   transition videos / HLS artifacts stay out of git.

## Part 1 — db/database.py

- `init_db()`: add `ALTER TABLE runs ADD COLUMN IF NOT EXISTS
  transition_url TEXT;` after the CREATE TABLE.
- `update_transition_url(run_id, url)` — single-row UPDATE.
- `get_all_runs_ordered()` — `SELECT ... ORDER BY date ASC, id ASC`
  (chronological, stable). Returns list of dicts (same shape as
  `get_all_runs`, plus `transition_url`).
- `get_first_run()` — oldest (`ORDER BY date ASC, id ASC LIMIT 1`).
- `get_last_run()` — newest (`ORDER BY date DESC, id DESC LIMIT 1`).
- All existing SELECTs that enumerate columns also return
  `transition_url`.

## Part 2 — generator/transition_gen.py

`generate_transition(from_video_url, to_video_url, run_id, next_run_id,
seed_a=None, seed_b=None)`

(next_run_id is needed for the R2 key; passing it explicitly avoids a
second DB lookup. seeds are for progress output.)

1. Download both videos from R2 to a temp dir.
2. ffmpeg extract: last frame of `from` (`-sseof -0.1 ... -frames:v 1`),
   first frame of `to`.
3. `fal_client.upload_file()` both frames → URLs.
4. `fal_client.subscribe("fal-ai/kling-video/o1/image-to-video",
   arguments={start_image_url, end_image_url, duration:"5", prompt:
   "seamless morphing transition, one scene flowing continuously into
   another, dreamlike and fluid, no cut"})`.
   (Field names verified against fal docs — same fix as
   scripts/test_transitions.py.)
5. Download the result video (`result["video"]["url"]`).
6. Upload to R2 key `transitions/transition_{run_id}_to_{next_run_id}.mp4`
   (content type video/mp4), via `r2_upload.upload_file_with_type`.
7. Clean up temp files.
8. Return the R2 public URL.

Progress: `Generating transition: {seed_a} → {seed_b}` and
`Uploaded: {r2_url}`. Reads FAL_KEY from env like video_gen.py. Raises on
failure (callers decide whether to continue).

## Part 3 — scripts/backfill_transitions.py

- Read `get_all_runs_ordered()`.
- Print `Found X runs — generating X transitions (including loop-closing
  transition)`.
- For each consecutive pair (i → i+1):
  - Skip if `run_i.transition_url` already set (resumable).
  - `generate_transition(...)`, then `update_transition_url(run_i.id,url)`.
  - Print `Transition X/Y: {seed_a} → {seed_b}` then `... complete`.
  - `time.sleep(2)` between generations.
  - On error: log and continue (don't abort).
- Loop-closing: `generate_transition(last.video_url, first.video_url,
  last.id, first.id)`, update `last.transition_url`; print `Loop-closing
  transition complete`.
- Call `assemble_final_video()`.
- Summary: `X generated`, `X skipped`, `Final video rebuilt and uploaded`.
- `--dry-run`: list every transition (incl. loop) with seeds, no API/DB
  writes, no assembly.
- `--limit N`: only first N consecutive transitions; still runs assembly
  on what exists. (Loop-closing only runs when not limited / when reaching
  the end.)

## Part 4 — assembler/assemble.py

Self-contained (owns ffmpeg + HLS helpers; no datamosh import).

`assemble_final_video()`:
1. `get_all_runs_ordered()`.
2. Build sequence: for each run, `clip` then its `transition_url`
   (skip a missing transition with a warning rather than crash).
3. Download all videos to temp dir; print `Downloading clip X/Y...`.
4. Write concat list (`file '...'` lines, absolute paths).
5. Concat: `ffmpeg -f concat -safe 0 -i list.txt -c copy final.mp4`.
   **Validate** output with ffprobe; on failure OR invalid output,
   re-encode: `-c:v libx264 -preset fast -crf 20 -vf
   scale=1920:1080 -c:a aac` (normalize), concat via re-encode path.
6. HLS chunk `final.mp4` → `output/hls/` (playlist `datamosh.m3u8`),
   same ffmpeg HLS flags as before (`-hls_time 6 -hls_playlist_type vod
   -hls_flags independent_segments -crf 23 -preset fast`).
7. `upload_hls_dir(output/hls)` → R2 `hls/` (overwrites). Playlist URL
   `{R2_PUBLIC_URL}/hls/datamosh.m3u8`.
8. `update_all_datamosh_urls(playlist_url)` (existing helper) — all runs.
9. Clean up temp + `output/hls/`.
- Print clip/transition counts, total duration, chunk count, m3u8 URL.

## Part 5 — main.py

After the new run is uploaded + inserted (replacing the datamosh
subprocess stage):
1. **Generate transition** (previous → new): `get_all_runs_ordered()`,
   previous = second-to-last; `generate_transition(prev.video_url,
   new.video_url, prev.id, new.id)`; `update_transition_url(prev.id,url)`.
2. **Loop-closing** (new → first): `generate_transition(new.video_url,
   first.video_url, new.id, first.id)`;
   `update_transition_url(new.id, url)`.
3. **Assemble**: `assemble_final_video()`.
Each wrapped in `run_stage`. Remove datamosh import + subprocess stage.

## Part 6 — cleanup

- `datamosh.py` → `datamosh.py.bak`.
- `app.js` / `index.html` unchanged (already play `.m3u8`).
- `.gitignore`: add `output/test_transitions/` (and confirm
  `output/hls/`, `output/final.mp4`, transition temp dirs ignored).
- Commit `scripts/test_transitions.py`.

## Part 7 — test before backfill

1. `--dry-run` → confirm it lists **54** transitions incl. loop-closing.
2. `--limit 3` → 3 live generations; confirm R2 `transitions/` objects,
   `transition_url` set for those runs, and `assemble_final_video()`
   yields a valid HLS stream. Verify chunks fetch from R2.
3. Report; **stop** before full backfill.

## Risks

- `-c copy` incompatibility between Kling 1.6 clips and O1 transitions →
  handled by auto re-encode fallback (decision 3).
- Full backfill cost/time (~54 paid gens, 1.5-3 hrs) → gated behind
  explicit go-ahead (decision 4).
- fal field names → already verified in test_transitions.py.

## Deviations from literal spec (approved)
- 54 transitions, not 98 (actual DB state).
- Playlist `datamosh.m3u8`, not `final.m3u8` (keeps frontend unchanged).
- HLS logic in assembler, not imported from removed datamosh.py.
- `-c copy` with re-encode fallback, not copy-only.
