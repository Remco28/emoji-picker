"""emoji-picker: open the picker window (bound to a shortcut by install.sh)."""
import time

T0 = time.monotonic()

import argparse  # noqa: E402
import sys  # noqa: E402

from . import __version__  # noqa: E402

APP_ID = "io.github.remco28.EmojiPicker"


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="emoji-picker", description=__doc__)
    ap.add_argument("--query", default="", help="start with this search text")
    ap.add_argument("--print", dest="print_only", action="store_true",
                    help="print the chosen emoji instead of inserting it")
    ap.add_argument("--version", action="version", version=f"emoji-picker {__version__}")
    ap.add_argument("--doctor", action="store_true",
                    help="print what is installed and active, for bug reports")
    ap.add_argument("--setup", nargs=argparse.REMAINDER, metavar="INSTALL_OPTIONS",
                    help="run the installer again (after adding a keyboard layout); "
                         "takes install.sh options such as --dry-run")
    ap.add_argument("--finish-setup", action="store_true",
                    help="(run once at login by the installer) switch keyboards to the emoji ones")
    # test hooks (not for everyday use)
    ap.add_argument("--screenshot", help=argparse.SUPPRESS)
    ap.add_argument("--keys", help=argparse.SUPPRESS)
    ap.add_argument("--quit-after-map", action="store_true", help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.doctor or args.finish_setup or args.setup is not None:
        from . import setup_steps
        if args.setup is not None:
            return setup_steps.run_installer(args.setup)
        return setup_steps.doctor() if args.doctor else setup_steps.finish_setup()
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Graphene", "1.0")
    from gi.repository import Adw, Gio, GLib, Graphene, Gtk

    from . import fonts
    from .data import load_emoji, load_enrichment
    from .search import Index
    from .usage import Usage
    from .window import PickerWindow, log

    timings = {"imports": time.monotonic() - T0}
    testing = bool(args.screenshot or args.keys or args.quit_after_map or args.print_only)
    flags = Gio.ApplicationFlags.NON_UNIQUE if testing else Gio.ApplicationFlags.DEFAULT_FLAGS
    app = Adw.Application(application_id=APP_ID, flags=flags)
    state = {}

    def screenshot(win, path):
        w, h = win.get_width(), win.get_height()
        snap = Gtk.Snapshot()
        Gtk.WidgetPaintable.new(win).snapshot(snap, w, h)
        node = snap.to_node()
        rect = Graphene.Rect().init(0, 0, w, h)
        win.get_renderer().render_texture(node, rect).save_to_png(path)
        print(f"screenshot: {path}", flush=True)

    def run_keys(win, spec):
        from gi.repository import Gdk
        names = {"Down": Gdk.KEY_Down, "Up": Gdk.KEY_Up, "Left": Gdk.KEY_Left, "Right": Gdk.KEY_Right,
                 "Tab": Gdk.KEY_Tab, "Return": Gdk.KEY_Return, "Escape": Gdk.KEY_Escape,
                 "Page_Down": Gdk.KEY_Page_Down, "Page_Up": Gdk.KEY_Page_Up}
        for k in spec.split(","):
            k = k.strip()
            if k.startswith("type:"):
                win.entry.set_text(k[5:])
            elif k == "Ctrl+c":
                win._on_key(None, Gdk.KEY_c, 0, Gdk.ModifierType.CONTROL_MASK)
            elif k in ("Ctrl+Up", "Ctrl+Down"):
                win._on_key(None, names[k[5:]], 0, Gdk.ModifierType.CONTROL_MASK)
            else:
                win._on_key(None, names[k], 0, 0)
            if not win.get_visible() or app.get_windows() == []:
                break

    def on_activate(app):
        if app.get_windows():
            win = app.get_windows()[0]
            if win.mode in ("inserting", "copied"):
                win.reopen_requested = True   # opens once this one has finished
            else:
                win.present()
            return
        t = time.monotonic()
        data = load_emoji()
        enrichment = load_enrichment()
        cutoff = fonts.max_version(data["emoji"])
        usage = Usage()
        timings["data"] = time.monotonic() - t
        t = time.monotonic()
        index = Index(data, enrichment, usage, max_version=cutoff, lazy=True)
        timings["index"] = time.monotonic() - t
        t = time.monotonic()
        def reopen():
            again = PickerWindow(app, index, usage, {"reopen": reopen})
            again.present()

        win = PickerWindow(app, index, usage, {"query": args.query, "print_only": args.print_only,
                                               "reopen": reopen})
        timings["window"] = time.monotonic() - t
        state["win"] = win

        def first_frame(*_a):
            if "shown" in timings:
                return
            timings["shown"] = time.monotonic() - T0
            GLib.idle_add(index.build)  # search index after the first frame
            summary = " ".join(f"{k}={v * 1000:.0f}ms" for k, v in timings.items())
            log(f"startup {summary} font_cutoff={cutoff} emoji={len(index.emoji)}")
            if testing:
                print(f"startup {summary}", flush=True)
            if args.keys:
                GLib.timeout_add(150, lambda: (run_keys(win, args.keys), False)[1])
            if args.screenshot:
                GLib.timeout_add(600, lambda: (screenshot(win, args.screenshot), app.quit(), False)[2])
            elif args.quit_after_map:
                GLib.idle_add(lambda: (app.quit(), False)[1])

        win.connect("map", lambda *_a: win.get_frame_clock().connect("after-paint", first_frame))
        win.present()

    app.connect("activate", on_activate)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
