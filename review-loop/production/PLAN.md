# Plan: production-ready emoji-picker (v1.0)

Problem and the owner's decisions: [PROBLEM.md](PROBLEM.md). Base version:
commit 9b9275e (prototype plus the hover fix).

## What the user will see

1. `git clone`, `./install.sh --dry-run`, `./install.sh` (one password
   prompt). The clone can then be deleted; nothing runs from it.
2. They log out and back in once. After that, the top bar shows no
   keyboard indicator (if they had one keyboard layout before), Super+. opens
   the picker, and the IBus emoji picker no longer reacts to Super+.
3. Before that logout their keyboard keeps working exactly as before
   (sources are not converted until IBus can see the new engines).
4. `emoji-picker-uninstall` (installed, so it works without the clone) puts
   back the plain keyboard sources and IBus's Super+. and removes every file.
5. Upgrading: pull or clone a newer version and run `./install.sh` again.

## 1. Files go to a fixed place

`install.sh` copies, with `sudo install`, to:

| What | Where |
|---|---|
| Python package `emoji_picker/` (with data) and `engine/engine.py` | `/usr/local/lib/emoji-picker/` |
| `finish-setup`, `uninstall.sh`, `VERSION` (version + git commit) | `/usr/local/lib/emoji-picker/` |
| launcher | `/usr/local/bin/emoji-picker` |
| uninstall launcher | `/usr/local/bin/emoji-picker-uninstall` |
| app entry | `/usr/local/share/applications/io.github.remco28.EmojiPicker.desktop` |
| icon | `/usr/local/share/icons/hicolor/scalable/apps/io.github.remco28.EmojiPicker.svg` |
| IBus component | `/usr/share/ibus/component/emoji-picker.xml` (IBus reads only there) |

- The old tree is replaced whole: install to `/usr/local/lib/emoji-picker.new`,
  then `rm -rf` the old one and `mv` (both under `sudo`, paths fixed in the
  script, guarded with `${VAR:?}`).
- `python3 -m compileall -q` runs on the installed tree, so users (who cannot
  write there) never recompile on each start.
- The `.desktop` file makes GNOME show the picker's name and icon (Alt+Tab,
  app grid). `NoDisplay=false`, so it can also be opened from the app grid.

## 2. One emoji engine per keyboard layout, replacing it in place

For every `('xkb', ID)` in the user's input sources, the component gets an
engine `emoji-picker:ID` (e.g. `emoji-picker:us`, `emoji-picker:de+nodeadkeys`):

- `layout` / `layout_variant` from ID (variant element only when non-empty).
- `language`: the layout's first language from GnomeDesktop.XkbInfo
  (`eng`), so the menu says "English (…)". Fallback when GnomeDesktop is
  missing: `other`.
- `symbol`: XkbInfo's short name (`en`), the same text GNOME shows for the
  plain layout.
- `longname`: the part in brackets of XkbInfo's display name plus ", with
  emoji": "English (US)" → longname "US, with emoji" → menu "English (US,
  with emoji)". No brackets ("German") → "with emoji".
- The component also keeps every `emoji-picker:*` engine already in an
  installed component of ours (a second user on the machine, or a layout
  removed since), so installing for one user never takes an engine away from
  another. The old prototype engine `emoji-picker` is dropped.

Sources: each `('xkb', ID)` becomes `('ibus', 'emoji-picker:ID')` in the same
position. Other sources (other IBus engines such as Japanese) are kept as
they are. The prototype's `('ibus', 'emoji-picker')` is removed. With one
layout, the user ends with one source, so GNOME hides the indicator.

If the user has no xkb source, sources are left alone and the installer says
the picker will copy instead of insert.

## 3. Converting sources only once IBus knows the engines

A running ibus-daemon does not see a new component until the next login, and
GNOME drops a source whose engine it does not know (falling back to 'us'). So:

- If `ibus list-engine` already lists every needed `emoji-picker:*` engine
  (a re-install with the same layouts), the installer converts the sources
  immediately.
