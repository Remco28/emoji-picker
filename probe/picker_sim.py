#!/usr/bin/env python3
"""Simulated emoji picker for the probe.

Shows a few emoji chosen to stress insertion (plain, skin tone, VS16,
ZWJ sequence, flag). Clicking one closes the window, waits, then inserts
into whatever app regains focus, using one of three methods:

  --mode ime     commit through the passive IBus engine (no clipboard)
  --mode portal  set the clipboard, then send Ctrl+V via the
                 RemoteDesktop portal
  --mode copy    set the clipboard only; you paste by hand

Run it from a GNOME shortcut (see setup.sh) so the target app is the
window that had focus, exactly as a real picker would be used.
"""
import argparse
import os
import socket
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

EMOJI = [
    ("😀", "plain"),
    ("👍🏽", "skin tone"),
    ("❤️", "VS16"),
    ("👨‍👩‍👧‍👦", "ZWJ family"),
    ("🏳️‍🌈", "ZWJ flag"),
    ("🇨🇦", "regional flag"),
]

STATE = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "emojitest"
)
os.makedirs(STATE, exist_ok=True)
SOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "emojitest-ibus.sock")
TOKEN_PATH = os.path.join(STATE, "portal_restore_token")
LOG_PATH = os.path.join(STATE, "picker.log")

KEY_LEFTCTRL, KEY_V = 29, 47  # evdev codes (assumes a QWERTY-position V key)


def log(msg):
    line = f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- IME method ----------
def ime_send(text):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(SOCK_PATH)
        s.sendall(text.encode())
        return s.recv(256).decode()
    except OSError as e:
        return f"err:engine-unreachable ({e})"
    finally:
        s.close()


def ime_deliver(text, give_up_ms=2000, interval_ms=50, on_done=None):
    """Retry until the engine reports a focused context; log how long it took.
    That latency is the key number for the IME approach."""
    t0 = time.monotonic()

    def attempt():
        reply = ime_send(text)
        waited = int((time.monotonic() - t0) * 1000)
        if reply == "ok":
            log(f"IME commit ok after {waited} ms of waiting for focus")
        elif waited < give_up_ms and reply == "err:no-focus":
            return True  # keep retrying
        else:
            log(f"IME commit FAILED after {waited} ms: {reply}")
        if on_done:
            on_done()
        return False

    GLib.timeout_add(interval_ms, attempt)


# ---------- portal method ----------
class Portal:
    NAME = "org.freedesktop.portal.Desktop"
    PATH = "/org/freedesktop/portal/desktop"
    IFACE = "org.freedesktop.portal.RemoteDesktop"

    def __init__(self):
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sender = self.conn.get_unique_name()[1:].replace(".", "_")
        self.n = 0
        self.session = None

    def _request(self, method, fixed, options, timeout_s=120):
        self.n += 1
        token = f"emojitest{os.getpid()}x{self.n}"
        options = dict(options)
        options["handle_token"] = GLib.Variant("s", token)
        req_path = f"/org/freedesktop/portal/desktop/request/{self.sender}/{token}"
        loop, out = GLib.MainLoop(), {}

        def on_response(_c, _s, _o, _i, _sig, params):
            out["code"], out["results"] = params.unpack()
            loop.quit()

        sub = self.conn.signal_subscribe(
            self.NAME, "org.freedesktop.portal.Request", "Response",
            req_path, None, Gio.DBusSignalFlags.NONE, on_response)
        sig = "(" + "".join(t for t, _ in fixed) + "a{sv})"
        args = tuple(v for _, v in fixed) + (options,)
        try:
            self.conn.call_sync(self.NAME, self.PATH, self.IFACE, method,
                                GLib.Variant(sig, args), None,
                                Gio.DBusCallFlags.NONE, -1, None)
            GLib.timeout_add_seconds(timeout_s, lambda: (loop.quit(), False)[1])
            loop.run()
        finally:
            self.conn.signal_unsubscribe(sub)
        if "code" not in out:
            raise RuntimeError(f"{method}: no response (timed out waiting for the dialog?)")
        if out["code"] != 0:
            raise RuntimeError(f"{method}: portal response code {out['code']} (1=cancelled, 2=failed)")
        return out["results"]

    def _prop(self, name):
        try:
            r = self.conn.call_sync(
                self.NAME, self.PATH, "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", (self.IFACE, name)), None,
                Gio.DBusCallFlags.NONE, -1, None)
            return r.unpack()[0]
        except GLib.Error as e:
            return f"unavailable ({e.message})"

    def start(self):
        log(f"RemoteDesktop portal version={self._prop('version')} "
            f"devices={self._prop('AvailableDeviceTypes')}")
        res = self._request("CreateSession", [], {
            "session_handle_token": GLib.Variant("s", f"emojitest{os.getpid()}")})
        self.session = res["session_handle"]
        opts = {"types": GLib.Variant("u", 1),          # 1 = keyboard
                "persist_mode": GLib.Variant("u", 2)}   # remember until revoked
        if os.path.exists(TOKEN_PATH):
            opts["restore_token"] = GLib.Variant("s", open(TOKEN_PATH).read().strip())
            log("using saved restore token (expect NO permission dialog)")
        else:
            log("no restore token yet: expect a permission dialog")
        self._request("SelectDevices", [("o", self.session)], opts)
        t0 = time.monotonic()
        res = self._request("Start", [("o", self.session), ("s", "")], {})
        log(f"portal Start returned after {time.monotonic() - t0:.1f}s, "
            f"devices={res.get('devices')}")
        if res.get("restore_token"):
            with open(TOKEN_PATH, "w") as f:
                f.write(res["restore_token"])
            log("saved restore token for next run")
        else:
            log("portal gave NO restore token: permission will be asked every run")

    def key(self, code, down):
        self.conn.call_sync(
            self.NAME, self.PATH, self.IFACE, "NotifyKeyboardKeycode",
            GLib.Variant("(oa{sv}iu)", (self.session, {}, code, 1 if down else 0)),
            None, Gio.DBusCallFlags.NONE, -1, None)

    def paste(self):
        self.key(KEY_LEFTCTRL, True)
        self.key(KEY_V, True)
        self.key(KEY_V, False)
        self.key(KEY_LEFTCTRL, False)


