# Problem: make emoji-picker production ready (install, upgrade, uninstall)

emoji-picker is a working prototype (this repository): a GTK 4 / libadwaita
picker window (`emoji_picker/`) plus a passive IBus engine (`engine/engine.py`)
that passes every key through and, when the picker asks over a Unix socket,
commits the chosen emoji into the focused app. `install.sh` / `uninstall.sh`
set it up today; read them.

## The owner's decisions (2026-11-05)

1. Audience: the owner, plus anyone who clones the GitHub repo and runs the
   installer. No .deb package.
2. The picker takes over **Super+.** from the built-in IBus emoji picker
   (whose stray characters started this project). Ctrl+Alt+E goes away.
3. Search stays English only.
4. The keyboard indicator in the top bar should not appear just because of
   this tool. Today the installer adds "Keyboard with emoji picker" as an
   extra input source next to the user's own "English (US)", so GNOME shows a
   source menu with a keyboard-glyph icon, labelled "Other (Keyboard with
   emoji picker)". The owner wants it to feel like their normal keyboard.

## Facts, measured

- Target: Ubuntu 26.04, GNOME Shell 50 on Wayland, IBus 1.5.34, Python 3.14.
  The owner's machine has the prototype installed (component at
  /usr/share/ibus/component/emoji-picker.xml with one engine named
  `emoji-picker`, input sources `[('ibus','emoji-picker'), ('xkb','us')]`,
  custom shortcut at .../custom-keybindings/emoji-picker/ bound to Ctrl+Alt+E,
  backups in ~/.local/state/emoji-picker/backup/).
- IBus loads engine components only from /usr/share/ibus/component (or
  IBUS_COMPONENT_PATH), so one root-owned file is unavoidable. A running
  ibus-daemon does not pick up a new component until it restarts; `ibus
  restart` must never be used (it broke the owner's Super+. once). Logging
  out and in restarts it.
- An IBus engine carries a keyboard layout (and optional variant); an empty
  `<layout_variant>` element stops IBus from activating it.
- GNOME Shell's input-source menu, for an IBus source, shows
  `IBus.get_language_name(language) (longname)` and in the top bar the
  engine's `<symbol>`, else a 2–3 letter language code, else a keyboard glyph.
  It hides the indicator when there is only one input source.
  For an xkb source it shows GnomeDesktop.XkbInfo's display name (e.g.
  "English (US)", short name "en").
- If an input source names an IBus engine the daemon does not know, GNOME
  skips it; if no source remains it falls back to the 'us' layout.
- Super+. today is IBus's emoji hotkey: gsettings
  `org.freedesktop.ibus.panel.emoji hotkey`, default
  `['<Super>period', '<Super>semicolon']`.
- Only one IBus engine is active at a time: while a user types with another
  IBus engine (e.g. Japanese), ours is not active and the picker falls back
  to copying the emoji (already implemented).
- Today the component's <exec> and the shortcut's command point into the git
  clone, so moving or deleting the clone breaks the install.

## What a good answer covers

How install, upgrade (from the prototype, and from one release to the next)
and uninstall should work; what the user sees and does at each step; what can
go wrong for a user whose setup differs from the owner's (another layout,
several layouts, another input method, a second user on the machine); and
what to test. Say where you are unsure.
