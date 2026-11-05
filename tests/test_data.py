import unittest

from emoji_picker.data import load_emoji


class DataTest(unittest.TestCase):
    def test_shape(self):
        d = load_emoji()
        self.assertGreater(len(d["emoji"]), 1800)
        self.assertNotIn(2, {e["g"] for e in d["emoji"]})  # components dropped
        orders = [e["o"] for e in d["emoji"]]
        self.assertEqual(orders, sorted(orders))
        thumbs = next(e for e in d["emoji"] if e["h"] == "1F44D")
        self.assertIn("+1", thumbs["sc"] + thumbs["t"])
        self.assertEqual(len(thumbs["sk"]), 5)


if __name__ == "__main__":
    unittest.main()
