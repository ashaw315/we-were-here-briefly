"""
Tests for the datamosh pipeline.

Verifies ffmpeg is available and that any R2 video URLs
referenced in the database/log.json are actually accessible.
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


class TestDatamosh(unittest.TestCase):

    def test_ffmpeg_available(self):
        """
        Confirms ffmpeg is installed and callable. The datamosh
        pipeline depends entirely on ffmpeg for video conversion.
        If this fails on CI, add ffmpeg to the GitHub Actions setup.
        """
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0,
                         "ffmpeg should be installed and return exit code 0")
        # Verify the output mentions ffmpeg (not some alias)
        self.assertIn("ffmpeg", result.stdout.lower(),
                       "Output should mention ffmpeg")

    def test_r2_urls_accessible(self):
        """
        For each video URL in the database (or log.json), confirms
        the URL returns HTTP 200. This catches stale/deleted R2 files
        before the datamosh pipeline tries to download them.

        Skips if no remote URLs are found (local-only setup).
        """
        import requests

        urls = []

        # Try Postgres first
        try:
            from db.database import get_all_runs
            runs = get_all_runs()
            if runs:
                urls = [r["video_url"] for r in runs
                        if r.get("video_url") and r["video_url"].startswith("http")]
        except Exception:
            pass

        # Fall back to log.json
        if not urls:
            log_path = os.path.join(config.OUTPUT_DIR, "log.json")
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    log = json.load(f)
                urls = [e.get("video_url") or e.get("video", "")
                        for e in log
                        if (e.get("video_url", "") or "").startswith("http")]

        if not urls:
            self.skipTest("No remote video URLs found — local-only setup")

        for url in urls:
            # HEAD request is faster than GET — only checks if the file exists
            resp = requests.head(url, timeout=10, allow_redirects=True)
            self.assertEqual(resp.status_code, 200,
                             f"Video URL should be accessible: {url}")


if __name__ == "__main__":
    unittest.main()
