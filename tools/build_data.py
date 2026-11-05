#!/usr/bin/env python3
"""Build emoji_picker/data/emoji.json from a pinned emojibase-data release.

    python3 tools/build_data.py            # downloads the pinned tarball
    python3 tools/build_data.py --tgz F    # uses a local copy (still checked)

The tarball's sha256 is pinned; a mismatch aborts. Output is deterministic
(sorted keys, emojibase order), so rebuilding gives an identical file.
"""
import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import urllib.request

VERSION = "18.0.0"
URL = f"https://registry.npmjs.org/emojibase-data/-/emojibase-data-{VERSION}.tgz"
SHA256 = "ed207c64f31baab5db419686135be3696bbd196a88228a3564383d7918db8f34"
SHORTCODE_SETS = ("github", "cldr", "emojibase")  # merged, in this order
COMPONENT_GROUP = 2  # bare skin-tone swatches and hair pieces

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "emoji_picker", "data")


def fetch(path):
    if path:
        blob = open(path, "rb").read()
    else:
        with urllib.request.urlopen(URL, timeout=60) as r:
            blob = r.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != SHA256:
        sys.exit(f"sha256 mismatch: got {digest}, expected {SHA256}")
    return tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")


def member(tar, name):
    return json.load(tar.extractfile(f"package/{name}"))


def as_list(v):
    return v if isinstance(v, list) else [v]


def build(tar):
    data = member(tar, "en/data.json")
    meta = member(tar, "meta/groups.json")
    codes = {s: member(tar, f"en/shortcodes/{s}.json") for s in SHORTCODE_SETS}

    out = []
    for d in data:
        if d.get("group") is None or d["group"] == COMPONENT_GROUP:
            continue
        sc = []
        for s in SHORTCODE_SETS:
            for c in as_list(codes[s].get(d["hexcode"], [])):
                if c not in sc:
                    sc.append(c)
        item = {
            "e": d["emoji"],
            "h": d["hexcode"],
            "n": d["label"],
            "t": d.get("tags", []),
            "g": d["group"],
            "sg": d["subgroup"],
            "o": d["order"],
            "v": d["version"],
            "sc": sc,
        }
        skins = d.get("skins") or []
        if skins:
            item["sk"] = [[s["emoji"], s["tone"], s["version"]] for s in skins]
        out.append(item)
    out.sort(key=lambda x: x["o"])
    return {
        "source": f"emojibase-data {VERSION}",
        "groups": meta["groups"],
        "subgroups": meta["subgroups"],
        "emoji": out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tgz", help="local copy of the tarball")
    args = ap.parse_args()
    tar = fetch(args.tgz)
    result = build(tar)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "emoji.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    with open(os.path.join(OUT_DIR, "LICENSE-emojibase.txt"), "wb") as f:
        f.write(tar.extractfile("package/LICENSE").read())
    n_sk = sum(1 for e in result["emoji"] if "sk" in e)
    print(f"wrote {len(result['emoji'])} emoji ({n_sk} with skin variants) "
          f"to {os.path.relpath(OUT_DIR, ROOT)}/emoji.json")


if __name__ == "__main__":
    main()
