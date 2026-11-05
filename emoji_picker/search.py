"""Keyword search over emoji, with no model at runtime.

The window and tools/eval.py both call `Index.sections()`, so the eval scores
exactly what the window shows: an ordered list of sections, each starting on
a new line of the chart.

Query handling, in order:
- a query starting with ":" searches shortcodes only, by prefix;
- otherwise words are normalised (lowercase, accents stripped, light plural
  stemming), stopwords dropped, and a negation ("not", "never", "...n't")
  also drops the next content word;
- each remaining word is a concept; the last word also matches as a prefix
  while the user is still typing it (no trailing space).

Results:
- one concept: a single "Results" section ranked by match weight;
- several concepts: "Best matches" (emoji matching 2+ concepts, most
  concepts first, a bonus when a label or term appears as a phrase in the
  query), then one line per concept, most specific concept first, then
  "Related" (everything else that matched, a few lines at most).
"""
import bisect
import math
import re
import unicodedata
from dataclasses import dataclass, field

from .layout import COLUMNS

# Field weights. A starting point; tools/eval.py is what judges them.
W_LABEL = 10.0
W_LABEL_SHORT = 6.0  # extra, divided by the label's word count: "cat" beats "cat face"
W_SHORTCODE = 9.0       # the query word is a whole shortcode (":fire:")
W_SHORTCODE_WORD = 6.0  # ... or one word of a multi-word shortcode (":happy_birthday:")
W_TAG = 8.0           # the query word is a whole tag
W_TAG_WORD = 6.0      # ... or one word of a multi-word tag
W_ENRICH = 7.0        # the query word is a whole enriched term
W_ENRICH_WORD = 4.0   # ... or one word of a multi-word enriched term
W_GROUP = 2.0
PREFIX_FACTOR = 0.6
PHRASE_BONUS = 15.0   # a multi-word label/tag/term appears as-is in the query
EVIDENCE_STEP = 0.5   # bonus per extra label/tag/term containing the word ...
EVIDENCE_MAX = 1.0    # ... capped: a tie-breaker, never stronger than a better field
BEST_FIRST = 3        # all-words matches shown before each word's top pick
SENTENCE_WORDS = 4    # negation handling only applies to queries this long
USAGE_BONUS_MAX = 3.0
RELATED_LINES = 3

STOPWORDS = frozenset("""
not never without
a about above after again against all am an and any are aren't as at be because
been before being below between both but by can can't cannot could couldn't did
didn't do does doesn't doing don't during each few for from further had hadn't
has hasn't have haven't having he he'd he'll he's her here here's hers herself
him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its
itself just let's me more most mustn't my myself nor of once only or other ought
our ours ourselves own same shan't she she'd she'll she's should shouldn't so
some such than that that's the their theirs them themselves then there there's
these they they'd they'll they're they've this those through to too under until
very was wasn't we we'd we'll we're we've were weren't what what's when when's
where where's which while who who's whom why why's with won't would wouldn't you
you'd you'll you're you've your yours yourself yourselves also really
""".split())
NEGATIONS = frozenset({"not", "never", "without"})
CLAUSE_WORDS = frozenset({"but", "and", "so", "or", "then"})

_WORD = re.compile(r"[a-z0-9']+")
_TOKEN = re.compile(r"[a-z0-9']+|[,.;:!?]")


def fold(text):
    """Lowercase and strip accents; curly apostrophes become straight."""
    text = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    return "".join(c for c in text if not unicodedata.combining(c))


