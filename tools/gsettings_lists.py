#!/usr/bin/env python3
"""Small, safe edits of GNOME list settings, for install.sh and uninstall.sh.

Reads a value as `gsettings get` prints it, prints the new value in the same
text format. Never touches entries that are not ours.

    gsettings_lists.py layout "<sources>"                 -> "us" or "us intl"
    gsettings_lists.py add-source "<sources>"             -> sources with ours first
    gsettings_lists.py remove-source "<sources>"          -> sources without ours
    gsettings_lists.py add-path "<paths>" PATH            -> keybinding list + PATH
    gsettings_lists.py remove-path "<paths>" PATH         -> keybinding list - PATH
    gsettings_lists.py component TEMPLATE EXEC LAYOUT [VARIANT]  -> engine XML
"""
import ast
import sys
from xml.sax.saxutils import escape

OURS = ("ibus", "emoji-picker")


def parse(text):
    text = text.strip()
    if text.startswith("@"):          # typed empty value, e.g. "@a(ss) []"
        text = text.split(" ", 1)[1]
    value = ast.literal_eval(text)
    if not isinstance(value, list):
        raise SystemExit(f"not a list: {text!r}")
    return value


def fmt_sources(items):
    if not items:
        return "@a(ss) []"
    return "[" + ", ".join(f"({a!r}, {b!r})" for a, b in items) + "]"


def fmt_paths(items):
    return "[" + ", ".join(repr(p) for p in items) + "]" if items else "@as []"


def main(argv):
    cmd = argv[1]
    if cmd == "layout":
        for kind, name in parse(argv[2]):
            if kind == "xkb":
                layout, _, variant = name.partition("+")
                print(f"{layout} {variant}".strip())
                return
        print("us")  # no plain keyboard source: fall back to US
    elif cmd == "add-source":
        items = [tuple(x) for x in parse(argv[2]) if tuple(x) != OURS]
        print(fmt_sources([OURS] + items))
    elif cmd == "remove-source":
        print(fmt_sources([tuple(x) for x in parse(argv[2]) if tuple(x) != OURS]))
    elif cmd == "add-path":
        items = [p for p in parse(argv[2]) if p != argv[3]]
        print(fmt_paths(items + [argv[3]]))
    elif cmd == "remove-path":
        print(fmt_paths([p for p in parse(argv[2]) if p != argv[3]]))
    elif cmd == "component":
        template, exe, layout = argv[2], argv[3], argv[4]
        variant = argv[5] if len(argv) > 5 else ""
        xml = open(template, encoding="utf-8").read()
        element = f"\n      <layout_variant>{escape(variant)}</layout_variant>" if variant else ""
        print(xml.replace("@EXEC@", escape(exe)).replace("@LAYOUT@", escape(layout))
              .replace("@VARIANT_ELEMENT@", element), end="")
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv)
