"""Which emoji the installed emoji font can draw.

Newer emoji than the font knows would show as boxes or as monochrome glyphs
from a fallback font (Pango silently uses Unifont for them), so a rendering
test is fooled. Instead we read the character set of the emoji font file
itself and find the newest emoji version V such that every single-code-point
emoji of version V or lower is in it. Emoji newer than V are hidden.

Cumulative, so versions with no new single code points (12.1, 13.1, 15.1:
sequences only) are kept when the versions around them are. Noto Color Emoji
ships every standard sequence of each version it supports, so the cutoff
covers ZWJ sequences and flags too.

The result is cached per font file and modification time.
"""
import json
import os
import subprocess

FAMILY = "Noto Color Emoji"


def cache_path():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "emoji-picker", "font-version.json")


KNOWN_PATHS = ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",)  # Ubuntu/Debian


def font_file(family=FAMILY):
    for p in KNOWN_PATHS:
        if os.path.exists(p):
            return p
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", family], capture_output=True,
                             text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def charset(path):
    """Set of code points in a font file, from fc-query's charset ranges."""
    out = subprocess.run(["fc-query", "-f", "%{charset}", path], capture_output=True,
                         text=True, timeout=10).stdout
    cps = set()
    for part in out.split():
        if "-" in part:
            a, b = part.split("-")
            cps.update(range(int(a, 16), int(b, 16) + 1))
        else:
            cps.add(int(part, 16))
    return cps


def supported_version(emoji, cps):
    """Newest version V with every single-code-point emoji <= V present."""
    singles = {}
    for e in emoji:
        cp = [c for c in e["e"] if c != "️"]
        if len(cp) == 1:
            singles.setdefault(e["v"], []).append(ord(cp[0]))
    best = None
    for v in sorted({e["v"] for e in emoji}):
        missing = [c for c in singles.get(v, []) if c not in cps]
        if missing:
            break
        best = v
    return best


def max_version(emoji):
    """The cutoff for this machine, or None (show everything) if unknown."""
    path = font_file()
    if not path or FAMILY.replace(" ", "") not in os.path.basename(path).replace("-", ""):
        return None  # the emoji font is not installed; do not guess
    try:
        stamp = f"{path}:{os.path.getmtime(path)}"
    except OSError:
        return None
    cp = cache_path()
    try:
        with open(cp, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("stamp") == stamp:
            return cached["version"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        version = supported_version(emoji, charset(path))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    try:
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp, "w", encoding="utf-8") as f:
            json.dump({"stamp": stamp, "version": version}, f)
    except OSError:
        pass
    return version
