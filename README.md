# emoji-picker

A fast, reliable emoji picker for Linux (Wayland + GNOME first). Emoji only.

**Status: research probe, not a picker yet.** The hard part is not the
window, it is getting an emoji into the app you were typing in without
stray characters or a clobbered clipboard. Before building, this repo tests
which insertion route actually works on a real Wayland GNOME desktop.

## Routes under test

| Route | Skips the clipboard | Needs |
|---|---|---|
| Input method (a passive IBus engine commits the text) | yes | one file in `/usr/share/ibus/component` |
| RemoteDesktop portal pastes for you | no | a one-time permission dialog |
| Copy only | no | nothing |

The eventual picker will pick the best available route at startup and fall
back down this list.

## Try it

Open `human_feedback/round-2026-11-03-insertion-probe/index.html` in a
browser and follow it. The short version, from `probe/`:

```
./env-report.sh              # read-only report of your system
python3 ibus/selftest.py     # headless engine test, private IBus, no sudo
./setup.sh install           # engine + Ctrl+Alt+1/2/3 test shortcuts (sudo once)
./setup.sh uninstall         # restores your input sources and shortcuts
```

## Findings so far

- IBus only loads a custom engine from `/usr/share/ibus/component` (or
  `IBUS_COMPONENT_PATH`). Per-user data dirs are ignored, so an IBus-based
  picker needs a system install, realistically a `.deb`.
- A per-context `set_engine` does not start an engine; the global-engine
  switch GNOME uses does.
- With no app focused, IBus parks the engine on an internal context and
  still accepts commits, which are then dropped. "Accepted" is not
  "delivered", so timing after the picker closes is the main risk.
- Headless on Ubuntu 24.04 (IBus 1.5.29): commits of simple, skin-tone and
  ZWJ-family emoji arrive intact, 20 ms after focus returns. Real apps on
  Wayland are untested; that is what the probe is for.
