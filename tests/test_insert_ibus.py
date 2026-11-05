"""Headless test of insertion through the real engine and a private IBus.

It starts its own ibus-daemon in a temporary folder (never the desktop's),
so it is safe to run anywhere IBus is installed; it is skipped otherwise.
It replays the sequence of a real insert: the target app has focus, the
picker opens (IBus moves the engine to its internal fake context), the
picker hides and the target takes focus back. This checks the logic in
emoji_picker/insert.py; it cannot prove the timing GNOME uses on Wayland.
"""
import os
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipUnless(shutil.which("ibus-daemon"), "IBus is not installed")
class InsertThroughIBusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ep-ibus-test-")
        run = os.path.join(cls.tmp, "run")
        comp = os.path.join(cls.tmp, "comp")
        os.makedirs(run, mode=0o700)
        os.makedirs(comp)
        with open(os.path.join(ROOT, "engine", "emoji-picker.xml.in"), encoding="utf-8") as f:
            xml = (f.read().replace("@EXEC@", os.path.join(ROOT, "engine", "engine.py"))
                   .replace("@LAYOUT@", "us").replace("@VARIANT_ELEMENT@", ""))
        with open(os.path.join(comp, "emoji-picker.xml"), "w", encoding="utf-8") as f:
            f.write(xml)
        cls.sock = os.path.join(run, "ibus.sock")
        cls.engine_sock = os.path.join(run, "emoji-picker-ibus.sock")
        cls.env = dict(os.environ, XDG_RUNTIME_DIR=run,
                       XDG_STATE_HOME=os.path.join(cls.tmp, "state"),
                       IBUS_ADDRESS=f"unix:path={cls.sock}",
                       IBUS_COMPONENT_PATH=f"{comp}:/usr/share/ibus/component")
        cls.saved_env = {k: os.environ.get(k) for k in ("IBUS_ADDRESS",)}
        os.environ["IBUS_ADDRESS"] = cls.env["IBUS_ADDRESS"]
        cls.daemon = subprocess.Popen(
            ["ibus-daemon", f"--address={cls.env['IBUS_ADDRESS']}", "--panel=disable", "--cache=none"],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        import gi
        gi.require_version("IBus", "1.0")
        from gi.repository import GLib, IBus
        cls.GLib, cls.IBus = GLib, IBus
        IBus.init()
        cls.bus = None
        for _ in range(60):
            time.sleep(0.25)
            if os.path.exists(cls.sock):
                bus = IBus.Bus()
                if bus.is_connected():
                    cls.bus = bus
                    break
        if cls.bus is None:
            raise unittest.SkipTest("private ibus-daemon did not start")
        cls.committed = []
        cls.target = cls.bus.create_input_context("target-app")
        cls.target.set_capabilities(IBus.Capabilite.FOCUS)
        cls.target.connect("commit-text", lambda _ic, t: cls.committed.append(t.get_text()))
        cls.ibus_engine("emoji-picker")
        cls.target.focus_in()
        cls.pump_until(lambda: os.path.exists(cls.engine_sock), 10)

    @classmethod
    def tearDownClass(cls):
        cls.daemon.terminate()
        try:
            cls.daemon.wait(3)
        except subprocess.TimeoutExpired:
            cls.daemon.kill()
        for k, v in cls.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def ibus_engine(cls, name):
        subprocess.run(["ibus", "engine", name], env=cls.env, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def pump(cls, seconds):
        ctx = cls.GLib.MainContext.default()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            while ctx.pending():
                ctx.iteration(False)
            time.sleep(0.005)

    @classmethod
    def pump_until(cls, pred, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            cls.pump(0.02)
            if pred():
                return True
        return False

    def run_insert(self, text, refocus_after_ms):
        from emoji_picker import insert
        self.committed.clear()
        self.target.focus_in()
        self.pump(0.1)
        self.target.focus_out()          # the picker window takes focus
        self.pump(0.1)
        ok, why, st = insert.preflight(self.engine_sock)
        self.assertTrue(ok, why)
        result = {}
        t0 = time.monotonic()
        ins = insert.Inserter(text, st["gen"], lambda r, d: result.update(r=r, d=d,
                              ms=(time.monotonic() - t0) * 1000), path=self.engine_sock)
        ins.start()                      # the picker hid
        if refocus_after_ms is not None:
            self.pump(refocus_after_ms / 1000)
            self.target.focus_in()       # the app takes focus back
        self.pump_until(lambda: "r" in result, 4)
        self.pump(0.1)
        return result

    def test_1_commit_reaches_the_app_after_it_takes_focus_back(self):
        r = self.run_insert("👨‍👩‍👧‍👦", refocus_after_ms=60)
        self.assertEqual(r.get("r"), "inserted", r)
        self.assertEqual(self.committed, ["👨‍👩‍👧‍👦"])
        self.assertGreaterEqual(r["ms"], 150)

    def test_2_slow_app_still_gets_it(self):
        r = self.run_insert("🔥", refocus_after_ms=600)
        self.assertEqual(r.get("r"), "inserted", r)
        self.assertEqual(self.committed, ["🔥"])

    def test_3_no_app_takes_focus_nothing_is_committed(self):
        r = self.run_insert("😀", refocus_after_ms=None)
        self.assertEqual(r.get("r"), "timeout", r)
        self.assertEqual(self.committed, [])

    def test_3b_engine_names_the_fake_context_and_refuses_it(self):
        from emoji_picker import insert
        self.target.focus_in()
        self.pump(0.1)
        self.assertEqual(insert.status(self.engine_sock).get("client"), "target-app")
        self.target.focus_out()          # nobody has focus: IBus's fake context
        self.pump(0.2)
        self.assertEqual(insert.status(self.engine_sock).get("client"), "fake")
        self.committed.clear()
        reply = insert.request({"op": "commit", "text": "😀"}, path=self.engine_sock)
        self.assertEqual(reply, {"ok": False, "why": "fake-context"})
        self.target.focus_in()
        self.pump(0.2)
        self.assertEqual(self.committed, [])

    def test_4_preflight_fails_when_engine_is_not_active(self):
        from emoji_picker import insert
        self.ibus_engine("xkb:us::eng")
        self.pump(0.5)
        ok, why, _st = insert.preflight(self.engine_sock)
        self.ibus_engine("emoji-picker")
        self.pump(0.5)
        self.assertFalse(ok)
        self.assertIn("not the active input source", why)

    def test_5_preflight_fails_when_engine_is_unreachable(self):
        from emoji_picker import insert
        ok, why, _st = insert.preflight(os.path.join(self.tmp, "nope.sock"))
        self.assertFalse(ok)
        self.assertIn("not running", why)


if __name__ == "__main__":
    unittest.main()
