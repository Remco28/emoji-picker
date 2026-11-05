# emoji-picker

A keyboard-first emoji picker for Ubuntu / GNOME on Wayland. Emoji only.

Press **Ctrl+Alt+E**, type a few words or a whole sentence, press **Enter**:
the emoji appears in the app you were typing in, with nothing left behind.

**Status: working prototype**, tested headlessly on Ubuntu 24.04 (X11) and
awaiting its first real test on Ubuntu 26.04 (Wayland). See "What is known"
below.

## How it works

- **Search by meaning, with no AI at runtime.** Every emoji carries extra
  search terms written once, at build time, by an LLM (for example 🇺🇸 gets
  "american flag", "fourth of july"; 🏥 gets "surgery", "get well soon").
  The picker itself does plain keyword search in under a millisecond.
- **Insertion without the clipboard.** A small passive input-method engine
  (IBus) commits the emoji straight into the focused app. It passes every
  key through, so typing is unchanged. If it cannot insert, the picker copies
  the emoji instead and says so.
- **Learns you.** Recent and frequent emoji first; the skin tone you choose
  is remembered per emoji and becomes your default.

## Install

Needs Python 3 with GTK 4, libadwaita and IBus bindings (present on Ubuntu
GNOME) and the Noto Color Emoji font.

```
git clone https://github.com/Remco28/emoji-picker
cd emoji-picker
./install.sh --dry-run   # see every step first
./install.sh             # asks for your password once
```

Then log out and back in once (so IBus loads the engine). Your original
input sources and shortcut list are backed up to
`~/.local/state/emoji-picker/backup/`. `./uninstall.sh` removes only what
the installer added.

## Keys

| Key | Does |
|---|---|
| typing | narrows the chart; works for words, phrases and sentences |
| arrows, Page Up/Down | move the highlight |
| Enter | insert the highlighted emoji |
| Tab | skin tones for the highlighted emoji (Tab or Esc to go back) |
| Ctrl+C | copy instead of inserting |
| Ctrl+plus / Ctrl+minus | bigger / smaller emoji |
| Esc | clear the search; on an empty search, close |
| `:fire` | search shortcodes |

## What is known

Search quality is measured against a frozen answer key
(`tests/eval_queries.json`), including 60 queries written blind by another
vendor's model:

| | plain keywords | with build-time terms |
|---|---|---|
| held-out test half | 19/30 | 27/30 |
| held-out tuning half | 21/30 | 28/30 |
| blind judge (Gemini, 30 queries, both orders) | preferred 4 times | preferred 14 times (12 ties) |

Known gaps: "vet" does not lead to 🏥 (no term links them); after
"american flag happy" the American Samoa flag still ranks second; startup
time on a real Wayland desktop is not measured yet. The full record is in
`review-loop/prototype/`.

## Development

```
python3 -m unittest discover -s tests -t .   # unit + headless IBus tests
python3 tools/eval.py                        # search quality
python3 tools/build_data.py                  # rebuild emoji data (pinned emojibase)
python3 tools/enrich.py                      # regenerate search terms (needs `claude`)
```

Emoji data: [emojibase](https://emojibase.dev) (MIT), derived from Unicode
CLDR. The `probe/` folder holds the earlier insertion experiments.
