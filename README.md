# emoji-picker

A keyboard-first emoji picker for Ubuntu / GNOME on Wayland. Emoji only.

Version 1.0, in daily use on Ubuntu 26.04 (GNOME 50, Wayland).

Press **Super+.**, type a few words or a whole sentence, press **Enter**: the
emoji appears in the app you were typing in, with nothing left behind.

## How it works

- **Search by meaning, with no AI at runtime.** Every emoji carries extra
  search terms written once, at build time, by an LLM (for example 🇺🇸 gets
  "american flag", "fourth of july"; 🏥 gets "surgery", "get well soon").
  The picker itself does plain keyword search in under a millisecond.
- **Insertion without the clipboard.** Your keyboard layout is swapped for
  the same layout "with emoji": a small IBus input method that passes every
  key through unchanged and, when the picker asks, types the emoji into the
  focused app. If it cannot, the picker copies the emoji and says why.
- **Learns you.** Recent and frequent emoji first; the skin tone you choose
  is remembered per emoji and becomes your default.

## Install

Needs Ubuntu (or another distribution) with GNOME, IBus, Python 3 and the
Noto Color Emoji font. On Ubuntu GNOME these are already installed; otherwise:
`sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-ibus-1.0 fonts-noto-color-emoji`.

```
git clone https://github.com/Remco28/emoji-picker
cd emoji-picker
./install.sh --dry-run   # see every step first
./install.sh             # asks for your password once
```

Then **log out and back in once**. Until then Super+. already opens the
picker, but Enter copies the emoji (paste with Ctrl+V) instead of typing it.

After installing you can delete the clone: the app lives in
`/usr/local/lib/emoji-picker`.

To use another key than Super+.: `./install.sh --shortcut '<Control><Alt>e'`.

### What the installer changes

| Change | Undone by uninstall |
|---|---|
| The app in `/usr/local/lib/emoji-picker`, `/usr/local/bin/emoji-picker`, an app entry and icon | removed (once no user on the computer still uses it) |
| `/usr/share/ibus/component/emoji-picker.xml`: one "with emoji" engine per keyboard layout | removed, or rewritten for the users still using it |
| Your input sources: each keyboard layout becomes the same layout "with emoji" (other input methods are kept). A layout other than plain US also keeps the plain layout, last, as a backup (see Limits) | each goes back to the plain layout |
| A custom shortcut "Emoji Picker" on Super+. | removed, unless you pointed it at something else |
| IBus's own emoji picker lets go of Super+. (keeps Super+;) | Super+. given back |

Your original settings are backed up first, to
`~/.local/state/emoji-picker/backup/`. The installer never runs `ibus restart`.

## Upgrade

Pull (or clone) a newer version and run `./install.sh` again. The new version
is installed beside the old one and switched to in one step, so a failed
upgrade leaves the old one working.

If you add a keyboard layout in Settings later, run `emoji-picker --setup`
to give it emoji too (no clone needed); until then the picker copies while
that layout is active.

## Uninstall

```
emoji-picker-uninstall --dry-run   # see every step first
emoji-picker-uninstall
```

then log out and back in once. Your emoji history and settings stay in
`~/.local/state/emoji-picker`; delete that folder if you want them gone.

## Keys

| Key | Does |
|---|---|
| typing | narrows the chart; works for words, phrases, sentences and category names ("food", "flags") |
| arrows, Page Up/Down | move the highlight |
| Ctrl+↑ / Ctrl+↓ | jump to the previous / next category or result line |
| Enter | insert the highlighted emoji |
| Tab | skin tones for the highlighted emoji (Tab or Esc to go back) |
| Ctrl+C | copy instead of inserting |
| Ctrl+plus / Ctrl+minus / Ctrl+0 | bigger / smaller / default size emoji |
| Esc | close skin tones; clear the search; on an empty search, close |
| `:fire` | search shortcodes |

## Limits

- **Other input methods.** IBus runs one input method at a time. While you
  type with another one (Japanese, Chinese, Korean...), the picker copies the
  emoji for you to paste instead of typing it.
- **No plain keyboard layout.** If your input sources contain no keyboard
  layout at all, there is nothing to add emoji to, and the picker copies.
- **The keyboard indicator** disappears only for a single US layout. GNOME
  types with US whenever IBus is not running (the first moments after login,
  or if it crashes), so any other layout keeps its plain version as a backup
  input source, and GNOME then shows its indicator. US users lose nothing,
  since US is GNOME's fallback anyway.
- **English search only.**
- **GNOME only.** Used on Ubuntu 26.04 (GNOME 50, Wayland); the installer
  and tests also run on Ubuntu 24.04 (GNOME 46). Other desktops are untested.

## Troubleshooting

```
emoji-picker --doctor
```

prints the version, your input sources, the engines IBus knows, the
shortcut, and the last lines of the logs in `~/.local/state/emoji-picker/`
(`picker.log`, `engine.log`, `setup.log`). Include it in a bug report; it
shows the emoji you inserted recently, and nothing you typed.

- *Super+. opens IBus's emoji box instead:* log out and back in once.
- *"Setup finishes when you log out and back in":* exactly that; if it
  keeps saying so after a login, `--doctor` and `setup.log` say why.

## Search quality

Measured against a frozen answer key (`tests/eval_queries.json`), including
60 queries written blind by another vendor's model:

| | plain keywords | with build-time terms |
|---|---|---|
| held-out test half | 19/30 | 27/30 |
| held-out tuning half | 20/30 | 28/30 |
| blind judge (Gemini, 30 queries, both orders) | preferred 4 times | preferred 14 times (12 ties) |

Known gaps: "vet" does not lead to 🏥; after "american flag happy" the
American Samoa flag ranks second. The record is in `review-loop/prototype/`.

## Development

How the pieces fit, and the mistakes that are easy to make:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Design decisions:
[docs/DESIGN.md](docs/DESIGN.md).

```
bin/emoji-picker                             # run from the clone, without installing
python3 -m unittest discover -s tests -t .   # unit, installer and headless IBus tests
python3 tools/eval.py                        # search quality
python3 tools/build_data.py                  # rebuild emoji data (pinned emojibase)
python3 tools/enrich.py                      # regenerate search terms (needs `claude`)
```

License: MIT (`LICENSE`). Emoji data: [emojibase](https://emojibase.dev)
(MIT), derived from Unicode CLDR. The `probe/` folder holds the earlier
insertion experiments.
