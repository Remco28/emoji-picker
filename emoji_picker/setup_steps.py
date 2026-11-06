"""Per-user steps that run outside the picker window.

`finish_setup()` runs once at login after an install (from an autostart
entry): it waits for IBus to know our engines, then switches the user's
keyboard sources to them. `doctor()` prints what is installed and active,
for bug reports. Neither needs GTK.
"""
import json
import os
import subprocess
import sys
import time

from . import __version__
from . import system

APP_ID = "io.github.remco28.EmojiPicker"
SRC_SCHEMA = "org.gnome.desktop.input-sources"
KB_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
KB_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/emoji-picker/"
HOTKEY_SCHEMA = "org.freedesktop.ibus.panel.emoji"


def state_dir():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "emoji-picker")


def autostart_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "autostart", f"{APP_ID}.finish-setup.desktop")


def setup_pending():
    return os.path.exists(autostart_path())


def log(msg):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        with open(os.path.join(state_dir(), "setup.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def gsettings(*args):
    r = subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(f"gsettings {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def ibus_engines():
    """Engine names the running ibus-daemon knows, or None when it is not up."""
    try:
        r = subprocess.run(["ibus", "list-engine"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return system.listed_engines(r.stdout)


def convert_now(known):
    """Switch sources and mru-sources to our engines IBus knows. Returns the
    new sources, or None when nothing changed."""
    changed = None
    for key in ("sources", "mru-sources"):
        before = system.parse(gsettings("get", SRC_SCHEMA, key))
        after = system.convert(before, known)
        if after != [tuple(x) for x in before]:
            gsettings("set", SRC_SCHEMA, key, system.fmt_sources(after))
            if key == "sources":
                changed = after
    return changed


def notify(summary, body):
    try:
        subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
                        "--object-path", "/org/freedesktop/Notifications", "--method",
                        "org.freedesktop.Notifications.Notify", "Emoji Picker", "0", APP_ID,
                        summary, body, "[]", "{}", "10000"],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def finish_setup(wait_s=None, poll_s=0.5):
    """Exit status 0 when done (or nothing to do), 1 when IBus never listed our engines."""
    if wait_s is None:  # the environment override is for tests
        wait_s = float(os.environ.get("EMOJI_PICKER_SETUP_WAIT", "60"))
    deadline = time.monotonic() + wait_s
    known = None
    while True:
        engines = ibus_engines()
        if engines is not None:
            known = {e for e in engines if e.startswith(system.PREFIX)}
            if known:
                break
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_s)
    if not known:
        log(f"finish-setup: IBus did not list our engines within {wait_s:.0f} s "
            f"({'IBus not reachable' if engines is None else 'none listed'}); will retry next login")
        marker = os.path.join(state_dir(), "finish-setup-notified")
        if not os.path.exists(marker):
            notify("Emoji Picker setup is not finished",
                   "The emoji keyboard did not load. It will try again at your next login; "
                   "run 'emoji-picker --doctor' to see why.")
            try:
                os.makedirs(state_dir(), exist_ok=True)
                open(marker, "w").close()
            except OSError:
                pass
        return 1
    try:
        changed = convert_now(known)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as e:
        log(f"finish-setup: could not change input sources: {e}")
        return 1
    log(f"finish-setup: done; sources {'now ' + system.fmt_sources(changed) if changed else 'unchanged'}")
    for path in (autostart_path(), os.path.join(state_dir(), "finish-setup-notified")):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    return 0


def _tail(path, n=8):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except OSError:
        return []


def doctor(out=sys.stdout):
    def p(label, value):
        print(f"{label:<22} {value}", file=out)

    def safe(fn):
        try:
            return fn()
        except Exception as e:  # a report must not stop at the first broken part
            return f"(error: {e})"

    pkg = os.path.dirname(os.path.abspath(__file__))
    p("version", f"{__version__} from {pkg}")
    p("input sources", safe(lambda: gsettings("get", SRC_SCHEMA, "sources")))
    engines = ibus_engines()
    p("IBus", "not reachable" if engines is None else "running")
    if engines is not None:
        ours = sorted(e for e in engines if e.startswith(system.PREFIX))
        p("emoji engines known", ", ".join(ours) or "none (log out and back in after installing)")
        r = subprocess.run(["ibus", "engine"], capture_output=True, text=True, timeout=10)
        p("active engine", r.stdout.strip() or r.stderr.strip())
    from . import insert
    p("engine status", insert.status() or "not reachable (no emoji keyboard has been active yet)")
    p("setup pending", "yes, finishes at next login" if setup_pending() else "no")
    p("IBus emoji hotkey", safe(lambda: gsettings("get", HOTKEY_SCHEMA, "hotkey")))
    for key in ("name", "binding", "command"):
        p(f"shortcut {key}", safe(lambda k=key: gsettings("get", f"{KB_SCHEMA}.custom-keybinding:{KB_PATH}", k)))
    try:
        with open(os.path.join(state_dir(), "installed.json"), encoding="utf-8") as f:
            p("installed.json", json.dumps(json.load(f)))
    except (OSError, ValueError):
        p("installed.json", "none")
    for name in ("setup.log", "picker.log", "engine.log"):
        lines = _tail(os.path.join(state_dir(), name))
        print(f"\n--- last lines of {name}", file=out)
        for line in lines:
            print("  " + line.rstrip(), file=out)
    return 0
