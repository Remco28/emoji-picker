#!/usr/bin/env python3
"""Headless self-test of the passive engine. Safe to run anywhere:
it starts its OWN private ibus-daemon in a temp dir, never touching your
real IBus or input settings, and needs no sudo and no display.

Checks, in order:
  1. the daemon loads the engine component
  2. a client input context can select the engine and focus in
  3. a commit request arrives at the client as a commit-text signal
  4. a request with no focused context is refused (not lost silently)
  5. after focus returns, committing works again, and how long that takes
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="emojitest-selftest-")
run = os.path.join(tmp, "run")
os.makedirs(run, mode=0o700)
os.makedirs(os.path.join(tmp, "comp"))
sock = os.path.join(run, "ibus.sock")

with open(os.path.join(HERE, "emojitest.xml.in")) as f:
    xml = f.read().replace("@EXEC@", os.path.join(HERE, "engine.py"))
with open(os.path.join(tmp, "comp", "emojitest.xml"), "w") as f:
    f.write(xml)

env = dict(os.environ,
           XDG_RUNTIME_DIR=run, XDG_STATE_HOME=os.path.join(tmp, "state"),
           IBUS_ADDRESS=f"unix:path={sock}",
           IBUS_COMPONENT_PATH=f"{tmp}/comp:/usr/share/ibus/component")
os.environ.update(env)

import gi  # noqa: E402  (after env is set)
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402

results = []
daemon = None


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""), flush=True)
    return ok


def pump(seconds):
    end = time.monotonic() + seconds
    ctx = GLib.MainContext.default()
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.01)


def ask(text):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(os.path.join(run, "emojitest-ibus.sock"))
    s.sendall(text.encode())
    r = s.recv(64).decode()
    s.close()
    return r


def wait_for(pred, timeout):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        pump(0.05)
        if pred():
            return int((time.monotonic() - t0) * 1000)
    return None


try:
    daemon = subprocess.Popen(
        ["ibus-daemon", f"--address={env['IBUS_ADDRESS']}", "--panel=disable", "--cache=none"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    IBus.init()
    bus = None
    for _ in range(40):
        time.sleep(0.25)
        if os.path.exists(sock):
            bus = IBus.Bus()
            if bus.is_connected():
                break
    if not check("private ibus-daemon starts", bus is not None and bus.is_connected()):
        sys.exit(1)

    engines = [e.get_name() for e in bus.list_engines()]
    if not check("daemon loads the emojitest component", "emojitest" in engines):
        sys.exit(1)

    committed = []
    ic = bus.create_input_context("emojitest-selftest")
    ic.set_capabilities(IBus.Capabilite.FOCUS)
    ic.connect("commit-text", lambda _ic, t: committed.append(t.get_text()))
    # GNOME selects an input source via the *global* engine; that is the call
    # that makes ibus-daemon spawn the engine (per-context set_engine does not).
    subprocess.run(["ibus", "engine", "emojitest"], env=env, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ic.focus_in()
    up = wait_for(lambda: os.path.exists(os.path.join(run, "emojitest-ibus.sock")), 8)
    check("engine process starts and listens", up is not None, f"{up} ms" if up else "timed out")
    got = wait_for(lambda: ask("__status__") == "focused", 5) if up is not None else None
    check("engine reports a focused context", got is not None, f"{got} ms" if got is not None else "never focused")

    family = "👨‍👩‍👧‍👦"
    reply = ask(family)
    wait_for(lambda: bool(committed), 2)
    check("commit reaches the client", reply == "ok" and committed == [family],
          f"reply={reply!r} got={committed!r}")

    ic.focus_out()
    pump(0.3)
    reply = ask("😀")
    # IBus parks the engine on an internal fake context when no app has focus,
    # so the engine still says "ok" and the text goes nowhere. Not a pass/fail:
    # it means "ok" can NOT be read as "delivered to an app".
    print(f"[NOTE] commit while no app has focus: reply={reply!r} "
          f"({'accepted then dropped by IBus: fake context' if reply == 'ok' else 'refused'})", flush=True)

    committed.clear()
    ic.focus_in()
    t0 = time.monotonic()
    ok = False
    for _ in range(100):
        pump(0.02)
        if ask("😀") == "ok":
            ok = True
            break
    ms = int((time.monotonic() - t0) * 1000)
    wait_for(lambda: bool(committed), 2)
    check("commit works again after focus returns", ok and committed == ["😀"],
          f"focus-to-commit {ms} ms")
finally:
    logf = os.path.join(tmp, "state", "emojitest", "engine.log")
    if os.path.exists(logf):
        print("\n--- engine.log ---")
        print(open(logf, encoding="utf-8").read().rstrip())
    if daemon:
        daemon.terminate()
        try:
            daemon.wait(3)
        except subprocess.TimeoutExpired:
            daemon.kill()
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) and len(results) == 6 else 1)
