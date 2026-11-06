"""Getting the chosen emoji into the app the user was typing in.

The picker talks to the passive IBus engine (engine/engine.py) over a Unix
socket. The sequence, from plan v3 section 7:

1. Before hiding, `preflight()` checks the engine is reachable and is the
   active engine. If not, the window copies the emoji while it still has
   focus (the only clipboard path measured to work on Wayland) and says so.
2. Otherwise read the engine's focus generation g0, hide the window, and
   `Inserter` polls every 25 ms. It commits only when at least 150 ms have
   passed since hiding, the generation is above g0 (a real app took focus
   after the picker hid), and there has been no focus change for 30 ms.
   When IBus names the focused client (1.5.27+), its internal "fake"
   context never counts as an app; the engine also refuses commits there.
3. If that does not happen within 2 s, nothing is committed (it would go
   into IBus's fake context and vanish); the user gets a notification.
"""
import json
import os
import socket
import time

from gi.repository import Gio, GLib

SOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "emoji-picker-ibus.sock")
MIN_DELAY_MS = 150
QUIET_MS = 30
POLL_MS = 25
GIVE_UP_MS = 2000


def request(obj, timeout=0.5, path=SOCK_PATH):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
        s.sendall(json.dumps(obj).encode())
        return json.loads(s.recv(4096).decode())
    finally:
        s.close()


def status(path=SOCK_PATH):
    """Engine status dict, or None when it cannot be reached."""
    try:
        return request({"op": "status"}, path=path)
    except (OSError, ValueError):
        return None


def preflight(path=SOCK_PATH):
    """(ok, why, status). ok means the engine can insert after we hide."""
    st = status(path)
    if st is None:
        return False, "the input engine is not running", None
    if not st.get("enabled"):
        return False, "the emoji-picker keyboard is not the active input source", st
    return True, "", st


def why_not_active():
    """Why our engine is not the one typing, in the user's terms, or None."""
    import subprocess
    try:
        r = subprocess.run(["ibus", "engine"], capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        return None
    name = r.stdout.strip()
    if r.returncode != 0 or not name or name.startswith("emoji-picker:"):
        return None
    if name.startswith("xkb:") or name == "emoji-picker":
        return ("this keyboard has no emoji support yet: run \u2018emoji-picker --setup\u2019 "
                "to add it")
    return (f"another input method is active ({name}); switch to a keyboard "
            "\u201cwith emoji\u201d to type emoji directly")


class Inserter:
    """Polls the engine after the window hid and commits when it is safe.

    `done(result, detail)` is called once with result "inserted", "timeout"
    or "error". `clock` returns milliseconds; injectable for tests.
    """

    def __init__(self, text, g0, done, path=SOCK_PATH, clock=None, log=None):
        self.text, self.g0, self.done, self.path = text, g0, done, path
        self.clock = clock or (lambda: time.monotonic() * 1000)
        self.log = log or (lambda msg: None)
        self.t0 = None
        self.finished = False

    def start(self):
        self.t0 = self.clock()
        GLib.timeout_add(POLL_MS, self._tick)

    def ready(self, st, now):
        """The commit rule, separated so it can be tested on its own."""
        return (now - self.t0 >= MIN_DELAY_MS and st is not None and st.get("enabled")
                and st.get("focused") and st.get("client") != "fake"
                and st.get("gen", 0) > self.g0
                and st.get("since_ms", 0) >= QUIET_MS)

    def _tick(self):
        if self.finished:
            return False
        now = self.clock()
        st = status(self.path)
        if self.ready(st, now):
            try:
                reply = request({"op": "commit", "text": self.text}, path=self.path)
            except (OSError, ValueError) as e:
                return self._finish("error", f"commit failed: {e}")
            if reply.get("ok"):
                return self._finish("inserted", f"after {now - self.t0:.0f} ms, gen {st['gen']}")
            return self._finish("error", f"engine refused: {reply.get('why')}")
        if now - self.t0 >= GIVE_UP_MS:
            return self._finish("timeout", f"no app took focus within {GIVE_UP_MS} ms "
                                           f"(last status {st})")
        return True

    def _finish(self, result, detail):
        self.finished = True
        self.log(f"insert {self.text!r}: {result} ({detail})")
        self.done(result, detail)
        return False


def notify(summary, body):
    """A desktop notification through org.freedesktop.Notifications.

    GNotification would be dropped by GNOME Shell for an app without an
    installed .desktop file, so this calls the notification service directly.
    """
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                      "org.freedesktop.Notifications", "Notify",
                      GLib.Variant("(susssasa{sv}i)", ("Emoji Picker", 0, "face-smile",
                                                       summary, body, [], {}, 5000)),
                      None, Gio.DBusCallFlags.NONE, 2000, None)
        return True
    except GLib.Error:
        return False
