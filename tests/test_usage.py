import json
import os
import tempfile
import unittest

from emoji_picker.usage import HALF_LIFE, Usage


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class UsageTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "usage.json")
        self.clock = Clock()

    def tearDown(self):
        self.dir.cleanup()

    def test_recent_and_frequent(self):
        u = Usage(self.path, self.clock)
        for h in ["A", "B", "A", "C"]:
            self.clock.t += 10
            u.record(h)
        self.assertEqual(u.recent(), ["C", "A", "B"])
        self.assertEqual(u.frequent()[0], "A")

    def test_frecency_halves_after_half_life(self):
        u = Usage(self.path, self.clock)
        u.record("A")
        self.clock.t += HALF_LIFE
        self.assertAlmostEqual(u.frecency("A"), 0.5)

    def test_round_trip(self):
        u = Usage(self.path, self.clock)
        u.record("A", tone=3)
        u.save()
        v = Usage(self.path, self.clock)
        self.assertEqual(v.recent(), ["A"])
        self.assertEqual(v.tone_for("A", {"single"}), 3)

    def test_corrupt_file_is_moved_aside(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        u = Usage(self.path, self.clock)
        self.assertEqual(u.recent(), [])
        self.assertTrue(any(n.startswith("usage.json.corrupt-") for n in os.listdir(self.dir.name)))

    def test_wrong_shape_counts_as_corrupt(self):
        with open(self.path, "w") as f:
            json.dump({"emoji": {"A": {"f": "x"}}}, f)
        self.assertEqual(Usage(self.path, self.clock).recent(), [])

    def test_tone_defaults(self):
        u = Usage(self.path, self.clock)
        self.assertIsNone(u.tone_for("B", {"single"}))
        u.set_tone("A", 4)
        self.assertEqual(u.tone_for("B", {"single"}), 4)  # learned default
        self.assertIsNone(u.tone_for("C", {"pair"}))      # pairs have their own default
        u.set_tone("D", [2, 5])
        self.assertEqual(u.tone_for("C", {"pair"}), [2, 5])
        u.set_tone("B", 1)
        self.assertEqual(u.tone_for("B", {"single"}), 1)  # per-emoji choice wins


if __name__ == "__main__":
    unittest.main()