# ---------- UI ----------
class App(Gtk.Application):
    def __init__(self, mode, delay_ms):
        super().__init__(application_id="dev.emojitest.Picker")
        self.mode, self.delay_ms, self.portal = mode, delay_ms, None

    def do_activate(self):
        log(f"picker start: mode={self.mode} delay={self.delay_ms}ms "
            f"session={os.environ.get('XDG_SESSION_TYPE')}")
        if self.mode == "portal":
            try:
                self.portal = Portal()
                self.portal.start()
            except Exception as e:  # noqa: BLE001
                log(f"PORTAL SETUP FAILED: {e}")
                self.quit()
                return
        win = Gtk.ApplicationWindow(application=self, title=f"Emoji probe ({self.mode})")
        win.set_default_size(420, 160)
        box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                          margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        for char, label in EMOJI:
            btn = Gtk.Button()
            btn.set_child(Gtk.Label(use_markup=True,
                                    label=f'<span size="xx-large">{char}</span>\n<small>{label}</small>'))
            btn.connect("clicked", self.on_pick, win, char, label)
            box.append(btn)
        win.set_child(box)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", lambda c, kv, kc, st: (self.quit(), True)[1]
                    if kv == Gdk.KEY_Escape else False)
        win.add_controller(key)
        win.present()

    def on_pick(self, _btn, win, char, label):
        log(f"picked {char} ({label})")
        if self.mode in ("portal", "copy"):
            Gdk.Display.get_default().get_clipboard().set(char)
        if self.mode == "copy":
            log("copied; paste it yourself with Ctrl+V")
            return
        win.set_visible(False)  # focus should return to the previous app
        done = lambda: GLib.timeout_add(1500, self.quit)  # noqa: E731
        if self.mode == "ime":
            GLib.timeout_add(self.delay_ms, lambda: (ime_deliver(char, on_done=done), False)[1])
        else:
            def paste():
                try:
                    self.portal.paste()
                    log("sent Ctrl+V via portal")
                except Exception as e:  # noqa: BLE001
                    log(f"portal paste FAILED: {e}")
                done()
                return False
            GLib.timeout_add(self.delay_ms, paste)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--mode", choices=["ime", "portal", "copy"], required=True)
    ap.add_argument("--delay-ms", type=int, default=150,
                    help="wait after closing the window before inserting (default 150)")
    args = ap.parse_args()
    sys.exit(App(args.mode, args.delay_ms).run([sys.argv[0]]))


if __name__ == "__main__":
    main()
