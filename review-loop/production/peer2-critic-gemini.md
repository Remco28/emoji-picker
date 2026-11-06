Initial findings from `plan/PLAN.md` and `plan/PROBLEM.md` while inspecting the prototype:

- **Prototype upgrade breaks between logout/login and `finish-setup` (or loses the user's keyboard layout immediately upon login)**:
  In Section 2 & 3, on upgrade from the prototype, the new `/usr/share/ibus/component/emoji-picker.xml` is written immediately during `install.sh`, and *"The prototype's single engine `emoji-picker` is not in it."* During the current session, `ibus-daemon` still has `emoji-picker` in memory, so `sources` is left untouched (`[('ibus', 'emoji-picker'), ('xkb', 'us')]`) and `finish-setup` is scheduled via XDG autostart for the next login.
  When the user logs out and logs back in, **GNOME Shell (`ibus-daemon`) starts before/concurrently with XDG autostart (`finish-setup`)**, and reads `/usr/share/ibus/component/emoji-picker.xml`, which no longer contains `emoji-picker`. Worse: how does `finish-setup` convert a prototype user's sources? In the prototype, the user's `sources` is `[('ibus', 'emoji-picker'), ('xkb', 'us')]`. Section 2 says: *"each `('xkb', ID)` becomes `('ibus', 'emoji-picker:ID')` in place; ... the prototype's `('ibus', 'emoji-picker')` is dropped."* That works if `('xkb', 'us')` is still in `sources`, **unless** the user removed the redundant `('xkb', 'us')` while using the prototype (leaving only `[('ibus', 'emoji-picker')]`), in which case dropping `('ibus', 'emoji-picker')` leaves an empty list or no xkb layout to convert! Let's check `install.sh` to see what the prototype actually put in `sources`.
- **Lock screen / GDM password entry when only an `ibus` engine is in `sources` (`xkb` replaced in-place)**:
  Wait: when GNOME Shell locks the screen (or on login screen if user sources are read via AccountsService), how does GNOME Shell's lock screen handle input sources when `sources` has **no** `('xkb', ...)` entry and **only** `('ibus', 'emoji-picker:ID')` (e.g., `emoji-picker:de` or `emoji-picker:fr` on a non-US keyboard)? I will verify how GNOME Shell's `InputSourceManager` behaves on the lock screen when all sources are `ibus` engines.

Let's read [install.sh](file:///home/frank/.cache/ep-review-prod/r2/critic/install.sh).
Additional finding from comparing `install.sh` and `plan/PLAN.md`:

- **`ibus write-cache` vs user/system cache and prototype upgrade at login**:
  In `PLAN.md` Section 2 & 3, during prototype upgrade, `/usr/share/ibus/component/emoji-picker.xml` is immediately overwritten on disk without the old `emoji-picker` engine (it only has `emoji-picker:<layout>`), while the user's `org.gnome.desktop.input-sources sources` is **not** updated during `install.sh` because `ibus list-engine` does not yet know `emoji-picker:<layout>`.
  What happens when the user logs out and logs back in?
  1. `ibus-daemon` starts with the session and reads `/usr/share/ibus/component/emoji-picker.xml` (or rebuilds its cache). Now `ibus-daemon` knows `emoji-picker:us` (or `emoji-picker:de`), and **no longer knows `emoji-picker`**!
  2. If the user had only `[('ibus', 'emoji-picker')]` (e.g. they deleted the duplicate `('xkb', 'us')` in Settings while using the prototype to get rid of the top-bar indicator!), then:
     - During `install.sh` (prototype upgrade), Section 2 says: *"Install writes this user's registry file (their xkb layouts, plus any already converted)"*. Neither `('xkb', ID)` nor `('ibus', 'emoji-picker:ID')` is in `sources` if they only had `('ibus', 'emoji-picker')`! Even if they still had `[('ibus', 'emoji-picker'), ('xkb', 'de')]`, before `finish-setup` runs (or while `finish-setup` is polling), GNOME Shell sees `('ibus', 'emoji-picker')` as an unknown engine and skips it.
  3. Worse: what if a **second user** on the same machine was using the prototype (`('ibus', 'emoji-picker')`), and User 1 upgrades to v1.0? User 1's upgrade overwrites `/usr/share/ibus/component/emoji-picker.xml` and removes `emoji-picker` from it. User 2 never ran v1.0's `install.sh`, has no `finish-setup` autostart, and their `('ibus', 'emoji-picker')` engine silently breaks at their next login!

Let's read [uninstall.sh](file:///home/frank/.cache/ep-review-prod/r2/critic/uninstall.sh).
Additional findings from `tools/gsettings_lists.py`, `engine/emoji-picker.xml.in`, and `engine/engine.py`:

- **Prototype upgrade with a single source (`[('ibus', 'emoji-picker')]`) loses the user's keyboard layout on upgrade**:
  In `install.sh` (prototype), step 2 saved the layout into `/usr/share/ibus/component/emoji-picker.xml`'s `<layout>` tag, and step 3 prepended `('ibus', 'emoji-picker')` before `('xkb', '<layout>')`. Any prototype user who manually removed the second input source (`('xkb', '<layout>')`) in GNOME Settings to hide the top-bar keyboard indicator (the exact annoyance described in `PROBLEM.md` Decision #4!) now has `sources = [('ibus', 'emoji-picker')]`.
  When that user runs v1.0's `install.sh`:
  - Section 2 says: *"Install writes this user's registry file (their xkb layouts, plus any already converted)"* and *"Sources (and `mru-sources`, the same way): each `('xkb', ID)` becomes `('ibus', 'emoji-picker:ID')` in place; ... the prototype's `('ibus', 'emoji-picker')` is dropped. ... No xkb source at all: sources are left alone"*.
  - Wait: if the user had `[('ibus', 'emoji-picker')]` (no `xkb` source because they removed the duplicate in Settings, or even if they had `('ibus', 'emoji-picker')` whose layout was only stored in `/usr/share/ibus/component/emoji-picker.xml` or `~/.local/state/emoji-picker/backup/input-sources.txt`), the plan never reads the layout of `('ibus', 'emoji-picker')` from the existing `/usr/share/ibus/component/emoji-picker.xml` or `backup/input-sources.txt`! So either it sees "No xkb source at all" and leaves `[('ibus', 'emoji-picker')]` alone while deleting `emoji-picker` from `emoji-picker.xml` (causing GNOME to drop their only source on next login and reset a German/French user to US layout!), or if `finish-setup` drops `('ibus', 'emoji-picker')`, the user is left with an empty source list (which falls back to US layout).
- **Even with default prototype sources `[('ibus', 'emoji-picker'), ('xkb', 'de')]`, prototype upgrade breaks on login before `finish-setup` runs (and breaks `finish-setup` if `ibus-daemon` isn't restarted)**:
  Look at what happens during prototype upgrade in Section 2 & 3:
  1. `install.sh` overwrites `/usr/share/ibus/component/emoji-picker.xml` with `emoji-picker:de`, removing `emoji-picker`, and runs `ibus write-cache`.
  2. Wait: `install.sh` runs `ibus write-cache` **without `sudo`**! Let's check what `ibus write-cache` without `--system` (or without `sudo`) does vs with `sudo`!
     - `ibus write-cache` by default (`--system` is NOT default in `ibus write-cache`! Wait: let's check `ibus write-cache --help` or how IBus behaves: without `--system`, `ibus write-cache` writes `~/.cache/ibus/bus/registry`, whereas `ibus-daemon` checks `/var/cache/ibus/bus/registry` and `~/.cache/ibus/bus/registry`!). Even more importantly, in `PLAN.md` Section 5 (Uninstall step 5): *"With sudo: ... remove the component, ... then `ibus write-cache`."* If `ibus write-cache` is run under `sudo`, it writes `/root/.cache/ibus/bus/registry` unless `--system` is passed, or if run as the user, other users' `~/.cache/ibus/bus/registry` still has stale cached components if mtime checks don't invalidate it!

Let's inspect `bin/` and `emoji_picker/` files. First let's read `bin/emoji-picker`.
Additional finding from `emoji_picker/insert.py` and `emoji_picker/window.py`:

- **Misleading copy-fallback message when another IBus input method (e.g. Japanese) is active, or when a user starts their session on a second input source**:
  In `PLAN.md` Section 6: *"The copy fallback names the cause and the fix ("this keyboard has no emoji support yet: run the installer again"), or "until you log out" when finish-setup is pending."*
  Look at `emoji_picker/insert.py`: `preflight()` only checks `status()` from `engine.py` (`st is None` -> not running; `not st.get("enabled")` -> not active).
  - If a user has `[('ibus', 'emoji-picker:us'), ('ibus', 'anthy')]` and is currently typing in Japanese (`anthy`), `finish-setup` is not pending and `st.get("enabled")` is `False` (or `st is None` if `emoji-picker:us` has not been activated yet in this session!). Telling the user *"this keyboard has no emoji support yet: run the installer again"* is wrong and sends them into a loop of re-running `install.sh`.

Let's list the root directory to see all remaining files.
Additional findings on GNOME `XkbInfo` and `PLAN.md` Section 2 & 3:

- **Every login where `ibus-daemon` is slow (or fails) resets a non-US user's keyboard to US QWERTY**:
  `PLAN.md` Section 3 assumes the race where GNOME drops unknown IBus engines only happens on the *first* login after install (hence the one-shot `finish-setup` autostart that deletes itself).
  In reality (I **know** this from GNOME Shell's `js/ui/status/keyboard.js`), once `finish-setup` replaces `('xkb', 'de')` with `('ibus', 'emoji-picker:de')` and deletes itself, the user has **no** `('xkb', ...)` source left in `org.gnome.desktop.input-sources sources`. On **every subsequent login**, GNOME Shell's `InputSourceManager` skips all `'ibus'` sources until `ibus-daemon` finishes starting, enumerating engines, and signalling readiness. During that window (or permanently for the session if `ibus-daemon` hangs or fails), `sourcesList` is empty, so GNOME Shell activates its fallback layout (`'us'`). A German or French user typing right after a slow login gets a US layout.
- **`XkbInfo` display names and languages break for non-US layouts (`"German (German, with emoji)"` or `"Other"`)**:
  In `PLAN.md` Section 2:
  1. *"longname = the bracketed part of XkbInfo's display name plus ', with emoji', so the menu reads 'English (US, with emoji)'."*
     I **know** from `xkeyboard-config` and `GnomeDesktop.XkbInfo` that most base layouts (`de` -> `"German"`, `fr` -> `"French"`, `es` -> `"Spanish"`, `it` -> `"Italian"`, `ru` -> `"Russian"`) have **no parentheses** in their `XkbInfo` display name. Extracting "the bracketed part" either yields an empty string (`"German (, with emoji)"`) or falls back to the whole string (`"German (German, with emoji)"`) when GNOME Shell renders `IBus.get_language_name(language) (longname)`.
  2. *"`language` from GnomeDesktop.XkbInfo (`eng`, falling back to `other`)"*:
     I **know** from `libgnome-desktop` (`GnomeDesktop.XkbInfo`) that `get_layout_info(id)` does not return a language code; `get_languages_for_layout(layout)` takes a base layout (not `layout+variant`, so passing `de+nodeadkeys` returns `[]` -> `"other"`), and for multilingual country layouts like `ch+fr` ("French (Switzerland)") or `ca` ("French (Canada)"), the base layout `ch`'s first language is German (`deu`), producing `"German (Switzerland, with emoji)"`.

Let's check `probe/ibus` inside our working directory.
Additional findings from our analysis of `plan/PLAN.md` and `install.sh`:

- **Deleting the clone breaks adding a keyboard layout later (contradiction between Sections 1, 2, and 6)**:
  - "What the user will see" #1 (line 11): *"The clone can then be deleted."*
  - Section 1 (lines 29–32): Installs `/usr/local/bin/emoji-picker` and `/usr/local/bin/emoji-picker-uninstall`, plus `engine/engine.py`, `finish-setup`, `uninstall.sh`, `VERSION` in `/usr/local/lib/emoji-picker/versions/...`. **It does not install `install.sh` (or an `emoji-picker --setup` command) to `/usr/local/bin` or `/usr/local/lib/emoji-picker`.**
  - Section 2 (line 70) & Section 6 (line 134): *"Layouts added later in Settings stay plain until the installer is run again; the picker's copy message says that"* (`"this keyboard has no emoji support yet: run the installer again"`).
  - If the user deleted the clone as told in step 1 and later adds a layout in GNOME Settings, there is no installer left on the system to run.
- **Missing helper files in `/usr/local/lib/emoji-picker/versions/<version>-<commit>/` break `finish-setup` and `emoji-picker-uninstall` once the clone is deleted**:
  - Section 1's file table lists only: *"Python package, `engine/engine.py`, `finish-setup`, `uninstall.sh`, `VERSION`"*.
  - Both `finish-setup` (at next login) and `uninstall.sh` (when run via `/usr/local/bin/emoji-picker-uninstall` after the clone is deleted, especially when another user remains and it must *"regenerate the component from theirs"*) require the GSettings list parser/formatter (`tools/gsettings_lists.py`) and the XML component template/generator (`engine/emoji-picker.xml.in`).
- **Order of `sources` vs `mru-sources` updates drops the active layout in GNOME Shell**:
  - I **know** from GNOME Shell's `js/ui/status/keyboard.js` (`InputSourceSessionSettings`) that GNOME Shell listens to `changed::sources` and **not** `changed::mru-sources`; it reads `mru-sources` inside `_updateMruSources()` immediately when `sources` changes, and then writes its in-memory MRU list back to `mru-sources`.
  - In Sections 2, 3, and 5, if `sources` is updated before `mru-sources` (two separate `gsettings set` calls instead of writing `mru-sources` first or using `Gio.Settings.delay()`/`apply()`), GNOME Shell reacts to the `sources` write while `mru-sources` still contains the old tuple kind (`xkb` vs `ibus`), finds no match, resets the active layout to `sources[0]`, and overwrites `mru-sources`.
- **Re-running `./install.sh --shortcut '<Control><Alt>e'` after a default install permanently orphans `Super+.`**:
  - First run (`./install.sh`) removes `'<Super>period'` from `org.freedesktop.ibus.panel.emoji hotkey` and binds `<Super>period` to the custom shortcut.
  - Second run (`./install.sh --shortcut '<Control><Alt>e'`) switches the custom shortcut to `Ctrl+Alt+E` and *"leaves IBus's hotkey alone"*. Now neither emoji-picker nor IBus responds to `Super+.`, and if `installed.json` is updated for the new run, `emoji-picker-uninstall` will not restore `<Super>period` either.
- **`gsettings list-recursively` never checks existing custom keybindings**:
  - I **know** from GLib's `gio/gsettings-tool.c` that `gsettings list-recursively` (without a schema:path argument) skips relocatable schemas such as `org.gnome.settings-daemon.plugins.media-keys.custom-keybinding`. The conflict check in `install.sh` line 92 (`grep -v "custom-keybindings/emoji-picker"`) never actually inspects `custom0`, `custom1`, etc.

Let's read [docs/DESIGN.md](file:///home/frank/.cache/ep-review-prod/r2/critic/docs/DESIGN.md).
### 1. Where the plan fails or hurts a user (concrete setups & sequences)

#### A. German (`de`, `de+nodeadkeys`) or other non-US layouts (`fr`, `es`, `ch+fr`, `ca`)
1. **Broken input-source names (`"German (German, with emoji)"` or `"German (, with emoji)"`)**:
   - **Setup**: User has a standard German layout `('xkb', 'de')` (or `fr`, `es`, `it`, `nl`, `pl`, `ru`, `jp`).
   - **Sequence**: User runs `./install.sh` and logs out/in.
   - **What breaks**: Section 2 specifies: *"`longname` = the bracketed part of XkbInfo's display name plus ', with emoji', so the menu reads 'English (US, with emoji)'."*
   - **[KNOW]** In `xkeyboard-config` / `GnomeDesktop.XkbInfo`, `get_layout_info("us")` returns `display_name = "English (US)"`, which has parentheses. Almost all national base layouts (`"de"` → `"German"`, `"fr"` → `"French"`, `"es"` → `"Spanish"`, `"it"` → `"Italian"`, `"ru"` → `"Russian"`) have **no parentheses** in `display_name`.
   - **[KNOW]** Both GNOME Shell (`js/ui/status/keyboard.js`) and GNOME Settings (`panels/keyboard/cc-input-source-ibus.c`) format IBus engine labels as `IBus.get_language_name(language) (longname)`. When there are no brackets in `"German"`, extracting "the bracketed part" either returns `""` (producing **`"German (, with emoji)"`**) or falls back to the full display name (producing **`"German (German, with emoji)"`**).
2. **Variant layout (`de+nodeadkeys`) falls back to language `"other"` (`"Other (no dead keys, with emoji)"`)**:
   - **Setup**: User has `('xkb', 'de+nodeadkeys')`.
   - **What breaks**: Section 2 says: *"`language` from GnomeDesktop.XkbInfo (`eng`, falling back to `other`)"*.
   - **[KNOW]** `GnomeDesktop.XkbInfo.get_layout_info(id)` returns `(exists, display_name, short_name, xkb_layout, xkb_variant)` — it does **not** return a language code. To get a language code from `XkbInfo`, you must call `XkbInfo.get_languages_for_layout(layout_id)`, which in `libgnome-desktop` (`gnome-xkb-info.c`) looks up `priv->layouts_table` by **base layout** (`"de"`), not `layout+variant` (`"de+nodeadkeys"`). Passing `"de+nodeadkeys"` returns `[]`, falling back to `"other"`, so GNOME Shell displays **`"Other (no dead keys, with emoji)"`**.
3. **Multilingual country layouts (`ch+fr`, `ca`, `be`) get the wrong language name**:
   - **Setup**: User has French (Switzerland) `('xkb', 'ch+fr')` or French (Canada) `('xkb', 'ca')`.
   - **[KNOW]** `XkbInfo.get_languages_for_layout("ch")` returns ISO 639-2/3 codes in alphabetical order: `['deu', 'fra', 'ita', 'roh']` (and for `"ca"`: `['eng', 'fra', 'iku']`). Taking the first language code gives `deu` (`"German"`) for `ch+fr`, so GNOME Shell labels a French (Switzerland) keyboard **`"German (Switzerland, with emoji)"`**.

---

#### B. A login where IBus is slow (or `ibus-daemon` crashes/fails to start)
- **Setup**: User with a non-US layout (e.g. German `de` or French `fr`) has installed v1.0, logged out and in once so `finish-setup` replaced `('xkb', 'de')` with `('ibus', 'emoji-picker:de')` and deleted its autostart file. Now `sources` is permanently `[('ibus', 'emoji-picker:de')]` with **no** `('xkb', 'de')` entry.
- **Sequence**: On any subsequent login, the system is under load and `ibus-daemon` takes several seconds to start (or fails to start).
- **What breaks**: Section 3 assumes the "unknown IBus engine falls back to `us`" problem only exists on the *first* login after install.
- **[KNOW]** In GNOME Shell (`js/ui/status/keyboard.js` and `js/misc/ibusManager.js`), `InputSourceManager._inputSourcesChanged()` runs at session startup while `this._ibusReady` is `false`. While `!this._ibusReady`, GNOME Shell skips every `type === 'ibus'` source (`if (!this._ibusReady && type === INPUT_SOURCE_TYPE_IBUS) continue;`). Because the user no longer has an `('xkb', 'de')` source in `sources`, `infosList` is empty and GNOME Shell activates its fallback layout (`'us'`). Until `ibus-daemon` finishes starting, enumerating engines (`list_engines_async`), and registering `org.freedesktop.IBus.Panel` (`_initPanelService`), the user's keyboard is **US QWERTY instead of German QWERTZ / French AZERTY** (and stays `'us'` for the entire session if `ibus-daemon` fails).

---

#### C. Two layouts (e.g. `('xkb', 'us')` and `('xkb', 'de')`)
1. **Active layout in `mru-sources` is reset when `sources` is written before `mru-sources`**:
   - **Setup**: User has `sources = [('xkb', 'us'), ('xkb', 'de')]` and is currently using `de`, so `mru-sources = [('xkb', 'de'), ('xkb', 'us')]`.
   - **Sequence**: `install.sh`, `finish-setup`, or `uninstall.sh` updates `sources` and `mru-sources` using two `gsettings set` calls (`sources` first, `mru-sources` second, as written in Sections 2, 3, and 5: *"converts sources and mru-sources"*).
   - **What breaks**: **[KNOW]** GNOME Shell's `InputSourceSessionSettings` (`js/ui/status/keyboard.js`) connects to `changed::sources` and **never** connects to `changed::mru-sources`. The instant `gsettings set ... sources` runs, GNOME Shell's `_inputSourcesChanged()` → `_updateMruSources()` reads `mru-sources` (still containing `('xkb', ...)`), finds zero matches against the new `('ibus', 'emoji-picker:...')` entries in `sources`, activates `sources[0]` (`us` instead of `de`), and overwrites `mru-sources` in dconf. Even if `finish-setup` writes `mru-sources` a millisecond later, GNOME Shell ignores `changed::mru-sources` and keeps `us` active.
2. **Adding a second layout in Settings after deleting the clone**:
   - **Sequence**:
     1. User clones repo, runs `./install.sh`, and deletes the clone as explicitly invited in "What the user will see" #1 (*"The clone can then be deleted"*).
     2. Later, user adds a second layout in GNOME Settings -> Keyboard, switches to it, presses `Super+.`, and presses Enter.
     3. Picker copies the emoji and displays Section 6's message: **`"this keyboard has no emoji support yet: run the installer again"`**.
   - **What breaks**: Section 1 installs `/usr/local/bin/emoji-picker` and `/usr/local/bin/emoji-picker-uninstall`, and copies `engine/engine.py`, `finish-setup`, `uninstall.sh`, `VERSION` into `/usr/local/lib/emoji-picker/versions/...` — **it does not install `install.sh` (or an `emoji-picker --setup` subcommand)**. The user deleted the clone as told and has no installer to run.
3. **Unanchored `State.enabled` across multiple engine instances in `engine/engine.py`**:
   - **Setup**: User has `emoji-picker:us` and `emoji-picker:de` served by one `engine.py` process.
   - **What breaks**: **[KNOW]** In [engine.py](file:///home/frank/.cache/ep-review-prod/r2/critic/engine/engine.py#L74-L100), `do_focus_out` checks `if State.focused is self: State.focused = None`, whereas `do_disable` sets `State.enabled = False` unconditionally without checking whether `self` is the currently enabled engine instance. If `disable` on the old engine instance arrives after `enable` on the new instance, `State.enabled` becomes `False` while the new engine is active, causing `insert.preflight()` to fail with `"the emoji-picker keyboard is not the active input source"`.

---

#### D. An existing Japanese input method (`mozc-jp` / `anthy`)
1. **User with `[('ibus', 'emoji-picker:us'), ('ibus', 'mozc-jp')]` typing in Japanese**:
   - **Sequence**: User switches to Japanese (`mozc-jp`), presses `Super+.`, picks an emoji, and presses Enter.
   - **What breaks**: `insert.preflight()` fails (`st` is `None` if the user logged in with `mozc-jp` active, since **[KNOW]** `ibus-daemon` only spawns an engine's `<exec>` lazily when that engine is first activated; or `st.get("enabled")` is `False` if they switched from `emoji-picker:us` to `mozc-jp`). Because `finish-setup` is not pending, Section 6's copy fallback tells the user: **`"this keyboard has no emoji support yet: run the installer again"`**. Running the installer again changes nothing.
2. **User with ONLY `('ibus', 'mozc-jp')` (no `xkb` source at all, common because Mozc handles both Latin and Japanese modes)**:
   - **Sequence**: User runs `./install.sh`.
   - **What breaks**:
     - Under Section 2, the user has 0 `xkb` sources and 0 converted sources, so `/usr/local/lib/emoji-picker/users/<uid>` is empty, and `/usr/share/ibus/component/emoji-picker.xml` is generated with an empty `<engines/>` block.
     - Under Section 4, `install.sh` still strips `<Super>period` from IBus's emoji hotkey even though our engine will never be used.
     - Every time the user presses Enter in the picker, Section 6's message tells them `"this keyboard has no emoji support yet: run the installer again"`.

---

#### E. Upgrade from the prototype
1. **Prototype user who removed the duplicate `('xkb', ID)` source in GNOME Settings loses their keyboard layout**:
   - **Setup**: The prototype added `('ibus', 'emoji-picker')` in front of `('xkb', 'de')`, which made GNOME show the top-bar indicator (`PROBLEM.md` Decision #4). A prototype user who removed the redundant `('xkb', 'de')` in GNOME Settings has `sources = [('ibus', 'emoji-picker')]`.
   - **Sequence**: User runs v1.0 `./install.sh` and logs out/in.
   - **What breaks**: Section 2 reads only *"their xkb layouts, plus any already converted"* (`emoji-picker:ID`), never inspecting the existing `/usr/share/ibus/component/emoji-picker.xml`'s `<layout>` tag or `~/.local/state/emoji-picker/backup/input-sources.txt`. It removes `<name>emoji-picker</name>` from `emoji-picker.xml` and drops `('ibus', 'emoji-picker')` from `sources`. On next login, the user's German layout is gone and GNOME falls back to `'us'`.
2. **Prototype user with default `[('ibus', 'emoji-picker'), ('xkb', 'de')]` if `finish-setup` times out or before it runs**:
   - **Sequence**: During `./install.sh`, `/usr/share/ibus/component/emoji-picker.xml` is immediately overwritten on disk **without** `<name>emoji-picker</name>`, while `sources` is left untouched until `finish-setup` runs at next login.
   - **What breaks**: At next login, `ibus-daemon` loads the new `emoji-picker.xml` (which no longer defines `emoji-picker`) *before* XDG autostart runs `finish-setup`. If `finish-setup` fails or is slow, `('ibus', 'emoji-picker')` is already invalid.

---

#### F. A second user on the machine
1. **User 1 installs; User 2 never installed emoji-picker**:
   - **What breaks**:
     - `/usr/local/share/applications/io.github.remco28.EmojiPicker.desktop` is system-wide, so **"Emoji Picker" appears in User 2's GNOME App Grid**. When User 2 opens it and presses Enter, it tells User 2: *"this keyboard has no emoji support yet: run the installer again"*.
     - `/usr/share/ibus/component/emoji-picker.xml` is system-wide, so User 1's `English (US, with emoji)` / `German (..., with emoji)` engines appear in User 2's GNOME Settings -> Keyboard -> Add Input Source. If User 2 adds one there (which creates no `/usr/local/lib/emoji-picker/users/<uid_2>`) and User 1 later runs `emoji-picker-uninstall`, User 1's uninstall deletes `emoji-picker.xml` and breaks User 2's keyboard.
2. **User 1 upgrades from the prototype; User 2 also had the prototype**:
   - **What breaks**: User 1's v1.0 `./install.sh` removes `<name>emoji-picker</name>` from `/usr/share/ibus/component/emoji-picker.xml`. User 2 has no `/usr/local/lib/emoji-picker/users/<uid_2>` and no `finish-setup` autostart, so User 2's `('ibus', 'emoji-picker')` breaks on User 2's next login.
3. **User 1 uninstalls via `emoji-picker-uninstall` (after deleting the clone) while User 2 still has it installed**:
   - **What breaks**: Section 5 step 5 says: *"If others remain, regenerate the component from theirs"*. Section 1's file table copies only *"Python package, `engine/engine.py`, `finish-setup`, `uninstall.sh`, `VERSION`"* into `/usr/local/lib/emoji-picker/versions/<version>-<commit>/` — **neither `tools/gsettings_lists.py` nor `engine/emoji-picker.xml.in` is in that list**. Once the clone is deleted, both `emoji-picker-uninstall` and `finish-setup` are missing the template and GSettings helper unless they are moved into `emoji_picker/`.

---

#### G. Re-running `./install.sh`
1. **Re-running `./install.sh --shortcut '<Control><Alt>e'` after a default `./install.sh` permanently kills `Super+.`**:
   - **Sequence**:
     1. User runs `./install.sh` (removes `'<Super>period'` from `org.freedesktop.ibus.panel.emoji hotkey`, records that in `installed.json`, binds `<Super>period` to our shortcut).
     2. User decides they prefer `Ctrl+Alt+E` and runs `./install.sh --shortcut '<Control><Alt>e'`.
   - **What breaks**: Section 4 says: *"`./install.sh --shortcut '<Control><Alt>e'` picks another key and leaves IBus's hotkey alone."* It does **not** put `'<Super>period'` back into `org.freedesktop.ibus.panel.emoji hotkey` when switching away from `<Super>period`. Worse, if `installed.json` is overwritten with the new shortcut state, `emoji-picker-uninstall` will never restore `'<Super>period'` to IBus either.
2. **Re-running `./install.sh` on the same `<version>-<commit>` breaks atomic upgrade and risks deleting the live directory**:
   - **Sequence**: User runs `./install.sh` again from the same git commit (e.g. after adding a keyboard layout in Settings).
   - **What breaks**: Section 1 puts files in `/usr/local/lib/emoji-picker/versions/<version>-<commit>/`, which is **already** the target of `/usr/local/lib/emoji-picker/current`. Writing into the existing `<version>-<commit>` directory modifies the live installation in place (not atomic), and version cleanup (*"The previous version directory is kept; older ones are removed"*) must handle `old_target == new_target`.
3. **Re-running `./install.sh` after adding plain `de` when `de+nodeadkeys` was already installed**:
   - **Sequence**: User had `de+nodeadkeys` installed (`emoji-picker:de+nodeadkeys` is in `ibus list-engine`), adds plain `de` in GNOME Settings, and runs `./install.sh`.
   - **What breaks**: If `install.sh` checks `ibus list-engine` with a substring match like `grep -q "emoji-picker:$ID"` (as prototype [install.sh](file:///home/frank/.cache/ep-review-prod/r2/critic/install.sh#L103) does), `"emoji-picker:de"` matches `"emoji-picker:de+nodeadkeys"`. `install.sh` then converts `('xkb', 'de')` to `('ibus', 'emoji-picker:de')` immediately even though the running `ibus-daemon` does not have `emoji-picker:de`, and GNOME Shell immediately drops the `de` source.

---

#### H. Uninstall after the user changed settings (or cancelled `sudo`)
1. **User cancels or fails `sudo` during `emoji-picker-uninstall`**:
   - **Sequence**: User runs `emoji-picker-uninstall` and hits Ctrl+C or fails the password prompt at Step 5.
   - **What breaks**: In Section 5, Steps 1–4 run *before* `sudo` in Step 5. The user's `sources`, shortcut, IBus hotkey, and autostart are already removed, while `/usr/local/lib/emoji-picker/users/<uid>`, `/usr/share/ibus/component/emoji-picker.xml`, and `/usr/local/bin/emoji-picker*` remain installed.
2. **User re-added plain `('xkb', 'us')` in Settings alongside `('ibus', 'emoji-picker:us')`, then uninstalls**:
   - **What breaks**: Step 1 converts `('ibus', 'emoji-picker:us')` back to `('xkb', 'us')` in place. Without deduplication, `sources` becomes `[('xkb', 'us'), ('xkb', 'us')]`.
3. **User deleted the custom shortcut in GNOME Settings before uninstalling**:
   - **What breaks**: **[KNOW]** Deleting a custom shortcut in `gnome-control-center` resets `name`, `command`, and `binding` at that dconf path to `''`. Section 5 step 2 says: *"removed when its name is 'Emoji Picker' and its command is ours ... Otherwise left, with a message"*, which prints a bogus warning that a foreign shortcut is at that path when `name` is simply `''`.

---

#### I. Rapid second invocation (`Super+.` right after Enter or `Ctrl+C`) closes the newly opened window
- **Sequence**: User presses `Super+.`, presses Enter (or `Ctrl+C`), and within 150 ms–2,000 ms (for Enter, while `Inserter` polls) or 1,500 ms (for `Ctrl+C`, `close_after_ms=1200` + `300` ms quit timer) presses `Super+.` again.
- **What breaks**: **[KNOW]** In [__main__.py](file:///home/frank/.cache/ep-review-prod/r2/critic/emoji_picker/__main__.py#L40-L41) and [window.py](file:///home/frank/.cache/ep-review-prod/r2/critic/emoji_picker/window.py#L482-L551), `Adw.Application` is single-instance (`DEFAULT_FLAGS`). During insertion (`self.set_visible(False)`) or post-copy delay, the first process still owns `io.github.remco28.EmojiPicker` on D-Bus and its `PickerWindow` is still in `app.get_windows()`. Pressing `Super+.` activates the first process, which calls `app.get_windows()[0].present()` on the window that is in `mode = "inserting"` or `"copied"`, and milliseconds later `_inserted()` or the copy timer calls `app.quit()`, closing the window in the user's face.

---

### 2. Design decisions that are wrong or will not work as described on Ubuntu 26.04 / GNOME 50 Wayland / IBus 1.5.34

| Rating | Design Decision | Why it is wrong / how the platform actually behaves |
|---|---|---|
| **HIGH** | **Replacing all `('xkb', ID)` sources in place with `('ibus', 'emoji-picker:ID')` + one-shot `finish-setup` (Sections 2 & 3)** | **[KNOW]** GNOME Shell's `InputSourceManager` (`js/ui/status/keyboard.js`) skips all `'ibus'` sources whenever `!this._ibusReady` (on every login until `ibus-daemon` starts, enumerates engines, and registers the panel service, or whenever `ibus-daemon` crashes). With no `('xkb', ID)` source left in `sources`, GNOME Shell falls back to `'us'` during every slow login or IBus failure. **[BELIEVE]** On GDM's login screen (which reads user `InputSources` via `AccountsService` where third-party IBus engines do not run), having only `('ibus', 'emoji-picker:de')` can also cause the greeter password prompt to fall back to the system default layout instead of the user's layout. |
| **HIGH** | **`XkbInfo` `longname` and `language` construction in Section 2** | **[KNOW]** (1) `XkbInfo.get_layout_info(id)` has no bracketed substring for most non-English layouts (`"German"`, `"French"`, `"Spanish"`), producing `"German (German, with emoji)"` or `"German (, with emoji)"`. (2) `XkbInfo.get_languages_for_layout()` takes a base layout (`"de"`), not `"de+nodeadkeys"` (which returns `[]` → `"other"`). (3) For multilingual country layouts (`ch+fr`, `ca`), `get_languages_for_layout(base)[0]` is alphabetical (`deu` for `ch`, `eng` for `ca`), mislabelling the language. |
| **HIGH** | **Dropping `<name>emoji-picker</name>` from `emoji-picker.xml` during prototype upgrade before `finish-setup` runs, and ignoring prototype layouts when no `xkb` source remains (Sections 2 & 3)** | **[KNOW]** If a prototype user removed the duplicate `('xkb', ID)` source in Settings (leaving `[('ibus', 'emoji-picker')]`), or if a second user on the machine is still on the prototype, or before `finish-setup` completes at next login, removing `emoji-picker` from `/usr/share/ibus/component/emoji-picker.xml` causes GNOME Shell to drop the unknown source and reset the keyboard to `'us'`. |
| **HIGH** | **Telling users to delete the clone while requiring `install.sh` to be re-run when layouts are added, and omitting `gsettings_lists.py` / `emoji-picker.xml.in` from `/usr/local/lib/emoji-picker` (Sections 1, 2, 5, 6)** | **[KNOW]** Deleting the clone leaves no installer on disk for Section 2/6's `"run the installer again"` workflow, and if `tools/gsettings_lists.py` and `engine/emoji-picker.xml.in` are not installed into `/usr/local/lib/emoji-picker/versions/...` (or folded into `emoji_picker`), both `finish-setup` and `emoji-picker-uninstall` fail once the clone is deleted. |
| **MEDIUM** | **Non-atomic updates of `sources` and `mru-sources` (Sections 2, 3, 5)** | **[KNOW]** GNOME Shell listens to `changed::sources` and not `changed::mru-sources`, and immediately rewrites `mru-sources` inside `_inputSourcesChanged()`. Running `gsettings set ... sources` before `gsettings set ... mru-sources` wipes out the active MRU layout for multi-layout users. You must either write `mru-sources` *before* `sources` or apply both in one dconf change-set (`Gio.Settings.delay()` + `apply()`). |
| **MEDIUM** | **Running `ibus write-cache` under `sudo` without `--system` (Section 5 step 5)** | **[KNOW]** In IBus 1.5.34 (`tools/main.vala`), `ibus write-cache` defaults to `system = false` (`~/.cache/ibus/bus/registry`). Under `sudo`, `HOME` is `/root`, so `sudo ibus write-cache` writes `/root/.cache/ibus/bus/registry` and updates neither `/var/cache/ibus/bus/registry` (`--system`) nor the user's `~/.cache/ibus/bus/registry`. Furthermore, `ibus-daemon` automatically checks directory/file `st_mtime` on `/usr/share/ibus/component` at startup (`bus/registry.c`) and rebuilds the user's cache anyway. |
| **MEDIUM** | **Checking shortcut conflicts via `gsettings list-recursively` (Section 4 & `install.sh` line 92)** | **[KNOW]** In GLib (`gio/gsettings-tool.c`), `gsettings list-recursively` with no arguments skips relocatable schemas (`org.gnome.settings-daemon.plugins.media-keys.custom-keybinding`). It never inspects existing custom shortcuts (`custom0`, `custom1`, etc.). |
| **MEDIUM** | **Single copy-fallback message blaming missing layout setup (Section 6)** | **[KNOW]** `preflight()` fails both when an unconfigured `xkb` layout is active *and* when another IBus engine (e.g. `mozc-jp`) is active. Telling a user typing in Japanese to `"run the installer again"` is wrong; the picker can read `org.gnome.desktop.input-sources` / current engine to distinguish an unconverted `xkb` layout from another IBus IME. |
| **LOW** | **`#!/usr/bin/python3 -I` on helper scripts (Section 1)** | **[KNOW]** In Python 3.14, `-I` removes the script's own directory from `sys.path[0]`. Any script under `/usr/local/lib/emoji-picker/current/` (`finish-setup`, `engine.py`, `uninstall.sh` helpers) that imports from `emoji_picker` or a sibling file will fail with `ModuleNotFoundError` unless it explicitly inserts the directory onto `sys.path`. |

---

### 3. Can anything leave the user's system worse than before they installed, with no clear way back?

Yes — three specific paths can leave a user with a broken keyboard layout or broken `Super+.` and no obvious recovery:

1. **Prototype user who removed the duplicate `xkb` source in GNOME Settings upgrades to v1.0**:
   - Before v1.0 install: `sources = [('ibus', 'emoji-picker')]`, working with their German/French layout stored in `/usr/share/ibus/component/emoji-picker.xml`.
   - After v1.0 install + logout/login: `emoji-picker.xml` was overwritten without `emoji-picker`, `users/<uid>` is empty, and GNOME falls back to `'us'`. Even running `emoji-picker-uninstall` puts back `'us'` (Step 1: *"never an empty list (`us`)"*) because their layout was only in the overwritten `/usr/share/ibus/component/emoji-picker.xml` (or in `~/.local/state/emoji-picker/backup/input-sources.txt`, which Section 5's uninstaller never reads!).
2. **Running `./install.sh` and then `./install.sh --shortcut '<Control><Alt>e'`**:
   - The first run removes `'<Super>period'` from `org.freedesktop.ibus.panel.emoji hotkey`.
   - The second run leaves `org.freedesktop.ibus.panel.emoji hotkey` without `'<Super>period'` and updates `installed.json` to record the `<Control><Alt>e` shortcut.
   - Running `emoji-picker-uninstall` afterwards sees that the installed shortcut was `<Control><Alt>e` and does not restore `'<Super>period'` to `org.freedesktop.ibus.panel.emoji hotkey`. The user's built-in `Super+.` emoji shortcut is permanently gone unless they manually run `gsettings reset org.freedesktop.ibus.panel.emoji hotkey` or find `~/.local/state/emoji-picker/backup/ibus-emoji-hotkey.txt`.
3. **Second user on a shared machine where User 1 upgrades from the prototype (or where User 2 selected an `emoji-picker:ID` source in GNOME Settings and User 1 uninstalls)**:
   - User 2 never ran v1.0's installer, has no `~/.local/state/emoji-picker/backup/`, and loses their input source at next login when User 1 modifies or deletes `/usr/share/ibus/component/emoji-picker.xml`.

---

### 4. What I would cut without losing the goal

1. **Cut the multi-version retention scheme (`/usr/local/lib/emoji-picker/versions/<version>-<commit>/` + `current` symlink + keeping N-1 versions)**:
   - **[KNOW]** A running Python process (`engine.py`) has already loaded its bytecode into memory at startup (`engine.py` has no lazy imports and reads no files from `/usr/local/lib/emoji-picker` after startup). The picker (`emoji-picker`) starts a fresh process on each `Super+.` press.
   - Installing directly into `/usr/local/lib/emoji-picker/` (staging to `/usr/local/lib/emoji-picker.new` and `mv -T` / swapping once) is simpler, cannot misbehave on same-commit re-runs, and eliminates version-directory pruning bugs.
2. **Cut the `XkbInfo` bracket-parsing heuristic for `longname` and `language` lookup**:
   - Instead of parsing brackets out of `XkbInfo` display names (which fails on `"German"`, `"French"`, `"ch+fr"`, `"de+nodeadkeys"`), set `<language>other</language>` (or look up the base layout `id.partition('+')[0]` in `XkbInfo.get_languages_for_layout` only when single-language) and use `XkbInfo`'s full `display_name` directly when it has no parens, or even simpler: since the top-bar indicator is **hidden** when the user has one input source, and uses `<symbol>` (`short_name`, e.g. `en`, `de`, `fr`) in the top bar when they have multiple sources, make sure `longname` never duplicates `IBus.get_language_name(language)`.
3. **Make `/usr/local/bin/emoji-picker` (or `emoji-picker --setup`) able to refresh layouts without the git clone**:
   - Instead of telling users to *"run the installer again"* from a git clone you told them they could delete, ship the setup logic inside the installed `/usr/local/lib/emoji-picker/` tree so `emoji-picker --setup` (or re-running `/usr/local/lib/emoji-picker/install.sh`) works after the clone is deleted.

