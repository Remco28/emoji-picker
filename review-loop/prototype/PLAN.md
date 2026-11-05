# Plan: emoji-picker prototype with build-time keyword enrichment

Frozen for review. The problem, Frank's decisions and the established facts are
in `PROBLEM.md` beside this file; this plan does not repeat them.

Success question: **Can Frank press a shortcut, type a few words or a
sentence, see the emoji he means near the top of a big keyboard-navigable
chart, press Enter, and have it appear in the app he was typing in, with
nothing left behind?**

## 1. Scope

In: the picker window, search (keywords, prefixes, phrases, shortcodes,
typo tolerance), build-time enrichment and its evaluation, recents and
frequency, skin-tone variants, insertion through the passive IBus engine with
a clipboard fallback, install/uninstall scripts, tests.

Out (later): replacing Super+., a .deb package, languages other than English,
other keyboard layouts beyond what the installer copies, settings UI,
"insert several then close", portal paste (it fails in terminals and
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
tools/build_data.py      emojibase tarball (pinned version + sha256) -> data/emoji.json
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
newer than that. Cached per font file mtime.

## 4. Enrichment (tested first, as Frank asked)

### 4a. The answer key comes before the keywords

`tests/eval_queries.json` is written and committed **before** any enrichment
is generated, so the keywords cannot be fitted to it. Each entry: the query,
and one or more groups of acceptable emoji; a query passes when every group
has a member in the top N (N = 5 for one concept, 10 for multi-concept
queries, 12 for sentences). Three sources, kept separate in the file:

1. **Frank's stories**: "american flag happy" (needs 🇺🇸, and one of the
   happy faces) and the vet sentence (needs a dog, one of 🏥 🩺 🚑, and 🙏).
2. **Persona queries** from the earlier simulated users: "skull", "party",
   "clap", "happy dog", "star", "check", "cake", "birthday", "tired but
   glad", "well done", "puppy", "praise", "tent fire", and others, about 40.
3. **A held-out set written by a different vendor's model** (Codex,
   gpt-6-luna), asked blind for 60 things people type into an emoji search
   box and the emoji they would expect. I review it only for impossible
   expectations (an emoji that does not exist), not for difficulty. This set
   is never shown to the enrichment model and is the main number.

Plus 10 **noise queries** ("the", "and", "asdfgh", "ok so") that must not
produce confident nonsense: stopword-only queries show the browse view;
gibberish shows "No matches".

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
shortcodes, and (b) baseline + enrichment, and reports hit@1 and pass rate
per source, the list of queries that regress, and search time.

Targets: held-out pass rate >= 85% enriched; enriched beats baseline on
every source; no more than 2 queries that the baseline passed now fail;
both of Frank's stories pass. If targets are missed I change the prompt or
the ranking (not the answer key) and rerun; each run's numbers go in the
ledger.

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
  trailing space), so results narrow on every keystroke. A word of 5+
  letters with no exact or prefix match gets **one-typo** matches.
- **Shortcodes**: a query starting with `:` matches shortcodes only, by
  prefix (`:fir` finds 🔥).
