import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes_cache_engine.clipper import clip, estimate_tokens, fingerprint


class ClipTests(unittest.TestCase):
    def test_small_text_untouched(self):
        r = clip("short output", cap_tokens=100)
        self.assertFalse(r.changed)
        self.assertEqual(r.saved, 0)

    def test_large_text_is_clipped_and_keeps_edges(self):
        body = "HEAD" + ("x" * 30_000) + "TAIL"
        r = clip(body, cap_tokens=500, chars_per_token=3.0)
        self.assertTrue(r.changed)
        self.assertIn("HEAD", r.text)
        self.assertIn("TAIL", r.text)
        self.assertIn("omitted", r.text)
        self.assertLess(estimate_tokens(r.text), estimate_tokens(body))

    def test_saved_is_positive_and_bounded(self):
        body = "y" * 60_000
        r = clip(body, cap_tokens=1000)
        self.assertGreater(r.saved, 0)
        self.assertLessEqual(estimate_tokens(r.text), 1000 + 60)  # pointer line overhead

    def test_fingerprint_is_stable(self):
        self.assertEqual(fingerprint("abc"), fingerprint("abc"))
        self.assertNotEqual(fingerprint("abc"), fingerprint("abd"))

    def test_zero_cap_does_not_crash(self):
        r = clip("z" * 5000, cap_tokens=0)
        self.assertTrue(r.changed)


if __name__ == "__main__":
    unittest.main()
