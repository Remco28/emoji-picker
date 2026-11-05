"""The picker window: a search box over a keyboard-navigable chart of emoji."""
import json
import os
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import design, insert  # noqa: E402
from .layout import SIDE_PADDING, columns  # noqa: E402
from .nav import Grid, Pointer  # noqa: E402
from .search import Section  # noqa: E402

TONE_NAMES = {1: "light", 2: "medium-light", 3: "medium", 4: "medium-dark", 5: "dark"}
HINT = "Enter insert · Tab skin tones · Ctrl+C copy · Esc close"


def state_dir():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "emoji-picker")


def log(msg):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        t = time.time()
        with open(os.path.join(state_dir(), "picker.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S', time.localtime(t))}.{int(t * 1000) % 1000:03d} {msg}\n")
    except OSError:
        pass


class Settings:
    def __init__(self):
        self.path = os.path.join(state_dir(), "settings.json")
        self.width, self.height = 760, 560
        self.emoji_size = design.EMOJI_DEFAULT
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            self.width = max(design.MIN_WIDTH, int(raw.get("width", self.width)))
            self.height = max(design.MIN_HEIGHT, int(raw.get("height", self.height)))
            if raw.get("emoji_size") in design.EMOJI_SIZES:
                self.emoji_size = raw["emoji_size"]
        except (OSError, ValueError, TypeError):
            pass

    def save(self):
        try:
            os.makedirs(state_dir(), exist_ok=True)
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"width": self.width, "height": self.height,
                           "emoji_size": self.emoji_size}, f)
            os.replace(self.path + ".tmp", self.path)
        except OSError:
            pass


class Chart(Gtk.Box):
    """Vertical box of sections that reports its width, to recompute columns."""
    __gtype_name__ = "EmojiPickerChart"

    def __init__(self, on_width):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.on_width = on_width
        self.add_css_class("ep-chart")

    def do_size_allocate(self, width, height, baseline):
        Gtk.Box.do_size_allocate(self, width, height, baseline)
        self.on_width(width)