def stem(word):
    """Very light plural stemming, applied to index and query alike."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def words(text):
    return _WORD.findall(fold(text))


def is_negation(w):
    return w in NEGATIONS or w.endswith("n't")


def raw_stems(query):
    """All words of the query, stemmed, stopwords included (for phrases)."""
    return tuple(stem(w) for w in words(query))


def parse(query):
    """Return (concepts, partial). Concepts are stemmed words; `partial` is
    the raw last word while it is still being typed (for prefix matching),
    else None.

    In a sentence (4+ words) a negation drops every content word up to the
    end of its clause (a punctuation mark or "but", "and", "so", "or",
    "then"), so "isn't looking good, please pray" keeps only "please" and
    "pray"; in a short query ("can't wait") negations are plain stopwords.
    The last word, while still being typed (no trailing space), is kept as a
    prefix even if it is a stopword, when it follows exactly one other word
    ("happy do" on the way to "happy dog").
    """
    tokens = _TOKEN.findall(fold(query))
    typing = bool(query) and not query[-1].isspace() and bool(tokens) \
        and tokens[-1][0].isalnum()
    sentence = sum(1 for t in tokens if t[0].isalnum()) >= SENTENCE_WORDS
    concepts, negated, last_kept, last_raw = [], False, False, None
    for k, w in enumerate(tokens):
        last_kept = False
        if not w[0].isalnum() or w in CLAUSE_WORDS:
            negated = False
            continue
        if is_negation(w):
            negated = sentence  # short idioms ("can't wait") are left alone
            continue
        if negated:
            continue
        is_last = k == len(tokens) - 1
        if w in STOPWORDS and not (is_last and typing and 0 < len(concepts) < 2):
            continue
        concepts.append(stem(w))
        last_kept = True
        last_raw = w
    return concepts, (last_raw if typing and last_kept else None)


@dataclass
class Section:
    title: str
    items: list = field(default_factory=list)  # indexes into Index.emoji
    kind: str = "results"  # results | concept | related | browse | recent | frequent


class Index:
    """The searchable emoji list. With lazy=True the word index is built on
    the first search (or by calling build()), so a window can show the
    browse view first."""

    def __init__(self, data, enrichment=None, usage=None, max_version=None, lazy=False):
        self.groups = data["groups"]
        self.subgroups = data["subgroups"]
        self.emoji = [e for e in data["emoji"]
                      if max_version is None or e["v"] <= max_version]
        self.usage = usage
        self._enrichment = enrichment or {}
        self.built = False
        if not lazy:
            self.build()

    def build(self):
        if self.built:
            return False
        enrichment = self._enrichment
        self._evidence = {}  # stemmed word -> {emoji index: how many fields mention it}
        self.terms = {}      # stemmed word -> {emoji index: weight}
        self.phrases = []    # per emoji: list of stemmed word tuples (2+ words)
        self.shortcodes = []  # (shortcode, emoji index), sorted
        for i, e in enumerate(self.emoji):
            phrases = set()
            label = words(e["n"])
            self._add(label, i, W_LABEL + W_LABEL_SHORT / max(1, len(label)))
            if len(label) > 1:
                phrases.add(tuple(stem(w) for w in label))
            for code in e.get("sc", []):
                self.shortcodes.append((code.lower(), i))
                cw = words(code.replace("_", " "))
                self._add(cw, i, W_SHORTCODE if len(cw) == 1 else W_SHORTCODE_WORD)
            for tag in e.get("t", []):
                tw = words(tag)
                self._add(tw, i, W_TAG if len(tw) == 1 else W_TAG_WORD)
                if len(tw) > 1:
                    phrases.add(tuple(stem(w) for w in tw))
            for term in enrichment.get(e["h"], []):
                tw = words(term)
                self._add(tw, i, W_ENRICH if len(tw) == 1 else W_ENRICH_WORD)
                if len(tw) > 1:
                    phrases.add(tuple(stem(w) for w in tw))
            group_words = words(self.groups.get(str(e["g"]), "").replace("-", " ")) + \
                words(self.subgroups.get(str(e["sg"]), "").replace("-", " "))
            self._add(group_words, i, W_GROUP)
            self.phrases.append([p for p in phrases if len(p) > 1])
        self.shortcodes.sort()
        for key, ev in self._evidence.items():
            bucket = self.terms[key]
            for i, n in ev.items():
                bucket[i] += min(EVIDENCE_MAX, EVIDENCE_STEP * (n - 1))
        del self._evidence
        self.keys = sorted(self.terms)
        self.built = True
        return False  # usable as a GLib idle callback

    def _add(self, ws, i, weight):
        for w in ws:
            if w in STOPWORDS:
                continue
            key = stem(w)
            bucket = self.terms.setdefault(key, {})
            ev = self._evidence.setdefault(key, {})
            ev[i] = ev.get(i, 0) + 1
            if bucket.get(i, 0) < weight:
                bucket[i] = weight

    # ---- matching -------------------------------------------------------

    def _matches(self, concept, prefix=None):
        """{emoji index: weight} for one concept; `prefix` adds prefix matches."""
        hits = dict(self.terms.get(concept, {}))
        if prefix and len(prefix) >= 2:
            lo = bisect.bisect_left(self.keys, prefix)
            for key in self.keys[lo:]:
                if not key.startswith(prefix):
                    break
                if key == concept:
                    continue
                for i, w in self.terms[key].items():
                    pw = w * PREFIX_FACTOR
                    if hits.get(i, 0) < pw:
                        hits[i] = pw
        return hits

    def _usage_bonus(self, i):
        if not self.usage:
            return 0.0
        f = self.usage.frecency(self.emoji[i]["h"])
        return min(USAGE_BONUS_MAX, 1.5 * math.log2(1 + f)) if f > 0 else 0.0

    def _order(self, i):
        return self.emoji[i]["o"]

    # ---- sections --------------------------------------------------------

    def sections(self, query, columns=COLUMNS):
        q = query.strip()
        if q and not self.built:
            self.build()
        if q.startswith(":"):
            return self._shortcode_sections(q[1:].lower())
        concepts, partial = parse(query)
        if not concepts:
            return None  # browse view (empty or stopwords only)
        per = []
        for n, c in enumerate(concepts):
            per.append(self._matches(c, partial if n == len(concepts) - 1 else None))
        qraw = raw_stems(query)

        def phrase(i):
            return PHRASE_BONUS if any(_contains(qraw, p) for p in self.phrases[i]) else 0.0

        if len(concepts) == 1:
            hits = per[0]
            ranked = sorted(hits, key=lambda i: (-(hits[i] + phrase(i) + self._usage_bonus(i)),
                                                 self._order(i)))
            return [Section("Results", ranked)] if ranked else []

        candidates = set().union(*per)
        count, score = {}, {}
        for i in candidates:
            count[i] = sum(1 for h in per if i in h)
            score[i] = sum(h.get(i, 0) for h in per) + phrase(i) + self._usage_bonus(i)

        def row_order(hits):
            return sorted(hits, key=lambda i: (-(hits[i] + phrase(i) + self._usage_bonus(i)),
                                               self._order(i)))

        # most specific concept (fewest matches) first
        order = [n for n in sorted(range(len(concepts)), key=lambda n: (len(per[n]), n)) if per[n]]
        ranked_rows = {n: row_order(per[n]) for n in order}
        multi = sorted((i for i in candidates if count[i] >= 2),
                       key=lambda i: (-count[i], -score[i], self._order(i)))
        # The first line always shows each word's top pick, so a word whose
        # row would fall below the fold is still seen.
        picks = []
        for n in order:
            top = next((i for i in ranked_rows[n] if i not in picks), None)
            if top is not None:
                picks.append(top)
        # The first line: the strongest all-words matches, then each word's top
        # pick, then the remaining all-words matches.
        head = multi[:BEST_FIRST]
        best = head + [i for i in picks if i not in head] + \
            [i for i in multi[BEST_FIRST:] if i not in picks]
        out = [Section("Best matches", best)] if best else []
        shown = set(best)
        for n in order:
            row = [i for i in ranked_rows[n] if i not in shown][:columns]
            if row:
                out.append(Section(concepts[n], row, kind="concept"))
                shown.update(row)
        related = sorted((i for i in candidates if i not in shown),
                         key=lambda i: (-count[i], -score[i], self._order(i)))
        related = related[:columns * RELATED_LINES]
        if related:
            out.append(Section("Related", related, kind="related"))
        return out

    def _shortcode_sections(self, prefix):
        if not prefix:
            return []
        lo = bisect.bisect_left(self.shortcodes, (prefix, -1))
        exact, starts, seen = [], [], set()
        for code, i in self.shortcodes[lo:]:
            if not code.startswith(prefix):
                break
            if i in seen:
                continue
            seen.add(i)
            (exact if code == prefix else starts).append((len(code), self._order(i), i))
        ranked = [i for _, _, i in sorted(exact)] + [i for _, _, i in sorted(starts)]
        return [Section("Shortcodes", ranked)] if ranked else []


def _contains(seq, sub):
    n = len(sub)
    return any(seq[k:k + n] == sub for k in range(len(seq) - n + 1))


def positions(sections, columns=COLUMNS):
    """Display positions: [(line, column, emoji index)] in reading order."""
    out, line = [], 0
    for sec in sections or []:
        for k, i in enumerate(sec.items):
            out.append((line + k // columns, k % columns, i))
        if sec.items:
            line += (len(sec.items) + columns - 1) // columns
    return out
