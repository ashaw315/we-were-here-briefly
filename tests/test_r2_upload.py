"""
Tests for Cloudflare R2 video upload.

Tests that need R2 credentials are skipped when not configured.
The missing-credentials test always runs to verify graceful fallback.
"""

import os
import sys
import unittest

# Ensure project root is on the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from uploader.r2_upload import upload_video, upload_datamosh, delete_file, _get_client


def r2_configured():
    """Check if R2 credentials are set in the environment."""
    return all([config.R2_ACCOUNT_ID, config.R2_ACCESS_KEY_ID,
                config.R2_SECRET_ACCESS_KEY, config.R2_BUCKET_NAME,
                config.R2_PUBLIC_URL])


class TestR2Upload(unittest.TestCase):

    @unittest.skipUnless(r2_configured(), "R2 credentials not configured")
    def test_r2_connection(self):
        """
        Confirms R2 credentials are valid and the bucket is accessible.
        Calls list_objects with max 1 result — if credentials are wrong
        or the bucket doesn't exist, boto3 raises an exception.
        """
        client = _get_client()
        self.assertIsNotNone(client, "Client should be created when creds are set")

        # list_objects_v2 will throw if credentials are invalid
        # or the bucket doesn't exist. MaxKeys=1 keeps it fast.
        response = client.list_objects_v2(
            Bucket=config.R2_BUCKET_NAME,
            MaxKeys=1,
        )
        # S3 API returns 'Name' = bucket name in the response
        self.assertEqual(response["Name"], config.R2_BUCKET_NAME)

    @unittest.skipUnless(r2_configured(), "R2 credentials not configured")
    def test_upload_and_delete(self):
        """
        Uploads a tiny test file (1x1 pixel PNG), confirms it's publicly
        accessible via URL, then deletes it. This tests the full round-trip:
        upload → verify → cleanup.
        """
        import requests
        import tempfile

        # 1x1 pixel transparent PNG (67 bytes)
        # This is the smallest valid PNG file.
        png_bytes = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
            b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
            b'\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )

        # Write to a temp file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            temp_path = f.name

        try:
            # Upload with a unique test filename
            test_filename = "_test_upload_check.png"
            client = _get_client()
            client.upload_file(
                temp_path,
                config.R2_BUCKET_NAME,
                test_filename,
                ExtraArgs={"ContentType": "image/png"},
            )

            # Verify it's publicly accessible
            public_url = f"{config.R2_PUBLIC_URL}/{test_filename}"
            resp = requests.get(public_url, timeout=10)
            self.assertEqual(resp.status_code, 200,
                             f"Uploaded file should be accessible at {public_url}")

            # Clean up — delete from R2
            deleted = delete_file(test_filename)
            self.assertTrue(deleted)
        finally:
            # Always clean up the local temp file
            os.unlink(temp_path)

    def test_missing_credentials(self):
        """
        Confirms that upload functions return None gracefully when
        R2 credentials are not set. This is the normal state for
        local development without R2 configured.
        """
        # Save original values
        orig = {
            "R2_ACCOUNT_ID": config.R2_ACCOUNT_ID,
            "R2_ACCESS_KEY_ID": config.R2_ACCESS_KEY_ID,
            "R2_SECRET_ACCESS_KEY": config.R2_SECRET_ACCESS_KEY,
            "R2_BUCKET_NAME": config.R2_BUCKET_NAME,
        }

        try:
            # Clear all R2 config
            config.R2_ACCOUNT_ID = None
            config.R2_ACCESS_KEY_ID = None
            config.R2_SECRET_ACCESS_KEY = None
            config.R2_BUCKET_NAME = None

            # upload_video should return None, not crash
            result = upload_video("/nonexistent/file.mp4", "test.mp4")
            self.assertIsNone(result, "Should return None when R2 not configured")

            # upload_datamosh should also return None
            result = upload_datamosh("/nonexistent/file.mp4")
            self.assertIsNone(result, "Should return None when R2 not configured")
        finally:
            # Restore original values
            for key, val in orig.items():
                setattr(config, key, val)


if __name__ == "__main__":
    unittest.main()
