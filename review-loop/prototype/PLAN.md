# Plan v2: emoji-picker prototype with build-time keyword enrichment

Version 2, after the first peer pass (findings and what changed: `LEDGER.md`).
Frozen for review. The problem, Frank's decisions and the established facts are
in `PROBLEM.md` beside this file; this plan does not repeat them.

Success question: **Can Frank press a shortcut, type a few words or a
sentence, see the emoji he means near the top of a big keyboard-navigable
chart, press Enter, and have it appear in the app he was typing in, with
nothing left behind?**

## 1. Scope

In: the picker window, search (keywords, prefixes, phrases, shortcodes),
build-time enrichment and its evaluation, recents and
frequency, skin-tone variants, insertion through the passive IBus engine with
a clipboard fallback, install/uninstall scripts, tests.

Out (later): replacing Super+., a .deb package, languages other than English,
other keyboard layouts beyond what the installer copies, settings UI,
"insert several then close", typo tolerance, a resident background
process (only if a fresh process per press proves too slow), portal paste (it fails in terminals and
overwrites the clipboard; copy-only is the fallback instead).

## 2. Shape of the code

```
emoji_picker/            Python package (stdlib + PyGObject only)
  __main__.py            entry point, Adw.Application
  window.py              GTK window, sections, key handling glue
  search.py              index and query (no GTK)        <- unit tested
  usage.py               recents, frequency, tone memory (no GTK) <- unit tested
  nav.py                 grid keyboard-navigation model (no GTK) <- unit tested
  insert.py              engine client + clipboard fallback
  fonts.py               which emoji the installed font can draw
  data/emoji.json        built emoji data (committed)
  data/enrich-en.json    build-time enrichment (committed)
engine/engine.py         passive IBus engine (from the probe, extended)
engine/emoji-picker.xml.in
tools/build_data.py      emojibase tarball (pinned version + sha256) -> data/emoji.json (done)
tools/enrich.py          batches -> LLM -> validated keywords -> data/enrich-en.json
tools/eval.py            scores search against the frozen query set
tests/                   unittest (no pytest dependency)
tests/eval_queries.json  frozen before enrichment runs
install.sh, uninstall.sh
```

The probe folder stays as it is.

## 3. Data

`tools/build_data.py` downloads `emojibase-data` 18.0.0 from the npm registry,
checks its sha256, and writes `data/emoji.json`: per emoji its character,
hexcode, label, tags, group, subgroup, order, Unicode version, shortcodes
(github + cldr + emojibase, deduplicated) and skin variants (character +
tone or tone pair). The "component" group (bare skin-tone swatches, hair
pieces) is dropped. License notices for emojibase (MIT) and CLDR (Unicode
license) are added to the repo.

**Font coverage.** Emoji newer than the installed Noto Color Emoji font
would draw as empty boxes. At startup `fonts.py` reads the font's character
set (`fc-query`/`fc-match` output, single code points), finds the newest emoji
version all of whose single-code-point emoji are present, and hides emoji
newer than that. Cached per font file mtime. This is needed: the data has
25 emoji of versions 16-18 and the development machine's Noto (2.047) stops
at 15.1. Noto ships every standard (RGI) sequence of each version it
supports, so a version cutoff also covers ZWJ sequences and flags.

## 4. Enrichment (tested first, as Frank asked)

### 4a. The answer key comes before the keywords

`tests/eval_queries.json` is written and committed **before** any enrichment
is generated, so the keywords cannot be fitted to it, and no model that
generates keywords ever reads it. Each entry: the query, one or more groups
of acceptable emoji, and optional **decoys** that must rank below the first
acceptable emoji of every group. A query passes when every group has a
member in the top N (N = 5 for one concept, 10 for multi-concept queries,
12 for sentences) and no decoy outranks it. Three sources, kept separate in
the file:

1. **Frank's stories**: "american flag happy" (needs 🇺🇸, and one of the
   happy faces; decoys 🇦🇸 and 🏈) and the vet sentence (needs a dog, one of
   🏥 🩺 🚑, and 🙏).
2. **Persona queries** from the earlier simulated users: "skull", "party",
   "clap", "happy dog", "star", "check", "cake", "birthday", "tired but
   glad", "well done", "puppy", "praise", "tent fire", and others, about 40.
3. **A held-out set written by a different vendor's model** (Codex,
   gpt-6-luna), asked blind for 60 things people type into an emoji search
   box and the emoji they would expect. I review it only for impossible
   expectations (an emoji that does not exist), not for difficulty. This set
   is never shown to the enrichment model and is the main number.

Plus 20 **noise queries**, with rules a script checks: a query made only
of stopwords ("the", "ok so") shows the browse view, not results; gibberish
("asdfgh", "qzxv") returns no results; and across the noise queries no
emoji appears in more than 3 of the top-5 lists (no "default answer").

A fourth source comes later and is not scored here: Frank's own queries in
his test round.