- Otherwise it writes a one-shot autostart entry,
  `~/.config/autostart/io.github.remco28.EmojiPicker.finish-setup.desktop`,
  running `/usr/local/lib/emoji-picker/finish-setup`. At the next login that
  waits (up to 60 s, polling every 0.5 s) until IBus lists the engines,
  converts the sources (same rule as above, applied to the sources as they
  are then), deletes its autostart entry and logs to
  `~/.local/state/emoji-picker/setup.log`. If the engines never appear, it
  leaves the sources alone, keeps the entry for the next login, and sends one
  notification saying so.
- The shortcut and the Super+. change (section 4) are applied at install
  time. Until the sources convert, Super+. opens the picker and Enter falls
  back to copying, with the existing "not the active input source" message.

## 4. Super+.

- Backup, first time only: `org.freedesktop.ibus.panel.emoji hotkey` to
  `~/.local/state/emoji-picker/backup/ibus-emoji-hotkey.txt`.
- Remove only `'<Super>period'` from that list (keep `'<Super>semicolon'` and
  anything else), and record in `~/.local/state/emoji-picker/installed.json`
  that we removed it.
- The custom shortcut (same settings path as the prototype, so a prototype
  install is simply updated) gets binding `<Super>period`, command
  `/usr/local/bin/emoji-picker`, name "Emoji Picker".
- `./install.sh --shortcut '<Control><Alt>e'` picks another key; then the
  IBus hotkey is left alone.
- Refuse, as today, if our settings path holds a shortcut we did not make.
  Warn (not refuse) when another setting besides IBus's emoji hotkey uses
  the chosen key.

## 5. Uninstall

`emoji-picker-uninstall` (or `./uninstall.sh` in a clone; both the same
script, with `--dry-run`):

1. Sources: each `('ibus', 'emoji-picker:ID')` back to `('xkb', ID)` in
   place; the prototype's `('ibus','emoji-picker')` removed; others kept. If
   that would leave the list empty, `('xkb','us')`.
2. Shortcut: removed only if its name is "Emoji Picker" (as today).
3. IBus hotkey: if installed.json says we removed `<Super>period` and it is
   not back already, add it back at the front. Other changes the user made
   since are kept.
4. Autostart entry removed if present.
5. With sudo: the files of section 1, then `ibus write-cache`. It cannot
   see other users' settings, so it removes the component anyway and says
   this affects every user on the machine who installed it.
6. Usage history, settings and backups in `~/.local/state/emoji-picker` are
   kept, and the script says where they are.

## 6. Smaller production items

- `LICENSE` (MIT, as the component already declares).
- Version 1.0.0 in `emoji_picker/__init__.py`; `emoji-picker --version`.
- picker.log rotates at 1 MB like engine.log.
- Each chart cell gets an accessible label (the emoji's name) for screen readers.
- When the active source is not one of ours (a layout added after install,
  or another input method), the copy fallback message says so plainly and
  names the fix ("run the installer again to add emoji to this keyboard").
- README: install, upgrade, uninstall, what changes on the system, limits
  (other IBus input methods; English search), troubleshooting (logs).

## 7. Tests

- Unit (`tests/test_setup.py`): source conversion and restore round-trip
  (one layout, several, a variant, mixed with another IBus engine, the
  prototype entry, an empty list), hotkey removal and restore (user changed
  it since), component generation (language, symbol, longname, variant
  element, keeping existing engines, escaping).
- Private ibus-daemon (`tests/test_insert_ibus.py`): a component with two
  engines (`emoji-picker:us`, `emoji-picker:de`); switching between them uses
  the one engine process and both insert.
- Installer end to end, without sudo, against `GSETTINGS_BACKEND=keyfile`
  and a temporary prefix (test-only flags `--prefix` and `--component-dir`):
  fresh install, upgrade from the prototype state, re-install, finish-setup
  with a stubbed engine list, uninstall back to the starting settings.
- Round 3 for the owner on the Wayland machine: a human-feedback guide.

## Out of scope

Search quality (the two story failures, "cake"), other languages, a .deb,
other desktops, inserting while another IBus input method is active.
