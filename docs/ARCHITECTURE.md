# How emoji-picker works

For anyone changing the code. The README covers using it; `DESIGN.md`
records taste decisions; `review-loop/` holds the reviews that shaped it.

## The pieces

```
Super+.  ──>  emoji-picker (GTK 4 window)
                 │ search, chart, keys, history
                 │
                 │ JSON over $XDG_RUNTIME_DIR/emoji-picker-ibus.sock
                 v
              engine.py (IBus engine "<layout>, with emoji")
                 │ passes every key through; commits the emoji on request
                 v
              the app you were typing in
```

Two processes, never more:

- **The picker** (`emoji_picker/`, started by the shortcut) is a GTK 4 /
  libadwaita window. It searches, shows the chart, and on Enter asks the
  engine to type the emoji. It is single-instance: pressing Super+. while
  it is open brings it forward (or opens a fresh one if the old one is
  already inserting).
- **The engine** (`engine/engine.py`, started by IBus) replaces the user's
  keyboard layout with the same layout plus a socket. It never changes a
  key. Its one job is `commit` into whichever app has focus.

Why an IBus engine and not the clipboard or a fake keypress: on GNOME
Wayland an app cannot type into another app, and the clipboard is only
reliable while the picker itself has focus. The probe rounds that settled
this are in `probe/` and `human_feedback/round-2026-11-03-insertion-probe/`.

## Inserting, step by step (`insert.py`)

1. Before the window hides, ask the engine for `status`. If it is not
   running or not the active input method, copy the emoji now (while the
   picker still has focus) and say why (`insert.why_not_active()`).
2. Otherwise remember the engine's focus counter, hide the window, and poll
   every 25 ms. Commit only once a real app has taken focus after the hide
   (counter went up, client is not IBus's internal "fake" context, 150 ms
   since hiding, 30 ms with no further focus change).
3. Give up after 2 s and notify; never commit blind, because a commit into
   the fake context silently disappears.

## Search (`search.py`, `data.py`)

Plain keyword search, under a millisecond, no model at runtime.
`emoji_picker/data/emoji.json` comes from emojibase (`tools/build_data.py`);
`enrich-en.json` adds meaning terms written once by an LLM
(`tools/enrich.py`). `Index.sections()` returns the sections the window
shows ("Best matches", one line per word, "Related"), and `tools/eval.py`
scores exactly that against `tests/eval_queries.json`.

## The window (`window.py` and friends)

| Module | Holds |
|---|---|
| `window.py` | the window: search bar, chart, pinned section title, preview card, key hints; key handling; modes (browsing, tones, inserting, copied) |
| `nav.py` | arrow and page movement over sectioned lines; `Pointer`, which ignores a pointer that has not really moved (stops hover from stealing the keyboard highlight) |
| `design.py` | every size, spacing and colour role, in one place (text sizes are libadwaita classes) |
| `layout.py` | columns per line at the default window, shared by the window and the search eval |
| `fonts.py` | hides emoji newer than the installed emoji font can draw |
| `usage.py` | recents, frecency (14-day half-life), remembered skin tones |

## Install (`install.sh`, `system.py`, `setup_steps.py`)

`system.py` is the logic, standalone and unit-tested (it runs as
`python3 -I system.py ...`, with no package imports); the shell scripts call
it and do the side effects.

- **Code** goes to `/usr/local/lib/emoji-picker/versions/<version>-<commit>-<time>`,
  and the `current` symlink is switched atomically, so a failed upgrade
  leaves the old version working. One previous version is kept.
- **Engines**: one per keyboard layout, named `emoji-picker:<xkb id>`
  (for example `emoji-picker:de+nodeadkeys`), in
  `/usr/share/ibus/component/emoji-picker.xml`. The component holds the
  union of every user's layouts, recorded in `.../users/<uid>`, so one
  user's uninstall does not break another's keyboard.
- **Input sources** are converted at once if IBus already knows the
  engines; otherwise at the next login by a one-shot autostart entry
  (`emoji-picker --finish-setup`), which waits up to 60 s for IBus and then
  removes itself.
- **Super+.**: only `<Super>period` is removed from IBus's emoji hotkey
  (recorded in `~/.local/state/emoji-picker/installed.json`), and a custom
  GNOME shortcut runs `/usr/local/bin/emoji-picker`.
- **Uninstall** reverses each step, touching only entries that are still
  ours. A setting whose restored value is its default is reset, not set
  (`system.py is-default`), so no copy of a default is left pinned. Folders
  the installer created are listed in `created-dirs` (`$LIB/` for system
  folders, the state folder for the user's) and removed once empty. The cache
  always goes; history, settings and the backup go with `--purge`. A fresh
  install after an uninstall backs up the settings of then, keeping the old
  backup as `backup-until-<time>`.

## Where things live on a user's machine

| Path | What |
|---|---|
| `~/.local/state/emoji-picker/usage.json` | history and tones |
| `~/.local/state/emoji-picker/{picker,engine,setup}.log` | logs (focus changes and inserted emoji, never typed text) |
| `~/.local/state/emoji-picker/installed.json` | what the installer changed, for uninstall |
| `~/.local/state/emoji-picker/backup/` | the user's settings before the first install |
| `~/.config/autostart/io.github.remco28.EmojiPicker.finish-setup.desktop` | present only until the login step has run |

`emoji-picker --doctor` prints all of this.

## Tests

`python3 -m unittest discover -s tests -t .` runs everything:

- `test_system.py`: source conversion, restore, registry, hotkey, component.
- `test_installer.py`: real `install.sh` / `uninstall.sh` runs against a
  keyfile gsettings backend, a temporary `--root` and a stub `ibus`. The
  "no trace" tests snapshot every file and setting before the install and
  compare after the uninstall.
- `test_insert_ibus.py`: a private `ibus-daemon` with the real engine,
  committing into a test client (skipped without IBus).
- `test_search.py`, `test_nav.py`, `test_usage.py`, `test_data.py`.

Wayland, the GNOME Shell shortcut and the lock screen cannot be tested
headless; the `human_feedback/` rounds are where those were checked.

## Mistakes that are easy to make

- **Never run `ibus restart`** in a script or while testing on a real
  session: it broke Super+. on the target machine once. `ibus write-cache`
  plus a fresh login is enough.
- **An empty `<layout_variant>` element** in the component stops the engine
  from activating; write the element only when there is a variant.
- **`gsettings list-recursively` skips custom keybindings** (a relocatable
  schema), so a shortcut-conflict check must also read each custom path.
- **IBus sources are skipped until IBus is up**, and with no source left
  GNOME types US. That is why non-US layouts keep a plain backup.
- **Pointer "motion" events arrive without movement** when the chart
  scrolls under a resting pointer; treat only real movement as hover.
