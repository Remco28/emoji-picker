import unittest

from emoji_picker.data import load_emoji
from emoji_picker.search import Index, parse, positions, stem

DATA = load_emoji()


def chars(index, sections, n=None):
    out = [index.emoji[i]["e"] for s in sections for i in s.items]
    return out if n is None else out[:n]


class ParseTest(unittest.TestCase):
    def test_stopwords_dropped_and_partial_last_word(self):
        self.assertEqual(parse("the happy do"), (["happy", "do"], "do"))
        self.assertEqual(parse("the happy dogs "), (["happy", "dog"], None))
        self.assertEqual(parse("cats"), (["cat"], "cats"))

    def test_negation_drops_the_rest_of_its_clause(self):
        self.assertEqual(parse("it isn't looking good, please pray ")[0], ["please", "pray"])
        self.assertEqual(parse("not happy at all")[0], [])
        self.assertEqual(parse("not sad but happy ")[0], ["happy"])

    def test_lone_partial_stopword_is_browse(self):
        self.assertEqual(parse("do")[0], [])

    def test_stopword_only_is_empty(self):
        self.assertEqual(parse("so the")[0], [])

    def test_stem_plurals(self):
        self.assertEqual(stem("flags"), "flag")
        self.assertEqual(stem("puppies"), "puppy")
        self.assertEqual(stem("glass"), "glass")


class IndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = Index(DATA)

    def test_browse_view_for_empty_and_stopwords(self):
        self.assertIsNone(self.idx.sections(""))
        self.assertIsNone(self.idx.sections("the and"))

    def test_gibberish_has_no_results(self):
        self.assertEqual(self.idx.sections("qzxvq"), [])

    def test_single_word(self):
        self.assertIn("🔥", chars(self.idx, self.idx.sections("fire"), 3))

    def test_prefix_while_typing(self):
        self.assertIn("🍕", chars(self.idx, self.idx.sections("pizz"), 5))
        # a trailing space ends the word: no prefix matching
        self.assertEqual(self.idx.sections("pizz "), [])

    def test_shortcodes(self):
        self.assertEqual(chars(self.idx, self.idx.sections(":fire"), 1), ["🔥"])
        self.assertEqual(chars(self.idx, self.idx.sections(":thumbsup"), 1), ["👍"])
        self.assertEqual(self.idx.sections(":zzzznope"), [])

    def test_multi_concept_rows(self):
        secs = self.idx.sections("pizza beer")
        titles = [s.title for s in secs]
        self.assertIn("pizza", titles)
        self.assertIn("beer", titles)
        for s in secs:
            if s.kind == "concept":
                self.assertLessEqual(len(s.items), 14)

    def test_label_phrase_bonus(self):
        self.assertEqual(chars(self.idx, self.idx.sections("hot dog"), 1), ["🌭"])

    def test_no_duplicates_across_sections(self):
        items = [i for s in self.idx.sections("happy dog cat") for i in s.items]
        self.assertEqual(len(items), len(set(items)))

    def test_positions_start_each_section_on_a_new_line(self):
        from emoji_picker.search import Section
        pos = positions([Section("a", [1, 2, 3]), Section("b", [4])], columns=2)
        self.assertEqual(pos, [(0, 0, 1), (0, 1, 2), (1, 0, 3), (2, 0, 4)])

    def test_max_version_hides_newer(self):
        idx = Index(DATA, max_version=15)
        self.assertTrue(all(e["v"] <= 15 for e in idx.emoji))
        self.assertLess(len(idx.emoji), len(self.idx.emoji))

    def test_enrichment_terms_are_searchable(self):
        idx = Index(DATA, {"1F3E5": ["vet", "sick pet"]})  # hospital
        self.assertEqual(chars(idx, idx.sections("vet"), 1), ["🏥"])


if __name__ == "__main__":
    unittest.main()
