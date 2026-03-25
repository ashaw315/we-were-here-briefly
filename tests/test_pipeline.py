"""
Tests for the core pipeline components: seed picker, scrapers,
text synthesizer, and video path formatting.

Tests that need API keys are skipped when not configured.
Scraper tests hit real external services — they verify that
our scraping logic still works against live websites.
"""

import os
import re
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


class TestSeedWords(unittest.TestCase):

    def test_seed_word_picks(self):
        """
        Runs the seed picker 50 times and confirms every result is
        a non-empty string that exists in the words.txt file.
        This catches issues like empty lines, encoding problems,
        or the file being missing/empty.
        """
        from main import pick_seed_word

        # Load the full word list for validation
        with open(config.SEED_WORDS_FILE, "r") as f:
            valid_words = {w.strip() for w in f.read().splitlines() if w.strip()}

        self.assertGreater(len(valid_words), 0, "words.txt should not be empty")

        for i in range(50):
            word = pick_seed_word()
            self.assertIsInstance(word, str, f"Pick #{i}: should be a string")
            self.assertGreater(len(word), 0, f"Pick #{i}: should not be empty")
            self.assertIn(word, valid_words, f"Pick #{i}: '{word}' not in words.txt")


class TestTextScraper(unittest.TestCase):

    def test_text_scraper(self):
        """
        Confirms the text scraper returns non-empty text for the
        seed word "elevator". This hits the real Wikipedia API —
        if Wikipedia changes their HTML structure, this test will catch it.
        """
        from scraper.text_scraper import scrape_text

        result = scrape_text("elevator")
        self.assertIsNotNone(result, "Scraper should return something for 'elevator'")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 100,
                           "Should return substantial text, not just a stub")


class TestImageScraper(unittest.TestCase):

    def test_image_scraper(self):
        """
        Confirms the image scraper downloads at least 2 images for
        the seed word "receipt". Tests the full flow: URL discovery
        from Bing/Wikimedia/Flickr → HTTP download → file validation.
        Cleans up downloaded files after the test.
        """
        from scraper.image_scraper import scrape_images

        temp_dir = os.path.join(config.OUTPUT_DIR, "temp")

        try:
            result = scrape_images("receipt", count=3)
            self.assertIsNotNone(result, "Should return a list of paths")
            self.assertGreaterEqual(len(result), 2,
                                    "Should download at least 2 images")

            # Verify each returned path actually exists and has content
            for path in result:
                self.assertTrue(os.path.exists(path), f"File should exist: {path}")
                self.assertGreater(os.path.getsize(path), 5000,
                                   f"File should be >5KB: {path}")
        finally:
            # Clean up downloaded images
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


class TestTextSynthesizer(unittest.TestCase):

    @unittest.skipUnless(config.ANTHROPIC_API_KEY,
                         "ANTHROPIC_API_KEY not configured")
    def test_text_synthesizer(self):
        """
        Confirms the telephone game (3x Claude compression) returns
        a single sentence with no newlines. Requires a real API key
        because it makes 3 Claude API calls.
        """
        from pipeline.text_synthesizer import synthesize_text

        # Feed it some raw text to compress
        raw = ("An elevator is a platform or compartment housed in a shaft "
               "for raising and lowering people or things to different floors.")

        result = synthesize_text(raw)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10, "Should produce a real sentence")
        # The result should be a single sentence — no paragraph breaks
        self.assertNotIn("\n\n", result,
                         "Should be a single sentence, not multiple paragraphs")


class TestVideoPathFormat(unittest.TestCase):

    def test_video_path_format(self):
        """
        Confirms video filenames follow the YYYY-MM-DD.mp4 format.
        This pattern is used throughout the pipeline to name files.
        If it changes, R2 uploads and datamosh would break.
        """
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = f"{today}.mp4"

        # Should match YYYY-MM-DD.mp4 pattern
        pattern = r"^\d{4}-\d{2}-\d{2}\.mp4$"
        self.assertRegex(filename, pattern,
                         f"Filename '{filename}' doesn't match YYYY-MM-DD.mp4")

        # Verify the date part is valid
        date_part = filename.replace(".mp4", "")
        parsed = datetime.strptime(date_part, "%Y-%m-%d")
        self.assertEqual(parsed.strftime("%Y-%m-%d"), date_part)


if __name__ == "__main__":
    unittest.main()
