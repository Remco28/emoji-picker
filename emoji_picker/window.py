"""The picker window: a search box over a keyboard-navigable chart of emoji,
with a card on the right that previews the highlighted emoji."""
import json
import os
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import design, insert  # noqa: E402
from .layout import columns  # noqa: E402
from .nav import Grid, Pointer  # noqa: E402
from .search import Section  # noqa: E402

TONE_NAMES = {1: "light", 2: "medium-light", 3: "medium", 4: "medium-dark", 5: "dark"}
PLACEHOLDER = "Search, or try ‘food’"

# The key hints in the bottom bar, per state: (key, what it does)
HINTS = {
    "browse": [("Enter", "insert"), ("Ctrl+C", "copy"), ("Ctrl+↑↓", "jump"), ("Esc", "close")],
    "search": [("Enter", "insert"), ("Ctrl+C", "copy"), ("Ctrl+↑↓", "jump"), ("Esc", "clear")],
    "search1": [("Enter", "insert"), ("Ctrl+C", "copy"), ("Esc", "clear")],  # one section: no jump
    "empty": [("Esc", "clear")],
    "tones": [("Enter", "insert"), ("Ctrl+C", "copy"), ("Tab or Esc", "back")],
    "copied": [("Any key", "closes")],
    "closing": [],
}


def state_dir():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "emoji-picker")


LOG_MAX = 1_000_000


def log(msg):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        path = os.path.join(state_dir(), "picker.log")
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX:
            os.replace(path, path + ".1")
        t = time.time()
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S', time.localtime(t))}.{int(t * 1000) % 1000:03d} {msg}\n")
    except OSError:
        pass


def hints_markup(state):
    parts = [f'<span weight="600">{GLib.markup_escape_text(k)}</span> '
             f'<span fgalpha="70%">{GLib.markup_escape_text(a)}</span>' for k, a in HINTS[state]]
    return '<span fgalpha="40%">   ·   </span>'.join(parts) or " "


def card_text(e):
    """(name, detail line) for the card: names start with a capital, and
    flags put the country first ("Azerbaijan", "Flag · :azerbaijan:")."""
    name, kind = e["n"], ""
    if name.startswith("flag: "):
        name, kind = name[len("flag: "):], "Flag"
    name = name[:1].upper() + name[1:]
    code = f":{e['sc'][0]}:" if e.get("sc") else ""
    return name, " · ".join(x for x in (kind, code) if x)


def tone_text(tone):
    if tone is None:
        return "Default yellow"
    if isinstance(tone, list):
        a, b = (TONE_NAMES.get(t, "") for t in tone)
        return f"{a.capitalize()} skin tone" if a == b else f"{a.capitalize()} and {b} skin tones"
    return f"{TONE_NAMES.get(tone, '').capitalize()} skin tone"


class Settings:
    def __init__(self):
        self.path = os.path.join(state_dir(), "settings.json")
        self.width, self.height = design.DEFAULT_WIDTH, design.DEFAULT_HEIGHT
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


