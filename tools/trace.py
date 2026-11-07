"""Check on a real computer that uninstalling leaves no trace.

    /usr/bin/python3 -I tools/trace.py snapshot DIR    save your settings and file lists to DIR
    /usr/bin/python3 -I tools/trace.py compare A B     what changed from snapshot A to snapshot B
    /usr/bin/python3 -I tools/trace.py leftovers       anything of emoji-picker's still here

A snapshot holds every GNOME setting you have changed from its default
(`dconf dump /`), the file lists of the folders an install can touch, and the
input engines IBus knows. It stays on this computer. `compare` prints only the
differences; your emoji history in ~/.local/state/emoji-picker is kept on
purpose and shown apart. Exit status: 0 when nothing unexpected differs.
"""
import json
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or f"{HOME}/.local/state", "emoji-picker")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or f"{HOME}/.cache", "emoji-picker")
CONFIG = os.environ.get("XDG_CONFIG_HOME") or f"{HOME}/.config"
APP_ID = "io.github.remco28.EmojiPicker"

# (folder, how deep to list it); None lists everything below it
FOLDERS = [
    ("/usr/local", None),
    ("/usr/share/ibus/component", None),
    (CONFIG, 1), (f"{CONFIG}/autostart", None),
    (f"{HOME}/.cache", 1),
    (f"{HOME}/.local/share", 1), (f"{HOME}/.local/share/applications", None),
    (f"{HOME}/.local/state", 1), (STATE, None),
]
SKIP = ("/usr/local/lib/python3",)   # pip packages: big, and not ours

# settings the installer changes: (schema, key)
KEYS = [
    ("org.gnome.desktop.input-sources", "sources"),
    ("org.gnome.desktop.input-sources", "mru-sources"),
    ("org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"),
    ("org.freedesktop.ibus.panel.emoji", "hotkey"),
]
BACKUP_FILES = {"sources": "input-sources.txt", "mru-sources": "mru-sources.txt",
                "custom-keybindings": "custom-keybindings.txt", "hotkey": "ibus-emoji-hotkey.txt"}


