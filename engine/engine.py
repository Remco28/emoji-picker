#!/usr/bin/env python3
"""Passive IBus engine for emoji-picker.

It passes every key straight through, so typing is unchanged. Its only job
is to commit an emoji into the app that has focus when the picker asks.

Protocol: one JSON request per connection on a 0600 Unix socket at
$XDG_RUNTIME_DIR/emoji-picker-ibus.sock, one JSON reply:
    {"op": "status"} -> {"gen": n, "since_ms": t, "enabled": bool, "focused": bool}
    {"op": "commit", "text": s} -> {"ok": true} or {"ok": false, "why": "..."}

"gen" counts focus_in events. IBus moves the engine to an internal "fake"
context whenever no app has focus, and a commit there is silently dropped,
so the picker uses the counter to wait until a real app has taken focus
after its own window hid. "since_ms" is the time since the last focus
change. Every event is logged with a timestamp for diagnosis.

The engine is created with has-focus-id, so IBus (1.5.27+) also says which
client took focus; the internal context is called "fake". The status
reports it as "client", and a commit into the fake context is refused.
(Tested 2026-11-05 with a private ibus-daemon 1.5.29.)
"""
import json
import os
import socket
import sys
import time

import gi

gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402

SOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "emoji-picker-ibus.sock")
STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                     "emoji-picker")
LOG_PATH = os.path.join(STATE, "engine.log")
LOG_MAX = 1_000_000


def log(msg):
    try:
        os.makedirs(STATE, exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX:
            os.replace(LOG_PATH, LOG_PATH + ".1")
        t = time.time()
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S', time.localtime(t))}.{int(t * 1000) % 1000:03d} {msg}\n")
    except OSError:
        pass


class State:
    gen = 0
    last_change = time.monotonic()
    focused = None   # engine instance holding focus
    enabled = False
    client = None    # who has focus ("fake" = nobody), when IBus tells us


class PassiveEngine(IBus.Engine):
    __gtype_name__ = "EmojiPickerPassiveEngine"

    def do_process_key_event(self, keyval, keycode, state):
        return False  # never consume a key

    def do_focus_in(self):  # older IBus, without client names
        State.gen += 1
        State.last_change = time.monotonic()
        State.focused = self
        State.client = None
        log(f"focus_in gen={State.gen}")

    def do_focus_out(self):
        State.last_change = time.monotonic()
        if State.focused is self:
            State.focused = None
        log("focus_out")

    def do_focus_in_id(self, object_path, client):
        State.gen += 1
        State.last_change = time.monotonic()
        State.focused = self
        State.client = client
        log(f"focus_in gen={State.gen} client={client!r} context={object_path}")

    def do_focus_out_id(self, object_path):
        State.last_change = time.monotonic()
        if State.focused is self:
            State.focused = None
        log(f"focus_out context={object_path}")

    def do_enable(self):
        State.enabled = True
        log("enable")

    def do_disable(self):
        State.enabled = False
        log("disable")

    def do_set_capabilities(self, caps):
        log(f"set_capabilities 0x{caps:x}")

    def do_set_cursor_location(self, x, y, w, h):
        log(f"cursor_location {x},{y} {w}x{h}")

    def do_set_content_type(self, purpose, hints):
        log(f"content_type purpose={purpose} hints=0x{hints:x}")


def handle(req):
    op = req.get("op")
    if op == "status":
        return {"gen": State.gen, "enabled": State.enabled, "focused": State.focused is not None,
                "client": State.client,
                "since_ms": int((time.monotonic() - State.last_change) * 1000)}
    if op == "commit":
        text = req.get("text", "")
        if not isinstance(text, str) or not text or len(text) > 64:
            return {"ok": False, "why": "bad-text"}
        eng = State.focused
        if eng is None:
            log(f"commit {text!r}: refused, no focused context")
            return {"ok": False, "why": "no-focus"}
        if State.client == "fake":
            log(f"commit {text!r}: refused, only IBus's internal context has focus")
            return {"ok": False, "why": "fake-context"}
        eng.commit_text(IBus.Text.new_from_string(text))
        log(f"commit {text!r}: sent at gen={State.gen}")
        return {"ok": True}
    return {"ok": False, "why": "bad-op"}


def serve():
    try:
        os.remove(SOCK_PATH)
    except FileNotFoundError:
        pass
    old = os.umask(0o177)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK_PATH)
    os.umask(old)
    srv.listen(8)
    srv.setblocking(False)

    def on_accept(_fd, _cond):
        try:
            conn, _ = srv.accept()
            conn.settimeout(1)
            raw = conn.recv(4096).decode("utf-8", "replace")
            try:
                reply = handle(json.loads(raw))
            except ValueError:
                reply = {"ok": False, "why": "bad-json"}
            conn.sendall(json.dumps(reply).encode())
            conn.close()
        except OSError as e:
            log(f"socket error: {e}")
        return True

    GLib.io_add_watch(srv.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, on_accept)
    return srv


def main():
    if "--ibus" not in sys.argv:
        sys.exit("engine.py is started by ibus-daemon (--ibus); see install.sh")
    IBus.init()
    bus = IBus.Bus()
    loop = GLib.MainLoop()
    bus.connect("disconnected", lambda _b: loop.quit())
    factory = IBus.Factory.new(bus.get_connection())
    created = [0]

    def create_engine(_factory, name):
        # has-focus-id makes IBus report which client has focus (see above)
        created[0] += 1
        log(f"creating engine {name}")
        return PassiveEngine(engine_name=name, connection=bus.get_connection(), has_focus_id=True,
                             object_path=f"/org/freedesktop/IBus/Engine/EmojiPicker/{created[0]}")

    factory.connect("create-engine", create_engine)
    bus.request_name("org.freedesktop.IBus.EmojiPicker", 0)
    _srv = serve()  # noqa: F841 (keep the socket alive)
    log(f"engine started, pid {os.getpid()}")
    loop.run()


if __name__ == "__main__":
    main()