class PickerWindow(Adw.ApplicationWindow):
    def __init__(self, app, index, usage, options):
        self.settings = Settings()
        super().__init__(application=app, title="Emoji Picker",
                         default_width=self.settings.width, default_height=self.settings.height)
        self.add_css_class("emoji-picker")
        self.set_size_request(design.MIN_WIDTH, design.MIN_HEIGHT)
        self.index, self.usage, self.options = index, usage, options
        self.by_hex = {e["h"]: i for i, e in enumerate(index.emoji)}
        self.mode = "pick"      # pick | tones | copied | inserting
        self.cells = []         # flat display order: (FlowBoxChild, emoji index, char)
        self.flowboxes = []
        self.highlight = None
        self.columns = columns(self.settings.width + SIDE_PADDING,
                               design.cell_width(self.settings.emoji_size))
        self.grid = Grid([], self.columns)
        self.saved_query_state = None
        self.tone_base = None

        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._apply_css()

        # search box: a plain Entry so it can use GTK's simple input method,
        # which keeps IBus (and so our engine) from ever seeing the picker
        self.entry = Gtk.Entry(placeholder_text="Search emoji, or type a sentence",
                               hexpand=True)
        self.entry.set_property("im-module", "gtk-im-context-simple")
        self.entry.add_css_class("ep-search")
        self.entry.connect("changed", self._on_changed)

        header = Adw.HeaderBar()
        header.set_title_widget(self.entry)

        self.chart = Chart(self._on_chart_width)
        self.scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroller.set_child(self.chart)
        self.chart.set_margin_start(SIDE_PADDING // 2)
        self.chart.set_margin_end(SIDE_PADDING // 2)
        self.chart.set_margin_bottom(design.S3)

        self.status_name = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)  # END
        self.status_hint = Gtk.Label(label=HINT, xalign=1)
        self.status_hint.add_css_class("ep-hint")
        status = Gtk.Box(spacing=design.S3)
        status.add_css_class("ep-status")
        status.append(self.status_name)
        status.append(self.status_hint)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self.scroller)
        body.append(status)
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(body)
        self.set_content(view)

        # window-level pointer tracking runs before the cells' hover handlers
        self.pointer = Pointer()
        moves = Gtk.EventControllerMotion()
        moves.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        moves.connect("enter", lambda _c, x, y: self.pointer.enter(x, y))
        moves.connect("motion", lambda _c, x, y: self.pointer.motion(x, y))
        moves.connect("leave", lambda _c: self.pointer.leave())
        self.add_controller(moves)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("close-request", self._on_close_request)
        self.connect("notify::is-active", self._on_active)

        self._show_results(self.options.get("query", ""))
        if self.options.get("query"):
            self.entry.set_text(self.options["query"])
        self.entry.grab_focus_without_selecting()
        self.entry.set_position(-1)

    # ---- building the chart ----------------------------------------------

    def _apply_css(self):
        self.css.load_from_string(design.css(self.settings.emoji_size))

    def _clear(self):
        child = self.chart.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.chart.remove(child)
            child = nxt
        self.cells, self.flowboxes = [], []

    def _add_section(self, title, chars_and_ids):
        if not chars_and_ids:
            return
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("ep-section")
        self.chart.append(label)
        fb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                         activate_on_single_click=True, column_spacing=0, row_spacing=0,
                         min_children_per_line=self.columns, max_children_per_line=self.columns)
        fb.connect("child-activated", self._on_activated)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion, fb)
        fb.add_controller(motion)
        right = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right.connect("pressed", self._on_right_click, fb)
        fb.add_controller(right)
        for n, (char, idx) in enumerate(chars_and_ids):
            cell = Gtk.Label(label=char)
            cell.add_css_class("ep-cell")
            fb.append(cell)
            child = fb.get_child_at_index(n)
            child.set_cursor_from_name("pointer")
            self.cells.append((child, idx, char))
        self.chart.append(fb)
        self.flowboxes.append(fb)

    def _display_char(self, i):
        e = self.index.emoji[i]
        skins = e.get("sk")
        if not skins:
            return e["e"]
        kinds = {"pair" if isinstance(s[1], list) else "single" for s in skins}
        tone = self.usage.tone_for(e["h"], kinds)
        if tone is None:
            return e["e"]
        for char, t, _v in skins:
            if t == tone:
                return char
        return e["e"]

    def _finish_build(self, sections):
        self._sections = sections
        self.grid = Grid([len(s.items) for s in sections], self.columns)
        self._set_highlight(0 if self.cells else None)

    FIRST_CELLS = 360  # browse cells built before the first frame; the rest in idle time

    def _show_results(self, query):
        t = time.perf_counter()
        self._build_token = getattr(self, "_build_token", 0) + 1
        self._clear()
        secs = self.index.sections(query, self.columns) if query.strip() else None
        if secs is None:
            secs = self._browse_sections()
            self._build_staged(secs, self._build_token)
            return
        if not secs:
            empty = Gtk.Label(label="No emoji match that. Try another word.")
            empty.add_css_class("ep-empty")
            self.chart.append(empty)
        for s in secs:
            self._add_section(s.title, [(self._display_char(i), i) for i in s.items])
        self._finish_build(secs)
        self.last_build_ms = (time.perf_counter() - t) * 1000

    def _build_staged(self, secs, token):
        """Add the browse sections: enough for the first screens now, the rest
        one section per idle callback, so the window appears quickly."""
        built, done = 0, []
        queue = list(secs)
        while queue and built < self.FIRST_CELLS:
            s = queue.pop(0)
            self._add_section(s.title, [(self._display_char(i), i) for i in s.items])
            done.append(s)
            built += len(s.items)
        self._finish_build(done)

        def more():
            if token != self._build_token or not queue or self.mode != "pick":
                return False
            s = queue.pop(0)
            self._add_section(s.title, [(self._display_char(i), i) for i in s.items])
            done.append(s)
            keep = self.highlight
            self.grid = Grid([len(x.items) for x in done], self.columns)
            self._sections = list(done)
            if keep is not None:
                self.highlight = keep
            return bool(queue)

        GLib.idle_add(more, priority=GLib.PRIORITY_LOW)

    def _browse_sections(self):
        out = []
        recent = [self.by_hex[h] for h in self.usage.recent() if h in self.by_hex]
        frequent = [self.by_hex[h] for h in self.usage.frequent() if h in self.by_hex]
        if recent:
            out.append(Section("Recent", recent, kind="recent"))
        if frequent:
            out.append(Section("Frequent", frequent, kind="frequent"))
        groups = {}
        for i, e in enumerate(self.index.emoji):
            groups.setdefault(e["g"], []).append(i)
        for g in sorted(groups):
            name = self.index.groups.get(str(g), "").replace("-", " & ").replace("smileys & emotion", "smileys & emotion")
            out.append(Section(name.capitalize(), groups[g], kind="browse"))
        return out

    def _on_chart_width(self, width):
        cols = columns(width + SIDE_PADDING, design.cell_width(self.settings.emoji_size))
        if cols != self.columns:
            self.columns = cols
            GLib.idle_add(self._relayout)

    def _relayout(self):
        for fb in self.flowboxes:
            fb.set_min_children_per_line(self.columns)
            fb.set_max_children_per_line(self.columns)
        if hasattr(self, "_sections"):
            keep = self.highlight
            self.grid = Grid([len(s.items) for s in self._sections], self.columns)
            self._set_highlight(keep)
        return False

    # ---- highlight and status -------------------------------------------

    def _set_highlight(self, k):
        if self.highlight is not None and self.highlight < len(self.cells):
            self.cells[self.highlight][0].remove_css_class("ep-highlight")
        self.highlight = k
        if k is None or not self.cells:
            self.status_name.set_label("")
            return
        child, idx, char = self.cells[k]
        child.add_css_class("ep-highlight")
        self._update_status(idx, char)
        GLib.idle_add(self._scroll_to, child, k)

    def _update_status(self, idx, char):
        e = self.index.emoji[idx]
        code = f"  :{e['sc'][0]}:" if e.get("sc") else ""
        tones = "  · Tab for skin tones" if e.get("sk") and self.mode == "pick" else ""
        self.status_name.set_label(f"{char}  {e['n']}{code}{tones}")

    def _scroll_to(self, child, k):
        adj = self.scroller.get_vadjustment()
        ok, rect = child.compute_bounds(self.chart)
        if not ok:
            return False
        top, bottom = rect.origin.y, rect.origin.y + rect.size.height
        if k == 0:
            adj.set_value(0)
        elif top < adj.get_value():
            adj.set_value(max(0, top - design.S6))
        elif bottom > adj.get_value() + adj.get_page_size():
            adj.set_value(bottom - adj.get_page_size() + design.S3)
        return False

    # ---- input -------------------------------------------------------------

    def _on_changed(self, _entry):
        if self.mode != "pick":
            return
        self._show_results(self.entry.get_text())

    def _on_motion(self, _ctrl, x, y, fb):
        if not self.pointer.moved:   # the chart moved under a still mouse
            return
        child = fb.get_child_at_pos(x, y)
        if child is None:
            return
        for k, (c, _i, _ch) in enumerate(self.cells):
            if c is child and k != self.highlight:
                self._set_highlight(k)
                break

    def _on_activated(self, _fb, child):
        for k, (c, _i, _ch) in enumerate(self.cells):
            if c is child:
                self._set_highlight(k)
                self._choose()
                return

    def _on_right_click(self, _gesture, _n, x, y, fb):
        child = fb.get_child_at_pos(x, y)
        for k, (c, _i, _ch) in enumerate(self.cells):
            if c is child:
                self._set_highlight(k)
                self._open_tones()
                return

    def _on_key(self, _ctrl, keyval, _keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if self.mode == "copied":
            self._quit()
            return True
        if self.mode == "inserting":
            return True
        moves = {Gdk.KEY_Left: "left", Gdk.KEY_Right: "right", Gdk.KEY_Up: "up",
                 Gdk.KEY_Down: "down", Gdk.KEY_Page_Up: "page_up", Gdk.KEY_Page_Down: "page_down"}
        if keyval in moves:
            page = max(1, int(self.scroller.get_vadjustment().get_page_size()
                              // design.cell_width(self.settings.emoji_size)) - 1)
            self._set_highlight(self.grid.move(self.highlight, moves[keyval], page))
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter):
            self._choose()
            return True
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            if self.mode == "tones":
                self._close_tones()
            else:
                self._open_tones()
            return True
        if keyval == Gdk.KEY_Escape:
            if self.mode == "tones":
                self._close_tones()
            elif self.entry.get_text():
                self.entry.set_text("")
            else:
                self._quit()
            return True
        if ctrl and keyval in (Gdk.KEY_c, Gdk.KEY_C) and not has_selection(self.entry):
            self._copy_highlighted()
            return True
        if ctrl and keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self._zoom(+1)
            return True
        if ctrl and keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self._zoom(-1)
            return True
        if ctrl and keyval == Gdk.KEY_0:
            self._zoom(0)
            return True
        if self.mode == "tones":
            return True  # typing does nothing while choosing a tone
        return False  # let the search box have it

    def _zoom(self, step):
        sizes = design.EMOJI_SIZES
        cur = sizes.index(self.settings.emoji_size)
        new = sizes.index(design.EMOJI_DEFAULT) if step == 0 else max(0, min(len(sizes) - 1, cur + step))
        self.settings.emoji_size = sizes[new]
        self._apply_css()
        self._on_chart_width(self.chart.get_width())

    # ---- skin tones -------------------------------------------------------

    def _open_tones(self):
        if self.highlight is None or self.mode != "pick":
            return
        idx = self.cells[self.highlight][1]
        e = self.index.emoji[idx]
        if not e.get("sk"):
            self.status_name.set_label(f"{e['e']}  {e['n']} has no skin tones")
            return
        self.saved_query_state = (self.highlight,)
        self.tone_base = idx
        self.mode = "tones"
        self._clear()
        items = [(e["e"], idx)] + [(s[0], idx) for s in e["sk"]]
        self._tone_values = [None] + [s[1] for s in e["sk"]]
        self._add_section(f"Skin tones for {e['n']}  (Enter to insert, Tab or Esc to go back)", items)
        self._sections = [Section("tones", [i for _c, i in items])]
        self.grid = Grid([len(items)], self.columns)
        current = self.usage.tone_for(e["h"], {"pair" if isinstance(s[1], list) else "single"
                                                for s in e["sk"]})
        start = self._tone_values.index(current) if current in self._tone_values else 0
        self._set_highlight(start)

    def _close_tones(self):
        self.mode = "pick"
        keep = self.saved_query_state[0] if self.saved_query_state else 0
        self._show_results(self.entry.get_text())
        if self.cells:
            self._set_highlight(min(keep, len(self.cells) - 1))

    # ---- choosing, inserting, copying --------------------------------------

    def _chosen(self):
        if self.highlight is None or not self.cells:
            return None, None, None
        _child, idx, char = self.cells[self.highlight]
        tone = None
        if self.mode == "tones":
            tone = self._tone_values[self.highlight]
        return idx, char, tone

    def _record(self, idx, tone):
        h = self.index.emoji[idx]["h"]
        self.usage.record(h)
        if self.mode == "tones":
            if tone is None:
                self.usage.tones.pop(h, None)
            else:
                self.usage.set_tone(h, tone)
        self.usage.save()

    def _choose(self):
        idx, char, tone = self._chosen()
        if idx is None:
            return
        self._record(idx, tone)
        if self.options.get("print_only"):
            print(char, flush=True)
            self._quit()
            return
        ok, why, st = insert.preflight()
        log(f"chose {char!r}; preflight ok={ok} {why} status={st}")
        if not ok:
            self._copy(char, reason=why)
            return
        self.mode = "inserting"
        self.settings.width, self.settings.height = self.get_width(), self.get_height()
        self.settings.save()
        self.set_visible(False)
        insert.Inserter(char, st["gen"], self._inserted, log=log).start()

    def _inserted(self, result, detail):
        if result != "inserted":
            insert.notify("Could not insert the emoji",
                          "This app did not accept it. Open the picker again and press "
                          "Ctrl+C to copy it instead.")
        self._quit()

    def _copy_highlighted(self):
        idx, char, tone = self._chosen()
        if idx is None:
            return
        self._record(idx, tone)
        self._copy(char, close_after_ms=1200)

    def _copy(self, char, reason=None, close_after_ms=None):
        """Copy while the window still has focus, then confirm by reading it back.

        With close_after_ms the window closes by itself once the copy is
        confirmed (Ctrl+C); otherwise it stays until the next key, so a
        fallback message can be read."""
        clipboard = self.get_display().get_clipboard()
        clipboard.set(char)
        self.mode = "copied"

        def check(cb, res):
            try:
                got = cb.read_text_finish(res)
            except GLib.Error:
                got = None
            if got == char:
                msg = f"Copied {char}: press Ctrl+V to paste (Ctrl+Shift+V in a terminal)."
                if reason:
                    msg = f"Could not insert directly ({reason}). " + msg
                msg += "  Any key closes."
            else:
                msg = "Copying failed: the clipboard still holds something else."
            log(f"copy {char!r}: {'confirmed' if got == char else 'NOT confirmed'}")
            self.status_name.set_label(msg if not close_after_ms or got != char
                                       else f"Copied {char}: press Ctrl+V to paste.")
            self.status_hint.set_label("")
            if close_after_ms and got == char:
                GLib.timeout_add(close_after_ms, lambda: (self._quit(), False)[1])

        clipboard.read_text_async(None, check)

    # ---- closing -------------------------------------------------------------

    def _on_active(self, *_a):
        # Clicking another window closes the picker, like a menu.
        if not self.is_active() and self.mode == "pick" and getattr(self, "_was_active", False):
            self._quit()
        if self.is_active():
            self._was_active = True

    def _on_close_request(self, *_a):
        self.settings.width, self.settings.height = self.get_width(), self.get_height()
        self.settings.save()
        return False

    def _quit(self):
        self._on_close_request()
        app = self.get_application()
        GLib.timeout_add(300 if self.mode == "copied" else 0, lambda: (app.quit(), False)[1])


def has_selection(entry):
    """True when the search box has selected text (then Ctrl+C copies that).

    PyGObject's GTK 4 override returns () or (start, end); a different
    binding could return (flag, start, end). Handle both."""
    bounds = entry.get_selection_bounds()
    if not bounds:
        return False
    if isinstance(bounds[0], bool):
        return bounds[0]
    return bounds[0] != bounds[1]
