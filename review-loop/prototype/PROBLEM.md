# The problem: a better emoji picker for Ubuntu (Wayland + GNOME)

## Who it is for, and what is wrong today

Frank uses Ubuntu 26.04.1 LTS, GNOME Shell 50.1, Wayland, IBus 1.5.34,
Python 3.14, on a ThinkPad X1 Yoga Gen 6, US keyboard layout. Today he presses
Super+. which starts IBus's built-in emoji typing: an underlined "e" appears in
the text field, he presses Space to get choices. He finds it unreliable to
open, without useful search, and it leaves stray characters behind.

## What he decided (in his words where quoted)

1. Emoji only. No kaomoji, GIFs or symbols.
2. "I want a big list/chart that gives me a reasonable amount of options to
   express myself with. I want to narrow it down quickly as I type. It should
   definitely be keyboard first, mouse second." Being able to press Enter
   instead of clicking "is a must".
3. Features wanted now: recents, frequency, search by meaning, shortcodes,
   variants (skin tones etc.). "Nothing else is that appealing right now."
   Explicitly not wanted now: suggestions while typing in other apps,
   classroom/safe mode, saved "people" profiles, team/brand sets.
4. User story: "User presses a shortcut, a popup with recent emojis, frequent
   emojis, and a small input box where I can type 'american flag happy' and it
   shows an American flag and a happy emoji. It will also show closely
   matching ones."
5. Second story: typing a sentence such as "my dog went to the vet and it
   isn't looking good, please pray for him" should show relevant emoji (dog,
   hospital, prayer hands, church, and so on).
6. No LLM calls at runtime ("overkill"; revisit when local inference is
   everywhere). No embedding model running just to find emoji. Instead: do the
   "meaning" work once at build time (for example, have an LLM write richer
   search keywords per emoji) and ship a plain data file; runtime search is
   plain keyword search. He likes this and wants the enrichment tested first,
   because it is what makes this better than what Ubuntu ships.
7. While it is being built it runs on its own shortcut; it replaces Super+.
   later.
8. Deliverable now: a working prototype, built end to end.

## Facts already established (measured, not assumed)

On Frank's machine (probe round, 2026-11-05):

- A passive IBus engine (passes every key through, commits text when another
  process asks over a Unix socket) inserted all of 😀 👍🏽 ❤️ 👨‍👩‍👧‍👦 🏳️‍🌈 🇨🇦
  intact into real apps on Wayland, including the terminal, with no stray
  characters. Flow: picker window opened by a GNOME custom shortcut (a new
  process each time), user clicked an emoji, the window hid, after 150 ms the
  picker asked the engine to commit; it succeeded on the first retry
  (<= 50 ms later). Typing in his US layout was unaffected while that engine
  was the selected input source.
- Clipboard + simulated Ctrl+V via the RemoteDesktop portal worked in apps
  (one-time permission dialog titled as a remote desktop / share request) but
  not in the terminal (terminals paste with Ctrl+Shift+V).
- Copy-only worked; the clipboard kept the emoji after the window closed.
- After the probe's install/uninstall (which ran `ibus restart`), his Super+.
  stopped working until he logged out and back in.

On the development machine (Ubuntu 24.04, X11, IBus 1.5.29), confirmed again
on Frank's machine by a headless self-test:

- IBus only loads a custom engine from `/usr/share/ibus/component` (or
  `IBUS_COMPONENT_PATH`, which GNOME does not set). Per-user data dirs are
  ignored. So installing an engine needs sudo once.
- The engine is spawned when it becomes the *global* engine (what GNOME does
  when the input source is selected), not by a per-context set_engine.
- When no app has focus, IBus attaches the engine to an internal "fake" input
  context: the engine still sees focus_in and a commit is accepted and then
  silently dropped. "Accepted" does not mean "delivered".

Search spike (development machine, untuned, scratch deleted):

- Plain keyword matching on emojibase labels and tags: "american flag happy"
  gave American Samoa's flag, an american football and mailboxes; "vet" gave
  nothing. Fast (under 10 ms), but not good enough.
- A local embedding model got the US flag right but missed inference (vet
  gave a poodle and a rat, not a hospital) and is ruled out at runtime anyway
  (decision 6).

## Materials available

- Emoji data: `emojibase-data` 18.0.0 (MIT; derived from Unicode CLDR):
  1958 entries with label, tags, group, order, Unicode version, skin-tone
  variants (single tone 1-5, or a pair of tones for two-person emoji), and
  shortcode sets (github, cldr, emojibase, iamcal, joypixels); about 20
  languages.
- Python 3 with PyGObject, GTK 4 and libadwaita are installed on Frank's
  machine. Noto Color Emoji is the emoji font.
- The development machine has Xvfb, so a GTK window can be run and
  screenshotted headlessly; it cannot test Wayland behaviour or Frank's apps.
- An LLM is available at build time on the development machine through the
  `claude -p` command line (no API key).
