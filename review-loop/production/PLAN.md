# Plan v2: production-ready emoji-picker (v1.0)

Problem and the owner's decisions: [PROBLEM.md](PROBLEM.md). Base version:
commit 9b9275e (prototype plus the hover fix). v2 takes in peer pass 1
(LEDGER.md): a per-user registry, versioned install directories, explicit
`/usr/bin/python3`, mru-sources, `--doctor`, plainer installer text.

## What the user will see

1. `git clone`, `./install.sh --dry-run`, `./install.sh` (one password
   prompt). The clone can then be deleted.
2. The installer ends by saying what works now and what needs a logout:
   "Super+. now opens the picker. Until you log out and back in, Enter
   copies the emoji instead of typing it." (A prototype upgrade keeps
   inserting through the already-running engine, so it says so instead.)
3. After the logout: no keyboard indicator (if they had one layout), Super+.
   opens the picker and Enter types the emoji; IBus's own picker no longer
   reacts to Super+.
4. `emoji-picker-uninstall` (works without the clone) puts back plain
   keyboard sources and IBus's Super+., and removes the files once no user
   on the machine still has it installed.
5. Upgrading: pull or clone a newer version and run `./install.sh` again.
6. `emoji-picker --doctor` prints what is installed and active, for bug reports.

## 1. Files go to a fixed place

| What | Where |
|---|---|
| Python package, `engine/engine.py`, `finish-setup`, `uninstall.sh`, `VERSION` | `/usr/local/lib/emoji-picker/versions/<version>-<commit>/` |
| the version in use | `/usr/local/lib/emoji-picker/current` → `versions/...` (symlink) |
| who has it installed | `/usr/local/lib/emoji-picker/users/<uid>`: that user's layouts, one per line |
| launcher, uninstall launcher | `/usr/local/bin/emoji-picker`, `/usr/local/bin/emoji-picker-uninstall` |
| app entry, icon | `/usr/local/share/applications/io.github.remco28.EmojiPicker.desktop`, `/usr/local/share/icons/hicolor/scalable/apps/io.github.remco28.EmojiPicker.svg` |
| IBus component | `/usr/share/ibus/component/emoji-picker.xml` |

- **Upgrade is atomic.** The new version goes into its own directory, is
  byte-compiled there (`/usr/bin/python3 -m compileall -q`), then `current`
  is switched with `ln -sfn` to a temporary name and `mv -T` over `current`.
  If anything fails before the switch, the old version is still in use. The
  previous version directory is kept (a running engine may still use it);
  older ones are removed. All `sudo rm` paths are fixed in the script and
  guarded with `${VAR:?}`.
- **No dependence on PATH.** The component runs
  `/usr/bin/python3 -I /usr/local/lib/emoji-picker/current/engine/engine.py --ibus`.
  The launchers are small `#!/usr/bin/python3 -I` scripts that put
  `current` on `sys.path` and run the package. A pyenv or venv first on PATH
  cannot break them.
- The `.desktop` entry gives the window its name and icon in GNOME (Alt+Tab,
  notifications), and opens the picker from the app grid.

## 2. One emoji engine per keyboard layout, replacing it in place

For every layout in the registry (all users' files), the component has an
engine `emoji-picker:ID` (e.g. `emoji-picker:us`, `emoji-picker:de+nodeadkeys`):
layout and variant from ID (variant element only when non-empty); `language`
from GnomeDesktop.XkbInfo (`eng`, falling back to `other`); `symbol` = XkbInfo's
short name (`en`); `longname` = the bracketed part of XkbInfo's display name
plus ", with emoji", so the menu reads "English (US, with emoji)".

Install writes this user's registry file (their xkb layouts, plus any already
converted), then regenerates the component from the union of all registry
files. The prototype's single engine `emoji-picker` is not in it.

Sources (and `mru-sources`, the same way): each `('xkb', ID)` becomes
`('ibus', 'emoji-picker:ID')` in place; other sources, such as a Japanese
input method, are kept; the prototype's `('ibus', 'emoji-picker')` is
dropped. With one layout the user has one source and GNOME hides the
indicator. No xkb source at all: sources are left alone, and the installer
and README say the picker will copy instead of type.

Layouts added later in Settings stay plain until the installer is run again;
the picker's copy message says that.

## 3. Converting sources only once IBus knows the engines

A running ibus-daemon only reads the new component at the next login, and
GNOME drops a source whose engine it does not know (falling back to 'us').

