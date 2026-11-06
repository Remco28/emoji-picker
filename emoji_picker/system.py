"""System setup for emoji-picker: input sources, the Super+. hotkey and the
IBus component. Used by install.sh, uninstall.sh and finish-setup.

Values are read and printed in the text format `gsettings get` uses. Every
edit touches only entries that are ours, so whatever else the user has (or
changed later) is kept.

    python3 -m emoji_picker.system engines "<sources>"
        -> one line per xkb source: "<xkb id>"
    system.py component VERSION EXEC REGISTRY_DIR
        -> IBus component XML with an engine for every layout listed in the
           registry files (one per user who installed it)
    system.py convert "<sources>" [--known "<ibus list-engine output>"] [--proto ID]
        -> sources using our engines (only engines IBus lists, with --known;
           the prototype's engine becomes ours for layout ID, with --proto)
    system.py prototype-layout COMPONENT_XML -> the prototype engine's layout, or ""
    system.py restore "<sources>"   -> sources back to plain xkb
    system.py missing "<sources>" "<ibus list-engine output>" [--proto ID]
        -> our engines the converted sources need that IBus does not list yet
    system.py has "<list>" KEY            -> exit status 0 when KEY is in the list
    system.py hotkey-remove "<list>" KEY  -> list without KEY
    system.py hotkey-restore "<list>" KEY -> list with KEY first
    system.py add-path "<paths>" PATH / remove-path "<paths>" PATH

It is run as a plain script with `python3 -I` (no package imports), so the
installer can use it from a clone and uninstall from the installed copy.
"""
import ast
import os
import re
import sys
from xml.sax.saxutils import escape

PREFIX = "emoji-picker:"
PROTOTYPE = ("ibus", "emoji-picker")  # the single engine of the 0.1 prototype


def engine_name(xkb_id):
    return PREFIX + xkb_id


def xkb_id_of(engine):
    return engine[len(PREFIX):] if engine.startswith(PREFIX) else None


# ---- gsettings text format ------------------------------------------------

def parse(text):
    text = text.strip()
    if text.startswith("@"):          # typed empty value, e.g. "@a(ss) []"
        text = text.split(" ", 1)[1]
    value = ast.literal_eval(text)
    if not isinstance(value, list):
        raise ValueError(f"not a list: {text!r}")
    return value


def fmt_sources(items):
    if not items:
        return "@a(ss) []"
    return "[" + ", ".join(f"({a!r}, {b!r})" for a, b in items) + "]"


def fmt_strings(items):
    return "[" + ", ".join(repr(p) for p in items) + "]" if items else "@as []"


# ---- input sources --------------------------------------------------------

def xkb_ids(sources):
    """The plain keyboard layouts, plus ones already converted, in order."""
    out = []
    for kind, name in sources:
        xid = name if kind == "xkb" else xkb_id_of(name) if kind == "ibus" else None
        if xid and xid not in out:
            out.append(xid)
    return out


def convert(sources, known=None, proto_id=None):
    """Each ('xkb', ID) becomes our engine for ID, in place.

    The prototype's single engine becomes our engine for `proto_id` (the
    layout it typed with), or is dropped when another of ours replaces it.
    With `known` (engine names IBus lists) only engines IBus knows are
    used, so a source is never swapped for one GNOME would skip. Anything
    else is kept as it is."""
    items = [tuple(s) for s in sources]

    def usable(engine):
        return known is None or engine in known

    proto_engine = engine_name(proto_id) if proto_id and usable(engine_name(proto_id)) else None
    replaced = any(k == "xkb" and usable(engine_name(n)) for k, n in items) or proto_engine
    out = []
    for kind, name in items:
        if (kind, name) == PROTOTYPE:
            if proto_engine:
                item = ("ibus", proto_engine)
            elif replaced:
                continue
            else:
                item = (kind, name)   # keep the only engine that works until ours load
        elif kind == "xkb" and usable(engine_name(name)):
            item = ("ibus", engine_name(name))
        else:
            item = (kind, name)
        if item not in out:
            out.append(item)
    return out


def prototype_layout(xml_text):
    """The layout id the prototype's engine typed with, from its component."""
    m = re.search(r"<name>emoji-picker</name>.*?<layout>([^<]+)</layout>"
                  r"(?:\s*<layout_variant>([^<]+)</layout_variant>)?", xml_text, re.S)
    if not m:
        return None
    return m.group(1) + (f"+{m.group(2)}" if m.group(2) else "")


def restore(sources):
    """The reverse of convert. A list with nothing of ours comes back as it
    was; otherwise the result is never empty."""
    items = [tuple(s) for s in sources]
    if not any(k == "ibus" and (n == PROTOTYPE[1] or xkb_id_of(n)) for k, n in items):
        return items
    out = []
    for kind, name in (tuple(s) for s in sources):
        if (kind, name) == PROTOTYPE:
            continue
        xid = xkb_id_of(name) if kind == "ibus" else None
        item = ("xkb", xid) if xid else (kind, name)
        if item not in out:
            out.append(item)
    return out or [("xkb", "us")]


def listed_engines(list_engine_output):
    """Engine names in `ibus list-engine` output ("  <name> - <longname>")."""
    known = set()
    for line in list_engine_output.splitlines():
        m = re.match(r"\s+(\S+) - ", line)
        if m:
            known.add(m.group(1))
    return known


def missing(sources, list_engine_output):
    """Our engines the converted sources would need that IBus does not know."""
    known = listed_engines(list_engine_output)
    return [engine_name(x) for x in xkb_ids(sources) if engine_name(x) not in known]