def out(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def settings_lines():
    """`dconf dump /` as one sorted line per key: /path/key=value."""
    lines, group = [], ""
    for line in out("dconf", "dump", "/").splitlines():
        if line.startswith("[") and line.endswith("]"):
            group = "/" + line[1:-1].strip("/") + "/"
            if group == "//":
                group = "/"
        elif "=" in line:
            lines.append(group + line)
    return sorted(lines)


def file_lines():
    lines = set()
    for top, depth in FOLDERS:
        if not os.path.isdir(top):
            continue
        base = top.rstrip("/").count("/")
        for dp, dns, fns in os.walk(top):
            if dp.startswith(SKIP):
                dns[:] = []
                continue
            level = dp.rstrip("/").count("/") - base + 1
            for n in dns + fns:
                p = os.path.join(dp, n)
                lines.add(p + ("/" if os.path.isdir(p) and not os.path.islink(p) else ""))
            if depth is not None and level >= depth:
                dns[:] = []
    return sorted(lines)


def engine_lines():
    return sorted(line.split(" - ")[0].strip() for line in out("ibus", "list-engine").splitlines()
                  if line.startswith("  "))


def snapshot(folder):
    os.makedirs(folder, exist_ok=True)
    parts = {"settings.txt": settings_lines(), "files.txt": file_lines(), "engines.txt": engine_lines()}
    for name, lines in parts.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print(f"saved {folder}: " + ", ".join(f"{len(v)} {k[:-4]}" for k, v in parts.items()))
    if not parts["settings.txt"]:
        print("WARNING: `dconf dump /` printed nothing; is dconf-cli installed?")


def read(folder, name):
    try:
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            return [line for line in f.read().splitlines() if line]
    except OSError:
        return []


def compare(a, b):
    unexpected = 0
    for name, title in (("settings.txt", "Settings"), ("files.txt", "Files and folders"),
                        ("engines.txt", "IBus input engines")):
        before, after = read(a, name), read(b, name)
        gone = [x for x in before if x not in set(after)]
        new = [x for x in after if x not in set(before)]
        kept = [x for x in new + gone if x.startswith(STATE + "/")]
        # IBus keeps the engines it loaded at login until the next one; the
        # file list shows whether the engine file itself is gone
        session = [x for x in new if name == "engines.txt" and x.startswith("emoji-picker")]
        gone = [x for x in gone if x not in kept]
        new = [x for x in new if x not in kept and x not in session]
        print(f"== {title}: " + ("no change" if not (gone or new) else f"{len(gone) + len(new)} changed"))
        for x in gone:
            print(f"  - {x}")
        for x in new:
            print(f"  + {x}")
        if kept:
            print(f"  ({len(kept)} changes inside {STATE}: your history, kept on purpose)")
        if session:
            print(f"  ({', '.join(session)}: IBus forgets {'these' if len(session) > 1 else 'it'} at your next login)")
        unexpected += len(gone) + len(new)
    print("\nRESULT: " + ("no trace left" if not unexpected else
                          f"{unexpected} differences; any that are not yours are a trace"))
    return 0 if not unexpected else 1


def leftovers():
    found = []
    for line in settings_lines():
        if "emoji-picker" in line:
            found.append(f"setting still mentions emoji-picker: {line}")
    try:
        from gi.repository import Gio
        for schema, key in KEYS:
            s = Gio.Settings.new(schema)
            user = s.get_user_value(key)
            if user is not None and user.equal(s.get_default_value(key)):
                found.append(f"{schema} {key} is written down although it equals the default "
                             f"(harmless; `gsettings reset {schema} {key}` clears it)")
    except Exception as e:   # no GObject bindings: skip this check, say so
        found.append(f"(could not check for pinned defaults: {e})")
    for p in ["/usr/local/lib/emoji-picker", "/usr/local/bin/emoji-picker",
              "/usr/local/bin/emoji-picker-uninstall", f"/usr/local/share/applications/{APP_ID}.desktop",
              f"/usr/local/share/icons/hicolor/scalable/apps/{APP_ID}.svg",
              "/usr/share/ibus/component/emoji-picker.xml",
              f"{CONFIG}/autostart/{APP_ID}.finish-setup.desktop", CACHE]:
        if os.path.lexists(p):
            found.append(f"still here: {p}")
    for d in ["/usr/local/share/icons/hicolor/scalable/apps", "/usr/local/share/icons/hicolor/scalable",
              "/usr/local/share/icons/hicolor", "/usr/local/share/icons", "/usr/local/share/applications"]:
        if os.path.isdir(d) and not os.listdir(d):
            found.append(f"empty folder, probably left by an older install: {d} (sudo rmdir {d})")
    names = [n for n in engine_lines() if "emoji-picker" in n]
    if names:
        found.append(f"IBus still lists {', '.join(names)} (normal until you log out and back in)")
    for line in found:
        print(f"- {line}")
    print("RESULT: " + ("nothing of emoji-picker's left" if not found else f"{len(found)} found"))
    backup = os.path.join(STATE, "backup")
    if os.path.isdir(backup):
        print(f"\nYour settings now, beside the backup taken at install ({backup}):")
        for schema, key in KEYS:
            try:
                with open(os.path.join(backup, BACKUP_FILES[key]), encoding="utf-8") as f:
                    then = f.read().strip()
            except OSError:
                then = "(not in backup)"
            now = out("gsettings", "get", schema, key).strip()
            same = "same" if now == then else "DIFFERENT"
            print(f"  {key}: {same}\n    backup: {then}\n    now:    {now}")
    return 0 if not found else 1


def main(argv):
    if len(argv) == 3 and argv[1] == "snapshot":
        snapshot(argv[2])
        return 0
    if len(argv) == 4 and argv[1] == "compare":
        return compare(argv[2], argv[3])
    if len(argv) == 2 and argv[1] == "leftovers":
        return leftovers()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
