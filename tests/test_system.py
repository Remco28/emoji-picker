import os
import tempfile
import unittest

from emoji_picker import system as s

INFO = {"us": ("eng", "en", "US, with emoji"), "de+nodeadkeys": ("deu", "de", "no dead keys, with emoji")}


def info(xid):
    return INFO.get(xid, ("other", xid[:3], "with emoji"))


class SourcesTest(unittest.TestCase):
    def test_one_layout_becomes_one_source(self):
        self.assertEqual(s.convert([("xkb", "us")]), [("ibus", "emoji-picker:us")])

    def test_order_and_other_engines_kept(self):
        src = [("xkb", "de+nodeadkeys"), ("ibus", "mozc-jp"), ("xkb", "us")]
        self.assertEqual(s.convert(src), [("ibus", "emoji-picker:de+nodeadkeys"),
                                          ("ibus", "mozc-jp"), ("ibus", "emoji-picker:us"),
                                          ("xkb", "de+nodeadkeys")])  # backup: not US

    def test_prototype_upgrade(self):
        self.assertEqual(s.convert([("ibus", "emoji-picker"), ("xkb", "us")]),
                         [("ibus", "emoji-picker:us")])

    def test_convert_is_idempotent(self):
        once = s.convert([("xkb", "us"), ("ibus", "mozc-jp")])
        self.assertEqual(s.convert(once), once)

    def test_restore_round_trip(self):
        for src in ([("xkb", "us")], [("xkb", "de+nodeadkeys"), ("ibus", "mozc-jp"), ("xkb", "us")]):
            self.assertEqual(s.restore(s.convert(src)), src)

    def test_restore_prototype_and_empty(self):
        self.assertEqual(s.restore([("ibus", "emoji-picker"), ("xkb", "us")]), [("xkb", "us")])
        self.assertEqual(s.restore([("ibus", "emoji-picker")]), [("xkb", "us")])
        self.assertEqual(s.restore([]), [])                   # nothing of ours: unchanged
        self.assertEqual(s.restore([("ibus", "mozc-jp")]), [("ibus", "mozc-jp")])

    def test_a_plain_layout_beside_ours_is_kept(self):
        # the user added the plain layout back themselves: leave it
        self.assertEqual(s.convert([("xkb", "us"), ("ibus", "emoji-picker:us")]),
                         [("xkb", "us"), ("ibus", "emoji-picker:us")])
        self.assertEqual(s.convert([("xkb", "us"), ("xkb", "us")]), [("ibus", "emoji-picker:us")])

    def test_gsettings_text_round_trip(self):
        text = "[('xkb', 'us'), ('ibus', 'mozc-jp')]"
        self.assertEqual(s.fmt_sources(s.parse(text)), text)
        self.assertEqual(s.parse("@a(ss) []"), [])
        self.assertEqual(s.fmt_sources([]), "@a(ss) []")

    def test_convert_only_engines_ibus_knows(self):
        src = [("ibus", "emoji-picker"), ("xkb", "us"), ("xkb", "de")]
        self.assertEqual(s.convert(src, known={"emoji-picker:us"}),
                         [("ibus", "emoji-picker:us"), ("xkb", "de")])
        # nothing known yet: the prototype engine stays, so typing still inserts
        self.assertEqual(s.convert(src, known=set()), src)

    def test_non_us_layout_keeps_a_plain_backup(self):
        once = s.convert([("xkb", "de")])
        self.assertEqual(once, [("ibus", "emoji-picker:de"), ("xkb", "de")])
        self.assertEqual(s.convert(once), once)                  # stable on re-install
        self.assertEqual(s.restore(once), [("xkb", "de")])
        self.assertEqual(s.convert([("xkb", "us+intl")]),         # US with dead keys is not 'us'
                         [("ibus", "emoji-picker:us+intl"), ("xkb", "us+intl")])
        self.assertEqual(s.convert([("xkb", "us"), ("xkb", "de")]),  # first is US: no backup
                         [("ibus", "emoji-picker:us"), ("ibus", "emoji-picker:de")])
        # a plain layout left unconverted already is a backup
        self.assertEqual(s.convert([("xkb", "de"), ("xkb", "fr")], known={"emoji-picker:de"}),
                         [("ibus", "emoji-picker:de"), ("xkb", "fr")])

    def test_prototype_engine_becomes_its_layout(self):
        self.assertEqual(s.convert([("ibus", "emoji-picker")], proto_id="de"),
                         [("ibus", "emoji-picker:de"), ("xkb", "de")])
        self.assertEqual(s.convert([("ibus", "emoji-picker"), ("xkb", "us")], proto_id="us"),
                         [("ibus", "emoji-picker:us")])
        xml = "<engine><name>emoji-picker</name><layout>us</layout></engine>"
        self.assertEqual(s.prototype_layout(xml), "us")
        self.assertIsNone(s.prototype_layout("<engine><name>emoji-picker:us</name></engine>"))

    def test_exact_engine_names_not_prefixes(self):
        listing = "  emoji-picker:de+nodeadkeys - x\n"
        self.assertEqual(s.convert([("xkb", "de")], known=s.listed_engines(listing)), [("xkb", "de")])

    def test_registry_union(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "1000"), "w") as f:
                f.write("us\nde+nodeadkeys\n")
            with open(os.path.join(d, "1001"), "w") as f:
                f.write("us\nfr(oss)\n../evil\n\n")
            self.assertEqual(s.registry_ids(d), ["us", "de+nodeadkeys", "fr(oss)"])
        self.assertEqual(s.registry_ids("/nonexistent"), [])

    def test_missing_engines(self):
        listing = "language: English\n  xkb:us::eng - English (US)\n  emoji-picker:us - US, with emoji\n"
        self.assertEqual(s.missing([("ibus", "emoji-picker:us")], listing), [])
        self.assertEqual(s.missing([("ibus", "emoji-picker:us"), ("ibus", "emoji-picker:de")], listing),
                         ["emoji-picker:de"])


class HotkeyTest(unittest.TestCase):
    def test_remove_only_ours(self):
        self.assertEqual(s.without(["<Super>period", "<Super>semicolon"], "<Super>period"),
                         ["<Super>semicolon"])

    def test_restore_keeps_user_changes(self):
        self.assertEqual(s.with_first(["<Super>semicolon", "<Alt>e"], "<Super>period"),
                         ["<Super>period", "<Super>semicolon", "<Alt>e"])
        self.assertEqual(s.with_first(["<Super>period"], "<Super>period"), ["<Super>period"])

    def test_string_list_format(self):
        self.assertEqual(s.fmt_strings([]), "@as []")
        self.assertEqual(s.parse(s.fmt_strings(["<Super>period"])), ["<Super>period"])


class ComponentTest(unittest.TestCase):
    def test_engines_names_and_variant(self):
        xml = s.component("/opt/x/engine.py", ["us", "de+nodeadkeys"], "1.0.0", info=info)
        self.assertIn("<name>emoji-picker:us</name>", xml)
        self.assertIn("<language>eng</language>", xml)
        self.assertIn("<symbol>en</symbol>", xml)
        self.assertIn("<layout_variant>nodeadkeys</layout_variant>", xml)
        self.assertEqual(xml.count("<layout_variant>"), 1)  # never an empty one
        self.assertIn("<exec>/opt/x/engine.py --ibus</exec>", xml)

    def test_escaping(self):
        xml = s.component("/a&b/engine.py", ["us"], "1.0.0", info=lambda x: ("eng", "en", "A<B"))
        self.assertIn("/a&amp;b/engine.py", xml)
        self.assertIn("A&lt;B", xml)


if __name__ == "__main__":
    unittest.main()