### 4b. Generating keywords

`tools/enrich.py` sends the emoji in batches of about 60 (label, existing
tags, group) to `claude -p` with Sonnet 5.5, from an empty scratch directory
so no project instructions are loaded, and asks for each emoji 10-25 extra
search terms of 1-3 words that people would actually type: synonyms,
situations ("vet" for 🏥), feelings, slang, demonyms and nicknames for
flags ("american", "usa", "uk", "aussie"), common activities and
occasions. Not wanted: words that fit hundreds of emoji ("emoji", "symbol",
"thing"), offensive associations, or the label repeated.

Every answer is validated: JSON only, keys must be the batch's hexcodes,
terms lowercased, 1-3 words of letters, digits, apostrophes or hyphens,
deduplicated against existing tags, capped at 25. A batch that fails is
retried once and then reported, never silently skipped. Output records
model, prompt hash and date. Batches are cached on disk so a rerun only
fills gaps.

A post-check flags terms attached to more than 40 emoji (too generic) for
removal, and prints a sample of 30 random emoji with their new terms for me
to read.

### 4c. Scoring

`tools/eval.py` runs every query against (a) baseline: labels + tags +
shortcodes, and (b) baseline + enrichment, and reports per source: pass
rate, hit@1, mean reciprocal rank of the first acceptable emoji, the rank
change per query (better / same / worse), the queries that regress, the
noise rules, and search time.

**Relevance, judged blind by another vendor.** Presence in the top N does
not show whether the rest of the list is junk. For 30 queries sampled from
the held-out set, a Gemini reader (agy, read-only) gets the two top-10 lists
unlabelled, in random order (each query judged in both orders), and says
which list is more useful and how many of its 10 are relevant. Neither
Claude nor the keyword generator judges.

Targets: held-out pass rate >= 85% enriched; enriched beats baseline on
pass rate, hit@1 and MRR for every source; no more than 2 queries that the
baseline passed now fail; both of Frank's stories pass; all noise rules
hold; the blind judge prefers enriched on at least two thirds of the
sampled queries. If targets are missed I change the prompt or the ranking
(never the answer key) and rerun; each run's numbers go in the ledger.

## 5. Search

Pure Python, no model. Built once at startup into dictionaries.

- **Normalise**: lowercase, strip accents, split into words; English
  stopwords removed (so sentences work), except when the whole query is
  stopwords.
- **Index fields and weights**: label words and the full label phrase (10),
  shortcodes (9), CLDR tags (7), enriched terms including multi-word ones
  (5), group/subgroup names (2).
- **Concepts**: the query is split greedily into the longest known phrases
  of up to 3 words ("american flag", "thumbs up"); the rest are one-word
  concepts. The last word is also matched as a **prefix** while typing (no
  trailing space), so results narrow on every keystroke.
- **Shortcodes**: a query starting with `:` matches shortcodes only, by
  prefix (`:fir` finds 🔥).
- **Ranking**: emoji that match **all** concepts come first ("Best
  matches"). If there is more than one concept, each concept then gets its
  own row of at most two lines ("american flag", "happy"), so "american
  flag happy" shows 🇺🇸 and happy faces even though no single emoji is both,
  and a long sentence cannot be swamped by one word. Personal use adds
  a capped bonus (frequency with a 14-day half-life). Ties go to emojibase
  order.
- **Speed target**: under 5 ms per keystroke for search on this machine.

## 6. The window

- A **new process per shortcut press**, as in the probe, which is measured
  to open and take focus on Frank's Wayland session. It exits after
  inserting or on Esc. Cold start (Python, GTK, data, index, window) is
  measured under Xvfb; target under 400 ms. A resident process is a later
  optimisation, only if this is too slow, because showing an existing window
  on Wayland without an activation token is unmeasured.
- The search box uses GTK's simple input method (`im-module` set to
  `gtk-im-context-simple`), so IBus never sees the picker: a commit cannot
  land in the search box, and the engine's focus events come only from real
  apps and IBus's fake context.
- Default size about 760 x 560, resizable, size remembered. Ctrl+plus /
  Ctrl+minus change the emoji size (remembered).
- Top: a large search box, always focused. Below, a scrolled chart of
  sections. Empty query: **Recent** (last 16), **Frequent** (top 24), then
  every category in emojibase order. With a query: **Best matches**, then a
  row per concept, then **Related** (prefix matches).
- Bottom bar: the highlighted emoji's name and shortcode, and the keys:
  "Enter insert · Tab skin tones · Esc close".
- Sections are FlowBoxes with a fixed column count computed from the width.
  The browse view's first screen is built before the window shows and the
  rest in idle time; result sections (at most ~150 emoji) are rebuilt per
  keystroke. Target: under 50 ms from keystroke to redrawn results on this
  machine. (GridView would virtualise, but has no section headers in
  GTK 4.14.)

**Keys** (search box keeps focus throughout):