- **Ranking**: emoji that match **all** concepts come first ("Best
  matches"). If there is more than one concept, each concept then gets its
  own short row ("american flag", "happy"), so "american flag happy" shows
  🇺🇸 and happy faces even though no single emoji is both. Personal use adds
  a capped bonus (frequency with a 14-day half-life). Ties go to emojibase
  order.
- **Speed target**: under 5 ms per keystroke for search on this machine.

## 6. The window

- Adw.Application, single instance, **resident**: started hidden at login
  (autostart file) and by D-Bus activation if not running; the shortcut
  only asks it to show. Hiding instead of quitting keeps it instant.
- Default size about 760 x 560, resizable, size remembered. Ctrl+plus /
  Ctrl+minus change the emoji size (remembered).
- Top: a large search box, always focused. Below, a scrolled chart of
  sections. Empty query: **Recent** (last 16), **Frequent** (top 24), then
  every category in emojibase order. With a query: **Best matches**, then a
  row per concept, then **Related** (prefix and typo matches).
- Bottom bar: the highlighted emoji's name and shortcode, and the keys:
  "Enter insert · Ctrl+Enter skin tones · Esc close".
- Sections are FlowBoxes with a fixed column count computed from the width.
  The browse view is built once; result sections (at most ~150 emoji) are
  rebuilt per keystroke. Target: under 50 ms from keystroke to redrawn
  results on this machine.

**Keys** (search box keeps focus throughout):

| Key | Does |
|---|---|
| typing | narrows results; the first result is highlighted |
| arrows | move the highlight through the chart, across sections |
| Page Up / Down | move by a screen |
| Enter | insert the highlighted emoji (with its remembered tone) and close |
| Ctrl+Enter | open the tone/variant chooser for the highlighted emoji; arrows + Enter pick and insert |
| Esc | clear the search; if already empty, close |
| mouse | hover highlights, click inserts, right-click opens variants |

Left/Right always move the highlight, not the text cursor; Home/End/
Backspace still edit the search text.

**Variants**: choosing a tone for an emoji remembers it for that emoji. The
most recent tone chosen also becomes the default for tone-capable emoji you
have never set, so picking your tone once covers the rest. Two-person emoji
offer all tone pairs.

## 7. Insertion

1. Before hiding, the window asks the engine for its focus **generation**
   counter (it increments on every focus_in) while the picker's own search
   box holds focus.
2. It hides itself; focus returns to the previous app.
3. It waits until the engine reports a newer generation **and** no further
   focus change for 60 ms; if the engine also reports a cursor-location
   update after that focus_in (real text fields send one, the internal fake
   context did not in testing), it commits at once. Then it sends the text.
   Overall limit 1.5 s.
4. If the engine is unreachable, not the active input source, or the limit
   passes, the emoji is put on the clipboard and a notification says
   "Copied: press Ctrl+V (Ctrl+Shift+V in a terminal)". The clipboard is
   served by the resident app, so it survives the window hiding.

The engine logs every focus change, capability and cursor-location event
with timestamps, so Frank's next test tells us whether step 3's heuristics
hold on Wayland.

**Focus when showing.** A resident app on Wayland may not get focus when it
presents an existing window without an activation token (GNOME may show
"Emoji Picker is ready" instead). The shortcut command therefore forwards the
token it was launched with: it calls the app's
`org.freedesktop.Application.Activate` over D-Bus with `gdbus` (a C program,
fast) passing `activation-token` and `desktop-startup-id` from its
environment as platform data, so GTK uses it when presenting. The app logs
whether a token arrived and whether the window became active. If this fails
on Frank's machine, fallback mode is a fresh process per shortcut press
(slower start, proven to focus).

## 8. Install and uninstall

`install.sh` (asks for sudo once):

1. Backs up input sources and the custom-shortcut list (first run only).
2. Writes the engine component to `/usr/share/ibus/component/` with the
   repo path, and the keyboard layout copied from the user's first xkb input
   source (Frank: `us`).
3. Adds the engine as the **first** input source, keeping the others after
   it (Super+Space switches back).
4. Installs a .desktop file, a D-Bus service file and an autostart entry in
   the user's home.
5. Adds a custom shortcut **Ctrl+Alt+E** running the show command, warning
   if that binding is already taken.
6. Does **not** run `ibus restart` (it broke Super+. last time); it tells the
   user to log out and back in once.

`uninstall.sh` restores the backups, removes every file it added (sudo for
the component), and also asks for a logout.

## 9. How it will be checked

On the development machine:

- Unit tests (stdlib unittest): search parsing and ranking, shortcodes,
  prefix and typo matching, usage store (including a corrupt file), grid
  navigation, variant memory, data build validation.
- `tools/eval.py` numbers, baseline vs enriched, in the ledger.
- Headless engine test (private ibus-daemon, as in the probe): the picker's
  insert routine against a scripted focus sequence (picker context out ->
  fake context in -> target context in), checking the text reaches the
  target context and not the fake one.
- The real window under Xvfb: show it via D-Bus, type queries through a
  debug action, save screenshots, measure show time and keystroke-to-redraw
  time, and memory use.

Not checkable here and handed to Frank as a test round (an offline test page
as in round 1): focus on show under Wayland, insertion into his apps,
the shortcut, install/uninstall on 26.04, how it feels.

**Done when**: unit tests pass, eval targets in section 4c are met, the
window works under Xvfb with screenshots of the empty view, "american flag
happy" and the vet sentence, and install/uninstall have been dry-run here as
far as is safe (sudo steps excepted).

## 10. Risks I know of

1. Focus on show under Wayland (section 7): the biggest unknown.
2. Commits lost to the fake context if focus returns slowly.
3. FlowBox speed in Python with the full browse chart.
4. Enrichment noise: generic terms pulling in junk; guarded by the
   40-emoji cap, the noise queries and the regression count.
5. The engine replaces the plain keyboard source as first input source;
   layouts with variants or other languages are not handled yet.
6. Frank's Python is 3.14, this machine's 3.12: no new-syntax features.