- If `ibus list-engine` already lists every needed engine (a re-install with
  the same layouts), sources are converted immediately.
- Otherwise a one-shot autostart entry,
  `~/.config/autostart/io.github.remco28.EmojiPicker.finish-setup.desktop`,
  runs `finish-setup` at the next login: it waits up to 60 s (polling every
  0.5 s) for IBus to list the engines, converts sources and mru-sources as
  they are then, deletes its entry and logs to `setup.log`. If the engines
  never appear it changes nothing, keeps the entry for the next login and
  sends one notification.
- Prototype upgrade: the running daemon still has the old `emoji-picker`
  engine, so the old source stays until finish-setup replaces it; insertion
  keeps working throughout (same socket protocol). The new picker must keep
  working with the old engine's replies: the protocol is unchanged in v1.0.

## 4. Super+.

- First install: back up `org.freedesktop.ibus.panel.emoji hotkey` to
  `~/.local/state/emoji-picker/backup/ibus-emoji-hotkey.txt`.
- Remove only `'<Super>period'` from it and record that in
  `~/.local/state/emoji-picker/installed.json` (with the shortcut we wrote).
- The custom shortcut at the prototype's settings path: name "Emoji Picker",
  command `/usr/local/bin/emoji-picker`, binding `<Super>period`.
- `./install.sh --shortcut '<Control><Alt>e'` picks another key and leaves
  IBus's hotkey alone.
- Refuse if our settings path holds a shortcut we did not make; warn when
  another setting besides IBus's emoji hotkey uses the chosen key.

## 5. Uninstall

`emoji-picker-uninstall` or `./uninstall.sh` (the same script; `--dry-run`):

1. Sources and mru-sources: our engines back to `('xkb', ID)` in place; the
   prototype's source removed; others kept; never an empty list (`us`).
2. Shortcut: removed when its name is "Emoji Picker" and its command is ours
   (`/usr/local/bin/emoji-picker`, or a clone's `bin/emoji-picker`). If the
   user changed only the key, it is still removed, since its command is about
   to disappear. Otherwise left, with a message.
3. IBus hotkey: if installed.json says we removed `<Super>period` and it is
   not back, add it back at the front; other edits are kept.
4. The autostart entry, if present.
5. With sudo: remove this user's registry file. If others remain, regenerate
   the component from theirs (so they keep working) and keep the files.
   If none remain, remove the component, `current`, the versions, the
   launchers, the app entry and icon, then `ibus write-cache`.
6. History, settings and backups in `~/.local/state/emoji-picker` are kept,
   and it says where.

## 6. Smaller production items

- `LICENSE` (MIT), version 1.0.0, `emoji-picker --version`.
- `emoji-picker --doctor`: version and install path, input sources, the
  active engine, our engines IBus knows, the hotkey and shortcut, whether
  finish-setup is pending, the last lines of the logs.
- picker.log rotates at 1 MB like engine.log. The engine never logs keys.
- Chart cells get the emoji's name as their accessible label.
- The copy fallback names the cause and the fix ("this keyboard has no emoji
  support yet: run the installer again"), or "until you log out" when
  finish-setup is pending.
- README: install, upgrade, uninstall, what changes on the system, limits
  (other IBus input methods; English search; no xkb source), troubleshooting.

## 7. Tests

- Unit: source conversion and restore round trips (one layout, several, a
  variant, mixed with another IBus engine, the prototype entry, empty),
  hotkey removal and restore, component generation (language, symbol,
  longname, variant element, escaping), registry union.
- Private ibus-daemon: a component with two engines (`emoji-picker:us`,
  `emoji-picker:de`) started through `/usr/bin/python3 -I`; switching between
  them uses one engine process and both insert; `ibus list-engine` parsing.
- Installer end to end without sudo, against `GSETTINGS_BACKEND=keyfile`
  and temporary roots (test-only `--root`): fresh install, prototype
  upgrade, re-install, a second user, finish-setup with a stubbed engine
  list, uninstall of one user then the last, a failed upgrade step leaving
  `current` intact.
- Round 3 for the owner on the Wayland machine: a human-feedback guide
  (install, logout, indicator gone, Super+., insert, lock-screen unlock,
  `--doctor`, uninstall and reinstall).

## Out of scope

Search quality, other languages, a .deb, other desktops, inserting while
another IBus input method is active.
