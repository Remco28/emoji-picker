"""install.sh, finish-setup and uninstall.sh end to end, without sudo.

GNOME settings go to a throwaway keyfile (GSETTINGS_BACKEND=keyfile), files
to a temporary root (--root), and `ibus` is a stub whose `list-engine`
output each test sets. Nothing on this computer is touched.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "org.gnome.desktop.input-sources"
KB = "org.gnome.settings-daemon.plugins.media-keys"
KB_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/emoji-picker/"
KB_ONE = f"{KB}.custom-keybinding:{KB_PATH}"
HOTKEY = "org.freedesktop.ibus.panel.emoji"


def have_schemas():
    if not shutil.which("gsettings") or not os.path.exists("/usr/bin/python3"):
        return False
    r = subprocess.run(["gsettings", "list-schemas"], capture_output=True, text=True)
    return all(s in r.stdout.split() for s in (SRC, KB, HOTKEY))


@unittest.skipUnless(have_schemas(), "GNOME / IBus settings schemas are not installed")
class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ep-installer-test-")
        self.root = os.path.join(self.tmp, "root")
        fake = os.path.join(self.tmp, "fakebin")
        os.makedirs(fake)
        self.engines_file = os.path.join(self.tmp, "engines.txt")
        with open(os.path.join(fake, "ibus"), "w") as f:
            f.write(f"""#!/bin/sh
case "$1" in
  list-engine) [ -s "{self.engines_file}" ] || {{ echo "Can't connect to IBus." >&2; exit 1; }}
               cat "{self.engines_file}" ;;
  engine) echo xkb:us::eng ;;
