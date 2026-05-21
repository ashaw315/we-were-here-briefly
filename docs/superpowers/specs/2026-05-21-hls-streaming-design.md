# HLS Streaming for datamosh video

**Date:** 2026-05-21
**Status:** Approved

## Problem

`datamosh.mp4` is ~268MB. Delivered as a single file via a plain
`<video src>`, playback is laggy — the browser must buffer a large
chunk before starting and re-buffers on seek/loop. Switch delivery to
HLS (HTTP Live Streaming): the mp4 is split into ~6s `.ts` chunks plus
an `.m3u8` playlist, and the browser streams chunks on demand. This is
the same approach YouTube/Vimeo use.

**The datamosh *generation* pipeline does not change. Only delivery does.**

## Architecture

```
datamosh pipeline (unchanged) ──▶ output/datamosh.mp4 ──▶ R2 (datamosh.mp4, kept for admin)
                                          │
                                          ▼
                                  convert_to_hls()
                                  ├─ ffmpeg → output/hls/{datamosh.m3u8, chunkNNN.ts}
                                  ├─ upload all to R2 under hls/ prefix
                                  ├─ update Postgres datamosh_url (all runs) → .m3u8
                                  └─ clean up output/hls/
                                          │
                                          ▼
                          R2: hls/datamosh.m3u8  +  hls/chunkNNN.ts
                                          │
                                          ▼
              app.js loadVideo(url) ── HLS.js (or native HLS in Safari)
```

## Part 1 — datamosh.py

### CORS comment
Top-of-file comment documenting the R2 CORS policy required for HLS
(browser fetches `.ts` chunks cross-origin). See Part 3.

### `convert_to_hls(input_path)`
1. Recreate `output/hls/` (clear stale contents).
2. Run ffmpeg (exact spec command):
   ```
   ffmpeg -i <input> -codec:v libx264 -crf 23 -preset fast \
     -codec:a aac -hls_time 6 -hls_playlist_type vod \
     -hls_segment_filename output/hls/chunk%03d.ts \
     -hls_flags independent_segments output/hls/datamosh.m3u8
   ```
3. Upload every file in `output/hls/` to R2 under `hls/`:
   - `datamosh.m3u8` → key `hls/datamosh.m3u8`, type `application/vnd.apple.mpegurl`
   - `chunkNNN.ts`   → key `hls/chunkNNN.ts`, type `video/mp2t`
   - Print `Uploading chunk X/Y...` progress.
4. Update Postgres `datamosh_url` for **all** runs → `{R2_PUBLIC_URL}/hls/datamosh.m3u8`.
5. Clean up `output/hls/`.
6. Return the playlist URL.

### main()
- Unchanged generation. Upload `datamosh.mp4` as today, **but do not
  delete it from R2** (kept for admin download per spec). The local
  file may still be removed after upload.
- After mp4 upload, call `convert_to_hls(DATAMOSH_OUTPUT)`.

### Standalone `--hls-only`
The local mp4 is deleted after each run, so it only lives on R2. The
one-off Part-4 conversion downloads the existing `datamosh.mp4` from R2
to a temp file and runs `convert_to_hls` on it — **no re-moshing**.
`python datamosh.py --hls-only`.

### r2_upload.py
- `upload_file_with_type(local_path, key, content_type)` — generic helper.
- `upload_hls_dir(local_dir)` — uploads playlist + chunks with correct
  types and progress, returns the playlist URL.

### database.py
- `update_all_datamosh_urls(url)` — single UPDATE across all rows.

## Part 2 — public/index.html + app.js

- `index.html`: add HLS.js CDN script before `app.js`:
  `https://cdnjs.cloudflare.com/ajax/libs/hls.js/1.4.12/hls.min.js`
- `app.js`: `loadVideo(url)`:
  - `.m3u8` + `Hls.isSupported()` → HLS.js with `startLevel:-1`,
    `maxBufferLength:30`, `maxMaxBufferLength:60`; play on
    `MANIFEST_PARSED`; loop via `ended` → `currentTime=0; play()`.
  - `.m3u8` + native (`canPlayType('application/vnd.apple.mpegurl')`) →
    set `src`, play (Safari).
  - else → plain mp4 `src`, play.
  - Fetch `/api/runs/latest`, pass `datamosh_url`; on failure fall back
    to `{R2_PUBLIC_URL}/hls/datamosh.m3u8`.
- Remove the `loop` attribute reliance on the HLS path; loop is handled
  by the `ended` listener (avoids double-fire).

## Part 3 — R2 CORS (manual, dashboard)

Cloudflare R2 dashboard → `we-were-here-briefly` → Settings → CORS Policy:
```json
[
  {
    "AllowedOrigins": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["Content-Length"],
    "MaxAgeSeconds": 3600
  }
]
```
Documented as a comment in datamosh.py. Must be set by the bucket owner.

## Part 4 — Run

`python datamosh.py --hls-only` → report chunk count, total chunk size,
playlist URL, upload confirmation.

## Deviations from literal spec (both approved improvements)
1. mp4 is **not** deleted from R2 (spec keeps it for admin download;
   current code deletes it).
2. `--hls-only` standalone path converts the existing R2 mp4 rather than
   re-moshing, matching "from the existing datamosh.mp4".