def registry_ids(registry_dir):
    """Every layout any user installed it for (files named by uid)."""
    out = []
    try:
        names = sorted(os.listdir(registry_dir))
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(registry_dir, n), encoding="utf-8") as f:
                for line in f:
                    xid = line.strip()
                    if re.fullmatch(r"[A-Za-z0-9_()+-]+", xid) and xid not in out:
                        out.append(xid)
        except OSError:
            pass
    return out


# ---- hotkeys and keybinding paths ----------------------------------------

def without(items, key):
    return [k for k in items if k != key]


def with_first(items, key):
    return [key] + [k for k in items if k != key]


# ---- the IBus component ---------------------------------------------------

def layout_info(xkb_id):
    """(language, symbol, longname) for a layout, so GNOME's menu entry,
    "<language name> (<longname>)", reads like the plain layout's name.

    "English (US)" -> eng, "US, with emoji". When the display name does not
    start with a language name ("Belgian"), the first language is used and
    the whole display name goes in the brackets: "French (Belgian, with emoji)".
    """
    language, symbol, display = "other", xkb_id.partition("+")[0][:3], xkb_id
    langs = []
    try:
        import gi
        gi.require_version("GnomeDesktop", "4.0")
        gi.require_version("IBus", "1.0")
        from gi.repository import GnomeDesktop, IBus
        info = GnomeDesktop.XkbInfo()
        ok, name, short, _l, _v = info.get_layout_info(xkb_id)
        if ok:
            display, symbol = name or xkb_id, short or symbol
            langs = list(info.get_languages_for_layout(xkb_id) or [])
    except (ImportError, ValueError):
        IBus = None
    for code in langs:
        lname = IBus.get_language_name(code) if IBus else ""
        if lname and (display == lname or display.startswith(lname + " (")):
            inner = display[len(lname):].strip()[1:-1] if display != lname else ""
            return code, symbol, f"{inner}, with emoji" if inner else "with emoji"
    if langs:
        language = langs[0]
    return language, symbol, f"{display}, with emoji"


ENGINE_XML = """    <engine>
      <name>{name}</name>
      <language>{language}</language>
      <license>MIT</license>
      <author>emoji-picker</author>
      <icon>io.github.remco28.EmojiPicker</icon>
      <symbol>{symbol}</symbol>
      <layout>{layout}</layout>{variant}
      <longname>{longname}</longname>
      <description>Your keyboard as usual; lets emoji-picker insert emoji</description>
      <rank>0</rank>
    </engine>
"""

COMPONENT_XML = """<?xml version="1.0" encoding="utf-8"?>
<!-- Written by emoji-picker's install.sh; removed by its uninstall.sh. -->
<component>
  <name>org.freedesktop.IBus.EmojiPicker</name>
  <description>Passive engine that lets emoji-picker insert emoji</description>
  <exec>{exec} --ibus</exec>
  <version>{version}</version>
  <author>emoji-picker</author>
  <license>MIT</license>
  <homepage>https://github.com/Remco28/emoji-picker</homepage>
  <textdomain>emoji-picker</textdomain>
  <engines>
{engines}  </engines>
</component>
"""


def component(exec_path, ids, version, info=layout_info):
    parts = []
    for xid in ids:
        layout, _, variant = xid.partition("+")
        language, symbol, longname = info(xid)
        parts.append(ENGINE_XML.format(
            name=escape(engine_name(xid)), language=escape(language), symbol=escape(symbol),
            layout=escape(layout), longname=escape(longname),
            # an empty <layout_variant> stops IBus activating the engine
            variant=f"\n      <layout_variant>{escape(variant)}</layout_variant>" if variant else ""))
    return COMPONENT_XML.format(exec=escape(exec_path), version=escape(version),
                                engines="".join(parts))


# ---- command line ---------------------------------------------------------

def _opts(args):
    """Positional arguments, plus --known LIST_ENGINE_OUTPUT and --proto ID."""
    pos, known, proto = [], None, None
    i = 0
    while i < len(args):
        if args[i] == "--known":
            known, i = listed_engines(args[i + 1]), i + 2
        elif args[i] == "--proto":
            proto, i = (args[i + 1] or None), i + 2
        else:
            pos.append(args[i])
            i += 1
    return pos, known, proto


def main(argv):
    cmd, (args, known, proto) = argv[1], _opts(argv[2:])
    if cmd == "engines":
        ids = xkb_ids(parse(args[0]))
        if proto and proto not in ids:
            ids.append(proto)
        for xid in ids:
            print(xid)
    elif cmd == "component":
        version, exec_path, registry = args
        print(component(exec_path, registry_ids(registry), version), end="")
    elif cmd == "convert":
        print(fmt_sources(convert(parse(args[0]), known, proto)))
    elif cmd == "restore":
        print(fmt_sources(restore(parse(args[0]))))
    elif cmd == "missing":
        for name in missing(convert(parse(args[0]), None, proto), args[1]):
            print(name)
    elif cmd == "prototype-layout":
        try:
            with open(args[0], encoding="utf-8") as f:
                print(prototype_layout(f.read()) or "")
        except OSError:
            print("")
    elif cmd == "has":
        sys.exit(0 if args[1] in parse(args[0]) else 1)
    elif cmd == "hotkey-remove":
        print(fmt_strings(without(parse(args[0]), args[1])))
    elif cmd == "hotkey-restore":
        print(fmt_strings(with_first(parse(args[0]), args[1])))
    elif cmd == "add-path":
        print(fmt_strings(without(parse(args[0]), args[1]) + [args[1]]))
    elif cmd == "remove-path":
        print(fmt_strings(without(parse(args[0]), args[1])))
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv)