esac
""")
        os.chmod(os.path.join(fake, "ibus"), 0o755)
        for d in ("home", "config", "state", "cache"):   # a home folder always has these
            os.makedirs(os.path.join(self.tmp, d))
        self.env = dict(os.environ, GSETTINGS_BACKEND="keyfile", HOME=os.path.join(self.tmp, "home"),
                        XDG_CONFIG_HOME=os.path.join(self.tmp, "config"),
                        XDG_STATE_HOME=os.path.join(self.tmp, "state"),
                        XDG_CACHE_HOME=os.path.join(self.tmp, "cache"),
                        MESA_SHADER_CACHE_DISABLE="true",   # the graphics driver's cache, not ours
                        PATH=f"{fake}:{os.environ['PATH']}")
        self.lib = os.path.join(self.root, "usr/local/lib/emoji-picker")
        self.bin = os.path.join(self.root, "usr/local/bin")
        self.autostart = os.path.join(self.tmp, "config/autostart/io.github.remco28.EmojiPicker.finish-setup.desktop")
        self.component = os.path.join(self.root, "usr/share/ibus/component/emoji-picker.xml")
        self.ibus_lists()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers
    def ibus_lists(self, *names):
        with open(self.engines_file, "w") as f:
            if names:
                f.write("language: English\n" + "".join(f"  {n} - x\n" for n in names))

    def get(self, schema, key):
        return subprocess.run(["gsettings", "get", schema, key], env=self.env,
                              capture_output=True, text=True, check=True).stdout.strip()

    def set(self, schema, key, value):
        subprocess.run(["gsettings", "set", schema, key, value], env=self.env, check=True)

    def run_script(self, args, ok=True):
        r = subprocess.run(args, env=self.env, capture_output=True, text=True, timeout=120)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def install(self, *extra, ok=True):
        return self.run_script([os.path.join(ROOT_DIR, "install.sh"), "--root", self.root, *extra], ok)

    def uninstall(self, *extra):
        return self.run_script([os.path.join(self.bin, "emoji-picker-uninstall"), "--root", self.root, *extra])

    def snapshot(self):
        """Every file and folder of this test's computer, and every setting
        (an empty [group] is only how the keyfile backend shows a reset)."""
        keyfile = os.path.join(self.tmp, "config/glib-2.0/settings/keyfile")
        files = set()
        for dp, dns, fns in os.walk(self.tmp):
            for n in dns + fns:
                p = os.path.join(dp, n)
                if p not in (keyfile, self.engines_file) and "/fakebin" not in p:
                    files.add(os.path.relpath(p, self.tmp))
        settings, group = {}, None
        if os.path.exists(keyfile):
            with open(keyfile) as f:
                for line in f.read().splitlines():
                    if line.startswith("["):
                        group = line
                    elif "=" in line:
                        settings[(group, line.split("=", 1)[0])] = line.split("=", 1)[1]
        return files, settings

    def use_the_app(self):
        """What a day of use leaves: history, a log, the font cache."""
        for path in ("state/emoji-picker/usage.json", "state/emoji-picker/picker.log",
                     "cache/emoji-picker/font-version.json"):
            os.makedirs(os.path.dirname(os.path.join(self.tmp, path)), exist_ok=True)
            with open(os.path.join(self.tmp, path), "w") as f:
                f.write("{}")

    def finish(self):
        return self.run_script([os.path.join(self.bin, "emoji-picker"), "--finish-setup"])

    def versions(self):
        return sorted(os.listdir(os.path.join(self.lib, "versions")))

    # tests
    def test_fresh_install_then_login_then_uninstall(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        out = self.install().stdout
        self.assertIn("Until you log out and back in, Enter copies", out)
        # sources wait for IBus to know the engine; the login step is queued
        self.assertEqual(self.get(SRC, "sources"), "[('xkb', 'us')]")
        self.assertTrue(os.path.exists(self.autostart))
        with open(self.component) as f:
            xml = f.read()
        self.assertIn("<name>emoji-picker:us</name>", xml)
        self.assertIn(f"/usr/bin/python3 -I {self.lib}/current/engine/engine.py --ibus", xml)
        self.assertEqual(self.get(KB_ONE, "binding"), "'<Super>period'")
        self.assertEqual(self.get(KB_ONE, "command"), f"'{self.bin}/emoji-picker'")
        self.assertEqual(self.get(HOTKEY, "hotkey"), "['<Super>semicolon']")
        self.assertTrue(os.path.islink(os.path.join(self.lib, "current")))
        # the installed launcher runs the installed copy, not the clone
        r = self.run_script([os.path.join(self.bin, "emoji-picker"), "--version"])
        self.assertIn("emoji-picker 1.", r.stdout)

        # next login: IBus knows the engine, finish-setup swaps the layout
        self.ibus_lists("xkb:us::eng", "emoji-picker:us")
        self.finish()
        self.assertEqual(self.get(SRC, "sources"), "[('ibus', 'emoji-picker:us')]")
        self.assertFalse(os.path.exists(self.autostart))
        self.run_script([os.path.join(self.bin, "emoji-picker"), "--doctor"])

        self.uninstall()
        self.assertEqual(self.get(SRC, "sources"), "[('xkb', 'us')]")
        self.assertEqual(self.get(HOTKEY, "hotkey"), "['<Super>period', '<Super>semicolon']")
        self.assertEqual(self.get(KB_ONE, "name"), "''")
        self.assertNotIn(KB_PATH, self.get(KB, "custom-keybindings"))
        self.assertFalse(os.path.exists(self.lib))
        self.assertFalse(os.path.exists(self.component))
        self.assertFalse(os.path.exists(os.path.join(self.bin, "emoji-picker")))

    def install_use_uninstall(self, *extra):
        self.install()
        self.ibus_lists("xkb:us::eng", "emoji-picker:us")
        self.finish()
        self.use_the_app()
        return self.uninstall(*extra)

    def test_uninstall_leaves_no_trace_but_your_history(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        files, settings = self.snapshot()
        self.install_use_uninstall()
        files_after, settings_after = self.snapshot()
        # no default is written down as the user's own value; no empty folder is left
        self.assertEqual(settings_after, settings)
        kept = files_after - files
        self.assertTrue(kept, "history should be kept")
        self.assertTrue(all(p.startswith("state") for p in kept), sorted(kept))
        self.assertFalse(files - files_after)
        self.assertNotIn("state/emoji-picker/created-dirs", kept)

    def test_purge_leaves_no_trace_at_all(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        before = self.snapshot()
        self.install_use_uninstall("--purge")
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_keeps_folders_that_were_there_before(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        for d in ("root/usr/local/share/applications", "config/autostart", "root/usr/share/ibus/component"):
            os.makedirs(os.path.join(self.tmp, d))
        before = self.snapshot()
        self.install_use_uninstall("--purge")
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_twice_and_dry_run_change_nothing(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        self.install()
        before = self.snapshot()
        self.uninstall("--dry-run")
        self.assertEqual(self.snapshot(), before)
        self.uninstall()
        after = self.snapshot()
        self.run_script([os.path.join(ROOT_DIR, "uninstall.sh"), "--root", self.root])
        self.assertEqual(self.snapshot(), after)

    def test_a_later_install_backs_up_the_settings_of_then(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        self.install()
        self.uninstall()
        self.set(SRC, "sources", "[('xkb', 'de')]")
        self.install()
        state = os.path.join(self.tmp, "state/emoji-picker")
        with open(os.path.join(state, "backup/input-sources.txt")) as f:
            self.assertEqual(f.read().strip(), "[('xkb', 'de')]")
        old = [d for d in os.listdir(state) if d.startswith("backup-until-")]
        self.assertEqual(len(old), 1)
        with open(os.path.join(state, old[0], "input-sources.txt")) as f:
            self.assertEqual(f.read().strip(), "[('xkb', 'us')]")

    def test_finish_setup_waits_and_leaves_sources_when_ibus_never_lists(self):
        self.set(SRC, "sources", "[('xkb', 'de'), ('ibus', 'mozc-jp')]")
        self.install()
        self.env["EMOJI_PICKER_SETUP_WAIT"] = "1.5"
        r = self.run_script([os.path.join(self.bin, "emoji-picker"), "--finish-setup"], ok=False)
        self.assertEqual(r.returncode, 1)
        with open(os.path.join(self.tmp, "state/emoji-picker/setup.log")) as f:
            self.assertIn("will retry next login", f.read())
        self.assertEqual(self.get(SRC, "sources"), "[('xkb', 'de'), ('ibus', 'mozc-jp')]")
        self.assertTrue(os.path.exists(self.autostart))

    def test_reinstall_converts_at_once_and_keeps_two_versions(self):
        self.set(SRC, "sources", "[('xkb', 'us'), ('ibus', 'mozc-jp')]")
        self.install()
        self.ibus_lists("emoji-picker:us", "mozc-jp")
        out = self.install().stdout
        self.assertNotIn("Log out", out)
        self.assertEqual(self.get(SRC, "sources"), "[('ibus', 'emoji-picker:us'), ('ibus', 'mozc-jp')]")
        self.assertFalse(os.path.exists(self.autostart))
        self.install()
        self.assertEqual(len(self.versions()), 2)
        target = os.readlink(os.path.join(self.lib, "current"))
        self.assertIn(os.path.basename(target), self.versions())

    def test_prototype_upgrade_keeps_inserting_until_login(self):
        self.set(SRC, "sources", "[('ibus', 'emoji-picker'), ('xkb', 'us')]")
        self.set(KB_ONE, "name", "Emoji Picker")
        self.set(KB_ONE, "command", "/home/someone/emoji-picker/bin/emoji-picker")
        self.set(KB_ONE, "binding", "<Control><Alt>e")
        self.set(KB, "custom-keybindings", f"['{KB_PATH}']")
        self.ibus_lists("emoji-picker", "xkb:us::eng")   # the running daemon has the old engine
        out = self.install().stdout
        self.assertIn("Enter keeps typing emoji as before", out)
        self.assertEqual(self.get(SRC, "sources"), "[('ibus', 'emoji-picker'), ('xkb', 'us')]")
        self.assertEqual(self.get(KB_ONE, "binding"), "'<Super>period'")
        self.ibus_lists("emoji-picker:us", "xkb:us::eng")  # after the login
        self.finish()
        self.assertEqual(self.get(SRC, "sources"), "[('ibus', 'emoji-picker:us')]")

    def test_second_user_keeps_working_after_first_uninstalls(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        os.makedirs(os.path.join(self.lib, "users"))
        with open(os.path.join(self.lib, "users", "99999"), "w") as f:
            f.write("de+nodeadkeys\n")
        self.install()
        with open(self.component) as f:
            xml = f.read()
        self.assertIn("emoji-picker:us<", xml)
        self.assertIn("emoji-picker:de+nodeadkeys<", xml)
        self.uninstall()
        with open(self.component) as f:
            xml = f.read()
        self.assertNotIn("emoji-picker:us<", xml)
        self.assertIn("emoji-picker:de+nodeadkeys<", xml)
        self.assertTrue(os.path.exists(os.path.join(self.bin, "emoji-picker")))
        self.assertEqual(self.get(SRC, "sources"), "[('xkb', 'us')]")

    def test_refuses_a_foreign_shortcut_at_our_path(self):
        self.set(KB_ONE, "name", "Something Else")
        before = self.get(SRC, "sources")
        r = self.install(ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing was changed", r.stderr)
        self.assertFalse(os.path.exists(self.root))
        self.assertEqual(self.get(SRC, "sources"), before)

    def test_refuses_our_name_on_someone_elses_command(self):
        self.set(KB_ONE, "name", "Emoji Picker")
        self.set(KB_ONE, "command", "/usr/bin/gnome-characters")
        r = self.install(ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.get(KB_ONE, "command"), "'/usr/bin/gnome-characters'")
        self.assertFalse(os.path.exists(self.root))

    def test_dry_run_changes_nothing(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        keyfile = os.path.join(self.tmp, "config/glib-2.0/settings/keyfile")
        with open(keyfile) as f:
            before = f.read()
        self.install("--dry-run")
        with open(keyfile) as f:
            self.assertEqual(f.read(), before)
        self.assertFalse(os.path.exists(self.root))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "state/emoji-picker")))

    def test_other_shortcut_leaves_ibus_hotkey_alone(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        self.install("--shortcut", "<Control><Alt>e")
        self.assertEqual(self.get(HOTKEY, "hotkey"), "['<Super>period', '<Super>semicolon']")
        self.assertEqual(self.get(KB_ONE, "binding"), "'<Control><Alt>e'")
        with open(os.path.join(self.tmp, "state/emoji-picker/installed.json")) as f:
            self.assertFalse(json.load(f)["removed_ibus_hotkey"])

    def test_warns_when_another_custom_shortcut_uses_the_key(self):
        p = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
        self.set(f"{KB}.custom-keybinding:{p}", "name", "Screenshot tool")
        self.set(f"{KB}.custom-keybinding:{p}", "binding", "<Super>period")
        self.set(KB, "custom-keybindings", f"['{p}']")
        out = self.install().stdout
        self.assertIn("WARNING: <Super>period is also used by", out)
        self.assertIn("Screenshot tool", out)
        self.assertIn(p, self.get(KB, "custom-keybindings"))   # theirs is kept

    def test_switching_to_another_key_gives_super_dot_back(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        self.install()
        self.assertEqual(self.get(HOTKEY, "hotkey"), "['<Super>semicolon']")
        self.install("--shortcut", "<Control><Alt>e")
        self.assertEqual(self.get(HOTKEY, "hotkey"), "['<Super>period', '<Super>semicolon']")
        self.uninstall()
        self.assertEqual(self.get(HOTKEY, "hotkey"), "['<Super>period', '<Super>semicolon']")

    def test_prototype_with_only_its_engine_keeps_its_layout(self):
        # a prototype user who removed the plain layout: the old engine typed German
        comp_dir = os.path.dirname(self.component)
        os.makedirs(comp_dir)
        with open(self.component, "w") as f:
            f.write("<component><engines><engine><name>emoji-picker</name><language>other</language>"
                    "<layout>de</layout>\n<layout_variant>nodeadkeys</layout_variant></engine>"
                    "</engines></component>")
        self.set(SRC, "sources", "[('ibus', 'emoji-picker')]")
        self.ibus_lists("emoji-picker")
        self.install()
        with open(self.component) as f:
            self.assertIn("<name>emoji-picker:de+nodeadkeys</name>", f.read())
        self.assertEqual(self.get(SRC, "sources"), "[('ibus', 'emoji-picker')]")  # until login
        self.ibus_lists("emoji-picker:de+nodeadkeys")
        self.finish()
        self.assertEqual(self.get(SRC, "sources"),
                         "[('ibus', 'emoji-picker:de+nodeadkeys'), ('xkb', 'de+nodeadkeys')]")
        self.uninstall()
        self.assertEqual(self.get(SRC, "sources"), "[('xkb', 'de+nodeadkeys')]")

    def test_uninstall_does_not_duplicate_a_readded_layout(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        self.install()
        self.set(SRC, "sources", "[('ibus', 'emoji-picker:us'), ('xkb', 'us')]")
        self.uninstall()
        self.assertEqual(self.get(SRC, "sources"), "[('xkb', 'us')]")

    def test_setup_from_the_installed_copy_adds_a_new_layout(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        self.install()
        self.set(SRC, "sources", "[('xkb', 'us'), ('xkb', 'de')]")
        self.run_script([os.path.join(self.bin, "emoji-picker"), "--setup", "--root", self.root])
        with open(self.component) as f:
            xml = f.read()
        self.assertIn("emoji-picker:de<", xml)
        with open(os.path.join(self.lib, "current", "VERSION")) as f:
            self.assertNotIn("nogit", f.read())   # the commit carried over from the first install

    def test_uninstall_keeps_a_shortcut_the_user_repointed(self):
        self.set(SRC, "sources", "[('xkb', 'us')]")
        self.install()
        self.set(KB_ONE, "command", "/usr/bin/gnome-characters")
        self.uninstall()
        self.assertEqual(self.get(KB_ONE, "command"), "'/usr/bin/gnome-characters'")


if __name__ == "__main__":
    unittest.main()