| Key | Does |
|---|---|
| typing | narrows results; the first result is highlighted |
| arrows | move the highlight through the chart, across sections |
| Page Up / Down | move by a screen |
| Enter | insert the highlighted emoji (with its remembered tone) and close |
| Tab | open the tone/variant strip for the highlighted emoji; arrows + Enter pick and insert; Tab or Esc returns |
| Esc | clear the search; if already empty, close |
| mouse | hover highlights, click inserts, right-click opens variants |

Left/Right always move the highlight, not the text cursor; Home/End/
Backspace still edit the search text.

**Variants**: choosing a tone for an emoji remembers it for that emoji. The
most recent tone chosen also becomes the default for tone-capable emoji you
have never set, so picking your tone once covers the rest. Two-person emoji
offer all tone pairs.

## 7. Insertion

The engine counts focus_in events (a **generation**) and reports, on
request, the generation, the time of the last focus change, and whether it
is the active engine.

1. On Enter, the picker reads the generation (call it g0) and hides.
   While the picker was showing, the previous app had lost focus and IBus
   had moved the engine to its fake context; the picker's own search box is
   invisible to IBus (section 6).
2. It then polls every 25 ms and commits only when **all** hold:
   at least **150 ms** since hiding (the delay measured to work on Frank's
   machine; the plan never commits sooner), the generation is **above g0**
   (a real app took focus after the picker hid), and **no focus change for
   the last 30 ms**.
3. If the engine is unreachable, is not the active engine, or the
   conditions are not met within 2 s, the emoji is copied to the clipboard
   and a notification says: "Could not insert. Copied: press Ctrl+V
   (Ctrl+Shift+V in a terminal)". This is a **degraded mode, counted as a
   failure**, never as success. (The probe showed the clipboard keeps the
   text after the process exits.)

An app with no input-method support never raises the generation, so it
falls back to the clipboard rather than committing into nothing.

The engine logs every focus change, capability and cursor-location event
with timestamps. These are diagnostics only; no decision depends on cursor
locations (the earlier belief that the fake context sends none was not
established).

## 8. Install and uninstall

`install.sh` (asks for sudo once):

1. Backs up input sources and the custom-shortcut list (first run only).
2. Writes the engine component to `/usr/share/ibus/component/` with the
   repo path, and the keyboard layout copied from the user's first xkb input
   source (Frank: `us`); runs `ibus write-cache`.
3. Adds the engine as the **first** input source, keeping the others after
   it (Super+Space switches back).
4. Adds a custom shortcut **Ctrl+Alt+E** running the picker, warning if
   that binding is already taken.
5. Does **not** run `ibus restart` (it broke Super+. last time). If
   `ibus list-engine` already lists the engine, it selects it with
   `ibus engine`; otherwise it asks for one logout.

`uninstall.sh` removes **only its own entries** (the engine from the input
sources, its shortcut from the list, its files; sudo for the component),
keeping any changes the user made after installing. The backups are kept
for manual recovery, not restored wholesale. It also asks for a logout if
the engine is still the current source.

## 9. How it will be checked

On the development machine:

- Unit tests (stdlib unittest): search parsing and ranking, shortcodes,
  prefix matching, usage store (including a corrupt file), grid
  navigation, variant memory, data build validation.
- `tools/eval.py` numbers, baseline vs enriched, in the ledger.
- Headless engine test (private ibus-daemon, as in the probe): the
  picker's insert routine against a scripted focus sequence (target out ->
  fake in -> target in), checking the text reaches the target context, not
  the fake one, and that with no target focus it falls back. This is a
  regression test of the logic; it does not prove Wayland timing.
- The real window under Xvfb: start it, type queries through a debug
  option, save screenshots, measure cold start, keystroke-to-redraw time
  and memory.

Not checkable here and handed to Frank as a test round (an offline test page
as in round 1): focus on show under Wayland, insertion into his apps
(with the engine logs), the shortcut, install/uninstall on 26.04, whether
Super+., Ctrl+C/V and Shift still behave with the engine selected, ten
searches of his own, and how it feels.

**Done when**: unit tests pass, eval targets in section 4c are met, the
window works under Xvfb with screenshots of the empty view, "american flag
happy" and the vet sentence, the headless insertion test passes, and
install/uninstall have been dry-run here as far as is safe (sudo and
gsettings steps against a throwaway settings backend).

## 10. Risks I know of

1. Commits lost if an app takes focus later than the rules in section 7
   allow; mitigated, not proven, until Frank's test logs.
2. Cold start of a fresh Python/GTK process may feel slow.
3. FlowBox speed in Python with the full browse chart.
4. Enrichment noise: generic terms pulling in junk; guarded by the
   40-emoji cap, the noise queries and the regression count.
5. The engine replaces the plain keyboard source as first input source;
   layouts with variants or other languages are not handled yet.
6. Frank's Python is 3.14, this machine's 3.12: no new-syntax features.
