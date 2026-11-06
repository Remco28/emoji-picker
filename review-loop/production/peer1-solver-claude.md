I read PROBLEM.md, both scripts, the component template, `gsettings_lists.py`, the engine, `insert.py`, the launcher and `probe/setup.sh`. I ran nothing against a live IBus or GNOME session. "Know" means documented behaviour, GNOME Shell or IBus source I'm confident of, or the measured facts. "Believe" means I need to check it.

# Plan: making emoji-picker production ready

## What the prototype gets wrong
- **Install points into the clone.** The component's `<exec>` (`install.sh:76`) and the shortcut command (`install.sh:97`) point into the clone, so deleting the clone breaks the install.
- **It adds a source instead of replacing one.** `add-source` (`tools/gsettings_lists.py:50`) puts a new engine in front of the user's own sources. That always creates two sources and so always shows the indicator, which conflicts with decision 4.
- **The engine pretends to be "other".** It uses `<language>other`, an `input-keyboard` icon, and only the layout of the *first* xkb source. That produces "Other (Keyboard with emoji picker)" and a keyboard glyph. Users with two layouts get the wrong keymap.
- **It depends on whatever `python3` is on PATH.** `#!/usr/bin/env python3` and `bin/emoji-picker` both use it. A pyenv or venv first on PATH has no `gi`, so the engine dies silently. (Believe: ibus-daemon inherits the session PATH.)
- **Uninstall can strand a second user.** It removes the system file with no thought for other users of the machine. A user whose sources name our engine would fall back to `us` (measured fact).

## 1. Files, install, upgrade, uninstall

**Where files go**
- **System files (sudo, once per install or upgrade):**
  - Code in `/usr/local/lib/emoji-picker/<version>/`, with a `current` symlink.
  - A launcher at `/usr/local/bin/emoji-picker` that runs `/usr/bin/python3 -I`.
  - `/usr/share/ibus/component/emoji-picker.xml`, whose `<exec>` points into `current`.
  - A user registry, `/usr/local/lib/emoji-picker/users/<uid>`.
- **Per-user files:** `~/.local/state/emoji-picker/manifest.json` records:
  - the version;
  - each source we replaced;
  - the original IBus emoji hotkey, and whether it was the default;
  - the shortcut path.
- After install, the clone can be deleted.

**One engine per xkb layout ("mirrored engines").** For each xkb source in use, the component holds an engine such as `emoji-picker-xkb:de:nodeadkeys`. Each has:
- that layout and variant (the variant element only when there is one);
- the language from xkeyboard-config;
- a `<symbol>` equal to XkbInfo's short name;
- a `<longname>` chosen so the menu text matches XkbInfo's display name. For example, language "en" plus longname "US" gives "English (US)". (Believe: the strings match for common layouts. Check against `IBus.get_language_name` on 26.04.)

The installer merges new engines into the existing file, so engines other users need are kept.

**Install (`./install.sh`). What the user sees:**
1. A summary of the planned changes.
2. One sudo prompt.
3. "Log out and back in once to finish."

What it does:
1. Checks dependencies with `/usr/bin/python3`.
2. Refuses if Super+. is bound to anything other than IBus or us.
3. Writes the manifest.
4. Installs the files and runs `ibus write-cache`, never `ibus restart`.
5. Sets the Super+. shortcut and the IBus hotkey (section 3).
6. Leaves the input sources alone for now. Until the next login the daemon doesn't know the new engines, and GNOME would skip them, sending a `de` user to `us` (fact).
7. Adds a one-shot autostart entry, `emoji-picker --finish`. At login it:
   - polls IBus (up to ~15 s) until our engines are listed;
   - swaps each `('xkb', X)` for its mirrored engine in place, keeping order and leaving other entries alone;
   - removes itself.

   If the engines never appear, it changes nothing and sends a notification. Until then the picker falls back to copying, which already works.

**Upgrade from the prototype** (detected by the old `<exec>` pointing into a clone, the `('ibus','emoji-picker')` source, or the Ctrl+Alt+E shortcut):
- Removes the `('ibus','emoji-picker')` source now. The plain xkb source behind it keeps working, and the user is left with one source and no indicator.
- Re-points the existing shortcut path to Super+. (decision 2: Ctrl+Alt+E goes away).
- Keeps the old backup directory.
- Tells the user: "keep the clone until you log out" (the old engine still runs from it).

**Upgrade between releases (`git pull && ./install.sh`):**
- Installs the new version directory, swaps `current` atomically, and keeps one older version for rollback.
- Regenerates the component only if the engine list or `<exec>` changed.
- Asks the user to log out only if `engine.py` changed. Until then the old engine keeps running.
- The socket protocol gets a version field. New pickers must keep working with the old `status`/`commit` replies.

