"""
Tests for Vercel Postgres database operations.

Tests that need a Postgres connection are skipped when POSTGRES_URL
is not configured. The missing-credentials test always runs to verify
graceful fallback.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from db.database import (
    init_db, insert_run, get_all_runs, get_latest_run,
    delete_run, _get_connection,
)


def postgres_configured():
    """Check if Postgres connection string is set."""
    return bool(config.POSTGRES_URL)


class TestDatabase(unittest.TestCase):

    @unittest.skipUnless(postgres_configured(), "POSTGRES_URL not configured")
    def test_postgres_connection(self):
        """
        Confirms POSTGRES_URL connects successfully.
        Opens a connection and runs a trivial query (SELECT 1).
        If the connection string is wrong, psycopg2 raises an error.
        """
        conn = _get_connection()
        self.assertIsNotNone(conn)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
            self.assertEqual(result[0], 1)
        finally:
            conn.close()

    @unittest.skipUnless(postgres_configured(), "POSTGRES_URL not configured")
    def test_init_db(self):
        """
        Confirms table creation is idempotent — calling init_db()
        twice should succeed both times without errors.
        CREATE TABLE IF NOT EXISTS handles the "already exists" case.
        """
        result1 = init_db()
        self.assertTrue(result1)

        # Second call should also succeed (IF NOT EXISTS)
        result2 = init_db()
        self.assertTrue(result2)

    @unittest.skipUnless(postgres_configured(), "POSTGRES_URL not configured")
    def test_insert_and_retrieve(self):
        """
        Full round-trip test: insert a dummy run, retrieve it,
        confirm all fields match, then delete it to clean up.
        This verifies INSERT, SELECT, and DELETE all work.
        """
        # Make sure table exists
        init_db()

        # Insert a test run with distinctive values
        test_data = {
            "date": "1999-12-31",
            "seed": "_test_seed_",
            "sentence": "This is a test sentence for automated testing.",
            "video_url": "https://example.com/test.mp4",
            "style_mode": "ABSTRACT",
        }

        run_id = insert_run(**test_data)
        self.assertIsNotNone(run_id, "insert_run should return an id")
        self.assertIsInstance(run_id, int)

        try:
            # Retrieve the latest run — should be our test run
            latest = get_latest_run()
            self.assertIsNotNone(latest)
            self.assertEqual(latest["seed"], "_test_seed_")
            self.assertEqual(latest["sentence"], test_data["sentence"])
            self.assertEqual(latest["video_url"], test_data["video_url"])
            self.assertEqual(latest["style_mode"], "ABSTRACT")

            # Also verify it appears in get_all_runs
            all_runs = get_all_runs()
            self.assertIsNotNone(all_runs)
            test_runs = [r for r in all_runs if r["seed"] == "_test_seed_"]
            self.assertEqual(len(test_runs), 1, "Should find exactly one test run")
        finally:
            # Always clean up the test data
            delete_run(run_id)

    def test_missing_credentials(self):
        """
        Confirms all database functions return None gracefully
        when POSTGRES_URL is not set. This is the normal state
        for local development without a database.
        """
        orig = config.POSTGRES_URL

        try:
            config.POSTGRES_URL = None

            # All functions should return None, not crash
            self.assertIsNone(init_db())
            self.assertIsNone(insert_run("2026-01-01", "test", "test", None, None))
            self.assertIsNone(get_all_runs())
            self.assertIsNone(get_latest_run())
        finally:
            config.POSTGRES_URL = orig


if __name__ == "__main__":
    unittest.main()
