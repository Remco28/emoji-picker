"""System setup for emoji-picker: input sources, the Super+. hotkey and the
IBus component. Used by install.sh, uninstall.sh and finish-setup.

Values are read and printed in the text format `gsettings get` uses. Every
edit touches only entries that are ours, so whatever else the user has (or
changed later) is kept.

    python3 -m emoji_picker.system engines "<sources>"
        -> one line per xkb source: "<xkb id>"
    python3 -m emoji_picker.system component EXEC [INSTALLED_XML] -- ID...
        -> IBus component XML with an engine per xkb id (plus ours already in
           INSTALLED_XML, so another user's engines are kept)
    python3 -m emoji_picker.system convert "<sources>"   -> sources using our engines
    python3 -m emoji_picker.system restore "<sources>"   -> sources back to plain xkb
    python3 -m emoji_picker.system missing "<sources>" "<ibus list-engine output>"
        -> our engines the sources need that IBus does not list yet
    python3 -m emoji_picker.system hotkey-remove "<list>" KEY  -> list without KEY
    python3 -m emoji_picker.system hotkey-restore "<list>" KEY -> list with KEY first
    python3 -m emoji_picker.system add-path "<paths>" PATH / remove-path ...
"""
import ast
import re
import sys
from xml.etree import ElementTree
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


def convert(sources):
    """Each ('xkb', ID) becomes our engine for ID, in place. The prototype's
    engine is dropped. Anything else is kept as it is."""
    out = []
    for kind, name in (tuple(s) for s in sources):
        if (kind, name) == PROTOTYPE:
            continue
        item = ("ibus", engine_name(name)) if kind == "xkb" else (kind, name)
        if item not in out:
            out.append(item)
    return out


def restore(sources):
    """The reverse of convert. Never returns an empty list."""
    out = []
    for kind, name in (tuple(s) for s in sources):
        if (kind, name) == PROTOTYPE:
            continue
        xid = xkb_id_of(name) if kind == "ibus" else None
        item = ("xkb", xid) if xid else (kind, name)
        if item not in out:
            out.append(item)
    return out or [("xkb", "us")]


def missing(sources, list_engine_output):
    """Our engines the converted sources would need that IBus does not know."""
    known = set()
    for line in list_engine_output.splitlines():
        # `ibus list-engine` prints "  <name> - <longname>" under language headings
        m = re.match(r"\s+(\S+) - ", line)
        if m:
            known.add(m.group(1))
    return [engine_name(x) for x in xkb_ids(sources) if engine_name(x) not in known]


# ---- hotkeys and keybinding paths ----------------------------------------

def without(items, key):
    return [k for k in items if k != key]


def with_first(items, key):
    return [key] + [k for k in items if k != key]


# ---- the IBus component ---------------------------------------------------

def layout_info(xkb_id):
    """(language, symbol, longname) for a layout, as GNOME would name it."""
    layout, _, variant = xkb_id.partition("+")
    language, symbol, display = "other", layout[:3], xkb_id
    try:
        import gi
        gi.require_version("GnomeDesktop", "4.0")
        from gi.repository import GnomeDesktop
        info = GnomeDesktop.XkbInfo()
        ok, display, short, _l, _v = info.get_layout_info(xkb_id)
        if ok:
            symbol = short or symbol
            langs = info.get_languages_for_layout(xkb_id) or []
            if langs:
                language = langs[0]
        else:
            display = xkb_id
    except (ImportError, ValueError):
        pass
    m = re.match(r"^[^(]*\((.*)\)\s*$", display or "")
    longname = f"{m.group(1)}, with emoji" if m else "with emoji"
    return language, symbol, longname


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


def installed_ids(xml_text):
    """xkb ids of our engines in an installed component (ours only)."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    if root.findtext("name") != "org.freedesktop.IBus.EmojiPicker":
        return []
    out = []
    for e in root.iter("engine"):
        xid = xkb_id_of(e.findtext("name") or "")
        if xid and xid not in out:
            out.append(xid)
    return out


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

def main(argv):
    cmd, args = argv[1], argv[2:]
    if cmd == "engines":
        for xid in xkb_ids(parse(args[0])):
            print(xid)
    elif cmd == "component":
        sep = args.index("--")
        exec_path, rest, ids = args[0], args[1:sep], args[sep + 1:]
        if rest:
            try:
                with open(rest[0], encoding="utf-8") as f:
                    ids = ids + [x for x in installed_ids(f.read()) if x not in ids]
            except OSError:
                pass
        from . import __version__
        print(component(exec_path, ids, __version__), end="")
    elif cmd == "convert":
        print(fmt_sources(convert(parse(args[0]))))
    elif cmd == "restore":
        print(fmt_sources(restore(parse(args[0]))))
    elif cmd == "missing":
        for name in missing(convert(parse(args[0])), args[1]):
            print(name)
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