class Chart(Gtk.Widget):
    """The sections, in a column exactly as wide as the whole cells that fit,
    so cells are never stretched. Reports its width so the window can
    recompute the column count. (The window also hands leftover width to the
    card, so normally the chart is already a whole number of cells wide.)"""
    __gtype_name__ = "EmojiPickerChart"

    def __init__(self, on_width, cell):
        super().__init__()
        self.on_width = on_width
        self.cell = cell
        self.inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.inner.set_parent(self)
        self.add_css_class("ep-chart")

    def inner_width(self, width):
        return max(self.cell, min(width, columns(width, self.cell) * self.cell))

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            _m, nat, _b, _b2 = self.inner.measure(orientation, -1)
            return 0, nat, -1, -1
        width = self.inner_width(for_size) if for_size >= 0 else -1
        m, nat, _b, _b2 = self.inner.measure(orientation, width)
        return m, nat, -1, -1

    def do_size_allocate(self, width, height, _baseline):
        self.inner.allocate(self.inner_width(width), height, -1, None)
        self.on_width(width)

    def do_dispose(self):
        if self.inner is not None:
            self.inner.unparent()
            self.inner = None
        Gtk.Widget.do_dispose(self)


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
        self.section_labels = []
        self.highlight = None
        cell = design.cell_width(self.settings.emoji_size)
        self.columns = columns(design.chart_width(self.settings.width), cell)
        self.grid = Grid([], self.columns)
        self._sections = []
        self.saved_query_state = None
        self.tone_base = None

        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._apply_css()

        # search box: a plain Entry so it can use GTK's simple input method,
        # which keeps IBus (and so our engine) from ever seeing the picker
        self.entry = Gtk.Entry(placeholder_text=PLACEHOLDER, hexpand=True)
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.entry.set_property("im-module", "gtk-im-context-simple")
        self.entry.connect("changed", self._on_changed)

        # the top bar: the search box across the width, lined up with the
        # chart, and a close button only (the picker closes when it loses
        # focus, so minimise would close it too)
        bar = Gtk.Box(spacing=design.S3)
        for m in ("top", "bottom"):
            getattr(bar, f"set_margin_{m}")(design.S2)
        bar.set_margin_start(design.S3)
        bar.set_margin_end(design.S3)
        bar.append(self.entry)
        bar.append(Gtk.WindowControls(side=Gtk.PackType.END, decoration_layout=":close"))
        header = Gtk.WindowHandle(child=bar)

        # the chart, with the current section's title pinned over its top
        # and a fade where it continues below the bottom edge
        self.chart = Chart(self._on_chart_width, cell)
        self.chart.set_margin_start(design.S3)
        self.chart.set_margin_end(design.S3)
        self.chart.set_margin_bottom(design.S6)
        self.scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True,
                                           hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroller.set_child(self.chart)
        self.scroller.get_vadjustment().connect("value-changed", self._update_pinned)
        self.pinned_label = Gtk.Label(xalign=0, ellipsize=3, hexpand=True,  # END
                                      margin_start=design.S3, margin_end=design.S3)
        self.pinned_label.add_css_class("heading")
        self.pinned_label.add_css_class("ep-section")
        self.pinned = Gtk.Box(valign=Gtk.Align.START, can_target=False, visible=False)
        self.pinned.add_css_class("ep-pinned")
        self.pinned.append(self.pinned_label)
        fade = Gtk.Box(valign=Gtk.Align.END, height_request=design.FADE, can_target=False)
        fade.add_css_class("ep-fade")
        chart_area = Gtk.Overlay(hexpand=True)
        chart_area.set_child(self.scroller)
        chart_area.add_overlay(self.pinned)
        chart_area.add_overlay(fade)

        body = Gtk.Box()
        body.append(chart_area)
        self.card = self._build_card()
        body.append(self.card)
        # "No emoji found", centred over the whole body (the card is hidden then)
        self.empty = self._build_empty()
        body_area = Gtk.Overlay(child=body)
        body_area.add_overlay(self.empty)

        self.hints = Gtk.Label(xalign=0, use_markup=True, ellipsize=3)
        self.hints.add_css_class("caption")
        self.hints.add_css_class("ep-hints")

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(body_area)
        view.add_bottom_bar(self.hints)
        self.set_content(view)
        self._fix_hints_height()

        # the card's first width, before the chart reports its own
        extra = design.chart_width(self.settings.width) - self.columns * cell
        self.card.set_size_request(design.CARD_WIDTH + max(0, extra), -1)

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

    # ---- the card ------------------------------------------------------------

    def _build_card(self):
        def label(*classes, **kw):
            lab = Gtk.Label(justify=Gtk.Justification.CENTER, max_width_chars=1, **kw)
            for c in classes:
                lab.add_css_class(c)
            return lab

        self.card_emoji = label("ep-card-emoji", height_request=design.CARD_EMOJI_BOX)
        self.card_name = label("title-4", wrap=True, wrap_mode=2, lines=3, ellipsize=3)  # WORD_CHAR, END
        self.card_detail = label("monospace", "ep-muted", ellipsize=2)  # MIDDLE
        self.card_note = label("caption", "ep-muted", wrap=True)
        self.card_result = label("heading")
        self.card_result_detail = label("ep-muted", wrap=True)
        # full height, so its edge never moves as the text under the emoji
        # changes; long text (a copy fallback reason) scrolls inside it
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=design.CARD_WIDTH)
        card.add_css_class("card")
        for m in ("top", "end", "bottom"):
            getattr(card, f"set_margin_{m}")(design.S3)
        card.set_margin_start(design.S3)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=design.S1)
        for m in ("top", "start", "end", "bottom"):
            getattr(inner, f"set_margin_{m}")(design.S3)
        self.card_name.set_margin_top(design.S2)
        self.card_note.set_margin_top(design.S2)
        self.card_result.set_margin_top(design.S2)
        for w in (self.card_emoji, self.card_name, self.card_detail, self.card_note,
                  self.card_result, self.card_result_detail):
            inner.append(w)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True,
                                    child=inner)
        card.append(scroll)
        return card

    def _build_empty(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=design.S2,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                      can_target=False, visible=False)
        title = Gtk.Label(label="No emoji found")
        title.add_css_class("title-4")
        desc = Gtk.Label(label="Try another word, or a category like ‘food’.", wrap=True,
                         justify=Gtk.Justification.CENTER)
        desc.add_css_class("ep-muted")
        box.append(title)
        box.append(desc)
        return box

    def _fix_hints_height(self):
        """The bar keeps one height in every state (some key glyphs come from
        a taller fallback font)."""
        tallest = 0
        for state in HINTS:
            self.hints.set_markup(hints_markup(state))
            tallest = max(tallest, self.hints.measure(Gtk.Orientation.VERTICAL, -1)[1])
        self.hints.set_size_request(-1, tallest)

    def _show_card(self, idx=None, char="", note=""):
        if idx is None:
            name, detail = "", ""
        else:
            name, detail = card_text(self.index.emoji[idx])
        # with nothing highlighted the card keeps its place but is not drawn
        self.card.set_opacity(0 if idx is None else 1)
        self.empty.set_visible(idx is None and self.mode == "pick" and bool(self.entry.get_text().strip()))
        self.card_emoji.set_label(char)
        self.card_name.set_label(name)
        self.card_detail.set_label(detail)
        self.card_detail.set_visible(bool(detail))
        self.card_note.set_markup(note)
        self.card_note.set_visible(bool(note))
        for w in (self.card_result, self.card_result_detail):
            w.set_visible(False)

    def _card_result(self, title, detail, role):
        self.card_note.set_visible(False)
        self.card_result.set_label(title)
        for r in ("success", "error"):
            self.card_result.remove_css_class(r)
        self.card_result.add_css_class(role)
        self.card_result_detail.set_label(detail)
        self.card_result.set_visible(True)
        self.card_result_detail.set_visible(True)

    # ---- building the chart ----------------------------------------------

    def _apply_css(self):
        self.css.load_from_string(design.css(self.settings.emoji_size))

    def _clear(self):
        inner = self.chart.inner
        child = inner.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            inner.remove(child)
            child = nxt
        self.cells, self.flowboxes, self.section_labels = [], [], []

    def _add_section(self, title, chars_and_ids):
        if not chars_and_ids:
            return
        label = Gtk.Label(label=title, xalign=0, ellipsize=3)  # END
        label.add_css_class("heading")
        label.add_css_class("ep-section")
        self.chart.inner.append(label)
        self.section_labels.append(label)
        fb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                         activate_on_single_click=True, column_spacing=0, row_spacing=0,
                         min_children_per_line=1, max_children_per_line=self.columns)
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
            # screen readers say the name, not the glyph's codepoints
            child.update_property([Gtk.AccessibleProperty.LABEL], [self.index.emoji[idx]["n"]])
            self.cells.append((child, idx, char))
        self.chart.inner.append(fb)
        self.flowboxes.append(fb)

    @staticmethod
    def _title(s):
        # a line per search word is named by that word, in quotes, so it does
        # not read as a category
        return f"“{s.title}”" if s.kind == "concept" else s.title

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
        GLib.idle_add(self._update_pinned)

    FIRST_CELLS = 360  # browse cells built before the first frame; the rest in idle time

    def _show_results(self, query):
        t = time.perf_counter()
        self._build_token = getattr(self, "_build_token", 0) + 1
        self._clear()
        self.scroller.get_vadjustment().set_value(0)
        secs = self.index.sections(query, self.columns) if query.strip() else None
        if secs is None:
            secs = self._browse_sections()
            self._build_staged(secs, self._build_token)
            self._set_hints("browse")
            return
        for s in secs:
            self._add_section(self._title(s), [(self._display_char(i), i) for i in s.items])
        self._finish_build(secs)
        self._set_hints("empty" if not secs else "search" if len(secs) > 1 else "search1")
        self.last_build_ms = (time.perf_counter() - t) * 1000

    def _build_staged(self, secs, token):
        """Add the browse sections: enough for the first screens now, the rest
        one section per idle callback, so the window appears quickly."""
        built, done = 0, []
        queue = list(secs)
        while queue and built < self.FIRST_CELLS:
            s = queue.pop(0)
            self._add_section(self._title(s), [(self._display_char(i), i) for i in s.items])
            done.append(s)
            built += len(s.items)
        self._finish_build(done)

        def more():
            if token != self._build_token or not queue or self.mode != "pick":
                return False
            s = queue.pop(0)
            self._add_section(self._title(s), [(self._display_char(i), i) for i in s.items])
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
        # Recent is one line; Frequent leaves out what Recent already shows
        recent = [self.by_hex[h] for h in self.usage.recent() if h in self.by_hex][:self.columns]
        shown = set(recent)
        frequent = [self.by_hex[h] for h in self.usage.frequent()
                    if h in self.by_hex and self.by_hex[h] not in shown]
        if recent:
            out.append(Section("Recent", recent, kind="recent"))
        if frequent:
            out.append(Section("Frequent", frequent, kind="frequent"))
        groups = {}
        for i, e in enumerate(self.index.emoji):
            groups.setdefault(e["g"], []).append(i)
        for g in sorted(groups):
            name = self.index.groups.get(str(g), "").replace("-", " & ")
            out.append(Section(name.capitalize(), groups[g], kind="browse"))
        return out

    def _on_chart_width(self, width):
        # The card takes the width left over after whole cells, so the
        # chart's right edge and the card's left edge keep one gap. Measured
        # from the chart's real width (a classic scrollbar takes some).
        cell = design.cell_width(self.settings.emoji_size)
        card_now = self.card.get_size_request()[0]
        total = width + max(0, card_now - design.CARD_WIDTH)
        cols = columns(total, cell)
        if cols != self.columns:
            self.columns = cols
            GLib.idle_add(self._relayout)
        card = design.CARD_WIDTH + max(0, total - cols * cell)
        if card != card_now:
            GLib.idle_add(self.card.set_size_request, card, -1)  # not during allocation

    def _relayout(self):
        keep = self.highlight
        if self.mode == "pick":
            # Recent and the search lines are cut to the line width: rebuild
            self._show_results(self.entry.get_text())
            if keep is not None and self.cells:
                self._set_highlight(min(keep, len(self.cells) - 1))
            return False
        for fb in self.flowboxes:
            fb.set_max_children_per_line(self.columns)
        self.grid = Grid([len(s.items) for s in self._sections], self.columns)
        self._set_highlight(keep)
        return False

    # ---- the pinned title ------------------------------------------------

    def _label_y(self, label):
        ok, rect = label.compute_bounds(self.chart)
        return rect.origin.y if ok else None

    def _pinned_height(self):
        # follows the title's real line height (Large Text makes it taller)
        return self.pinned.get_height() or design.PINNED_HEIGHT

    def _update_pinned(self, *_a):
        value = self.scroller.get_vadjustment().get_value()
        title = None
        for label in self.section_labels:
            y = self._label_y(label)
            # a title takes over as soon as it slides under the pinned one
            if y is None or (title is not None and y >= value + self._pinned_height()):
                break
            title = label.get_label()
        self.pinned_label.set_label(title or "")
        self.pinned.set_visible(bool(title))
        if value > 0:
            self.pinned.add_css_class("ep-scrolled")
        else:
            self.pinned.remove_css_class("ep-scrolled")
        return False

    def _section_starts(self):
        starts, n = [], 0
        for s in self._sections:
            starts.append(n)
            n += len(s.items)
        return starts

    def _jump(self, step):
        """Ctrl+Up/Down: to the start of the previous or next section, its
        title under the pinned one. Up from inside a section goes to its start."""
        starts = self._section_starts()
        if not starts or self.highlight is None:
            return
        cur = max(i for i, s in enumerate(starts) if s <= self.highlight)
        if step < 0 and self.highlight > starts[cur]:
            target = cur
        else:
            target = max(0, min(len(starts) - 1, cur + step))
        self._set_highlight(starts[target], scroll=False)
        y = self._label_y(self.section_labels[target]) if target < len(self.section_labels) else None
        if y is not None:
            self.scroller.get_vadjustment().set_value(y)

    # ---- highlight and status -------------------------------------------

    def _set_highlight(self, k, scroll=True):
        if self.highlight is not None and self.highlight < len(self.cells):
            self.cells[self.highlight][0].remove_css_class("ep-highlight")
        self.highlight = k
        if k is None or not self.cells:
            self._show_card()
            return
        child, idx, char = self.cells[k]
        child.add_css_class("ep-highlight")
        self._update_card(idx, char)
        if scroll:
            GLib.idle_add(self._scroll_to, child, k)

    def _update_card(self, idx, char):
        e = self.index.emoji[idx]
        if self.mode == "tones":
            note = GLib.markup_escape_text(tone_text(self._tone_values[self.highlight]))
        else:
            note = '<span weight="600">Tab</span> skin tones' if e.get("sk") else ""
        self._show_card(idx, char, note)

    def _set_hints(self, state):
        self.hints.set_markup(hints_markup(state))

    def _scroll_to(self, child, k):
        adj = self.scroller.get_vadjustment()
        ok, rect = child.compute_bounds(self.chart)
        if not ok:
            return False
        top, bottom = rect.origin.y, rect.origin.y + rect.size.height
        if k == 0:
            adj.set_value(0)
        elif top < adj.get_value() + self._pinned_height():
            adj.set_value(max(0, top - self._pinned_height()))
        elif bottom > adj.get_value() + adj.get_page_size() - design.FADE:
            adj.set_value(bottom - adj.get_page_size() + design.FADE)
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
        if ctrl and keyval in (Gdk.KEY_Up, Gdk.KEY_Down) and self.mode == "pick":
            self._jump(-1 if keyval == Gdk.KEY_Up else 1)
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
        self.chart.cell = design.cell_width(self.settings.emoji_size)
        self._apply_css()
        self.chart.queue_resize()
        self._on_chart_width(self.chart.get_width())

    # ---- skin tones -------------------------------------------------------

    def _open_tones(self):
        if self.highlight is None or self.mode != "pick":
            return
        idx = self.cells[self.highlight][1]
        e = self.index.emoji[idx]
        if not e.get("sk"):
            self.card_note.set_label("No skin tones")
            self.card_note.set_visible(True)
            return
        self.saved_query_state = (self.highlight,)
        self.tone_base = idx
        self.mode = "tones"
        self.entry.set_editable(False)
        self._clear()
        items = [(e["e"], idx)] + [(s[0], idx) for s in e["sk"]]
        self._tone_values = [None] + [s[1] for s in e["sk"]]
        self._add_section("Skin tones", items)
        self._sections = [Section("tones", [i for _c, i in items])]
        self.grid = Grid([len(items)], self.columns)
        current = self.usage.tone_for(e["h"], {"pair" if isinstance(s[1], list) else "single"
                                                for s in e["sk"]})
        start = self._tone_values.index(current) if current in self._tone_values else 0
        self._set_highlight(start)
        self._set_hints("tones")
        GLib.idle_add(self._update_pinned)

    def _close_tones(self):
        self.mode = "pick"
        self.entry.set_editable(True)
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
            from .setup_steps import setup_pending
            if setup_pending():
                why = "setup finishes when you log out and back in"
            else:
                why = insert.why_not_active() or why
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

        The card says what happened. With close_after_ms the window closes by
        itself once the copy is confirmed (Ctrl+C); otherwise it stays until
        the next key, so a fallback message can be read."""
        clipboard = self.get_display().get_clipboard()
        clipboard.set(char)
        self.mode = "copied"

        def check(cb, res):
            try:
                got = cb.read_text_finish(res)
            except GLib.Error:
                got = None
            ok = got == char
            log(f"copy {char!r}: {'confirmed' if ok else 'NOT confirmed'}")
            paste = "Press Ctrl+V to paste (Ctrl+Shift+V in a terminal)."
            if not ok:
                self._card_result("Not copied", "The clipboard still holds something else.", "error")
            elif reason:
                self._card_result("Copied instead",
                                  f"Could not insert directly: {reason}.\n\n{paste}", "success")
            else:
                self._card_result("Copied", paste, "success")
            closing = close_after_ms and ok
            self._set_hints("closing" if closing else "copied")
            if closing:
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

        def done():
            # the shortcut was pressed again while this one was finishing:
            # open a fresh picker now instead of swallowing that press
            if getattr(self, "reopen_requested", False) and self.options.get("reopen"):
                self.options["reopen"]()
                self.destroy()
            else:
                app.quit()
            return False

        GLib.timeout_add(300 if self.mode == "copied" else 0, done)


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