**Uninstall (`./uninstall.sh`, or `emoji-picker --uninstall` once the clone is gone):**
1. Swaps each mirrored engine back to its xkb source in place. This takes effect immediately with no logout (believe).
2. Removes the shortcut and restores the IBus hotkey (section 3).
3. Removes the autostart entry and deletes this user's registry entry.
4. With sudo: removes the component and `/usr/local` files only if no other registry entries remain. Otherwise it removes only engines no other user needs, or leaves them and says so.
5. Keeps history and logs, and prints where they are.

## 2. Decision 4: no indicator because of this tool
The count and labels of sources stay what the user already had.
- **One layout:** still one source, so no indicator (fact). Typing uses the same keymap (know: GNOME Shell takes the xkb keymap of an IBus source from the engine's layout).
- **Several layouts:** the indicator was already shown because of the user's own setup. Same count, same symbols, and (believe) the same menu text.
- **Another input method (e.g. Mozc) next to a layout:** only the layout is mirrored. While Mozc is active the picker copies instead (fact, already implemented).
- **Only IBus sources, no xkb source:** we add nothing, because adding a source would create an indicator. The installer says the picker will copy instead.
- **Layouts added later in Settings:** these stay plain xkb, and the picker copies while one is active. Re-running the installer mirrors them.
- **Settings' "Add input source" list:** our engines also appear there, looking like duplicates. Accepted cost.

## 3. Super+.
**Taking it over:**
- Remove only `<Super>period` from `org.freedesktop.ibus.panel.emoji hotkey`; `<Super>semicolon` stays with IBus.
- Record whether the key was at its default.
- Bind Super+. to `/usr/local/bin/emoji-picker` through the existing custom-keybinding path.
- Believe: a Shell/gsd global grab already beats IBus's in-context hotkey. Removing ours from IBus guarantees IBus's picker never also fires, which is the source of the stray characters.
- Believe: IBus picks up hotkey changes live. Verify; otherwise the change takes effect at the next login anyway.

**Giving it back:**
- If the value still equals what we wrote, either `gsettings reset` it (when it was the default) or write back the saved value.
- If the user changed it since, leave it and say so.

## 4. Riskiest parts, and how to find out early
1. **Mirrored engines look and behave like the plain layout on GNOME 50 Wayland.** Check: no indicator, correct variant keymap, lock-screen password entry, and the menu text. First task: a 2-minute probe for the owner. It installs one extra mirrored engine named `…-probe` that isn't in their sources, so it can't break their session. After a logout, they set it as their only source by hand and screenshot the result. Undo is one command.
2. **The login-time swap.** Risks: a race with ibus-daemon registering engines, GNOME switching the active source when the list changes, and stale `mru-sources`. Check: run `--finish` 20 times against a freshly started private daemon on the dev box, then once on the owner's machine with logging.
3. **Super+. on Wayland.** The custom keybinding must win over IBus, the overview must not open on Super release (believe it doesn't when another key is pressed), and the picker must get focus. Check: the owner's first test after the probe. Ctrl+Alt+E already launching with focus is encouraging, but it isn't the same key.

## 5. Testing on Ubuntu 24.04 X11
- **Unit tests (pure functions):**
  - source↔engine mapping, variants, and ordering;
  - install→uninstall round trip restoring exactly the original state for about 30 source lists;
  - idempotent re-runs;
  - prototype-migration fixtures;
  - hotkey restore when the value was default, when it was ours, and when the user changed it.
- **Installer in a sandbox:**
  - `dbus-run-session` with a temporary `XDG_CONFIG_HOME`, giving a separate dconf database (believe);
  - a `--root` prefix and a fake `sudo` on PATH;
  - run install, upgrade from a prototype snapshot, a second user, and uninstall; assert on the dconf values and files.
- **Engine against a private ibus-daemon** with `IBUS_COMPONENT_PATH`, as the probe did:
  - the generated component loads;
  - every engine activates, including variants;
  - `has-focus-id` works;
  - commits are refused in the fake context.

  IBus there is 1.5.29, not 1.5.34.
- **Real session:** a throwaway user on the dev box covering indicator hiding, the login swap, Super+. and uninstall under X11. This is the same Shell indicator logic as Wayland (believe), but GNOME 46, not 50.
- **Wayland and GNOME 50 can only be checked on the owner's machine.** Ship `emoji-picker --doctor`, which prints:
  - sources, the active engine and the engines IBus knows;
  - the hotkey value and the shortcut;
  - the end of the log.

  Plus a 10-minute checklist (each of the three risks, then uninstall and reinstall). Results go back to the developer.

**Not checked:** I had no live IBus or GNOME session, and no 26.04 VM image or network. That leaves these unverified:
- that the menu strings match exactly;
- that IBus applies hotkey changes live;
- that PATH handling and the lock screen behave as I expect on Wayland.
