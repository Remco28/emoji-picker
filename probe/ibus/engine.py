#!/usr/bin/env python3
"""Passive IBus engine for the emoji-picker probe.

It passes every key through untouched. Its only job is to commit text
to whichever app currently has focus when another process asks it to,
over a Unix socket. That is the question under test: can a picker
window close, focus return to the app, and a commit then land cleanly?

Protocol (one request per connection, UTF-8):
    "__status__"  -> "focused" or "unfocused"
    anything else -> commits it; replies "ok" or "err:<reason>"
Every focus change and commit is logged with a timestamp.
"""
import os
import socket
import sys
import time

import gi

gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
SOCK_PATH = os.path.join(RUNTIME, "emojitest-ibus.sock")
STATE = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "emojitest"
)
os.makedirs(STATE, exist_ok=True)
LOG_PATH = os.path.join(STATE, "engine.log")


def log(msg):
    line = f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {msg}"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class PassiveEngine(IBus.Engine):
    __gtype_name__ = "EmojiTestPassiveEngine"
    focused = None  # the engine instance that currently has an input context

    def do_process_key_event(self, keyval, keycode, state):
        return False  # never consume anything

    def do_focus_in(self):
        PassiveEngine.focused = self
        log("focus_in")

    def do_focus_out(self):
        if PassiveEngine.focused is self:
            PassiveEngine.focused = None
        log("focus_out")

    def do_set_capabilities(self, caps):
        # Logged to learn whether real app contexts differ from IBus's
        # internal "fake" context that holds focus when no app does.
        log(f"set_capabilities 0x{caps:x}")

    def do_set_cursor_location(self, x, y, w, h):
        log(f"cursor_location {x},{y} {w}x{h}")

    def do_enable(self):
        log("enable")

    def do_disable(self):
        log("disable")


def handle(text):
    if text == "__status__":
        return "focused" if PassiveEngine.focused else "unfocused"
    eng = PassiveEngine.focused
    if eng is None:
        log(f"commit {text!r}: REFUSED, no focused input context")
        return "err:no-focus"
    eng.commit_text(IBus.Text.new_from_string(text))
    log(f"commit {text!r}: sent")
    return "ok"


def serve():
    if os.path.exists(SOCK_PATH):
        os.remove(SOCK_PATH)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK_PATH)
    os.chmod(SOCK_PATH, 0o600)
    srv.listen(4)
    srv.setblocking(False)

    def on_accept(fd, cond):
        try:
            conn, _ = srv.accept()
            conn.settimeout(1)
            text = conn.recv(4096).decode("utf-8", "replace")
            conn.sendall(handle(text).encode())
            conn.close()
        except OSError as e:
            log(f"socket error: {e}")
        return True

    GLib.io_add_watch(srv.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, on_accept)


def main():
    IBus.init()
    bus = IBus.Bus()
    loop = GLib.MainLoop()
    bus.connect("disconnected", lambda b: loop.quit())
    factory = IBus.Factory.new(bus.get_connection())
    factory.add_engine("emojitest", PassiveEngine.__gtype__)
    if "--ibus" in sys.argv:
        bus.request_name("org.freedesktop.IBus.EmojiTest", 0)
    else:
        sys.exit("engine.py is started by ibus-daemon (--ibus); run setup.sh install")
    serve()
    log(f"engine started, pid {os.getpid()}")
    loop.run()


if __name__ == "__main__":
    main()
