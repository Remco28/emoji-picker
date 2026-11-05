#!/usr/bin/env python3
"""Score emoji search against the frozen answer key (tests/eval_queries.json).

    python3 tools/eval.py                 # baseline vs enriched (if present)
    python3 tools/eval.py --show tune     # list failures for a source
    python3 tools/eval.py --open-test     # the final run: show test-half detail
    python3 tools/eval.py --json out.json # machine-readable results

The held-out test half prints totals only, unless --open-test is given, so
tuning can only look at the tuning half's failures.
"""
import argparse
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from emoji_picker.data import load_emoji, load_enrichment  # noqa: E402
from emoji_picker.layout import COLUMNS  # noqa: E402
from emoji_picker.search import Index, positions  # noqa: E402

KEY = os.path.join(ROOT, "tests", "eval_queries.json")
LINES = {"multi": 3, "sentence": 5}
SINGLE_CELLS = 5


def norm(s):
    return s.replace("️", "")


def base_map(data):
    """Map any emoji or skin variant (VS16-insensitive) to its base character."""
    m = {}
    for e in data["emoji"]:
        m[norm(e["e"])] = norm(e["e"])
        for s in e.get("sk", []):
            m[norm(s[0])] = norm(e["e"])
    return m


def judge(index, entry, bases):
    secs = index.sections(entry["q"])
    pos = positions(secs, COLUMNS)
    order = [norm(index.emoji[i]["e"]) for _, _, i in pos]
    groups = [{bases.get(norm(x), norm(x)) for x in g} for g in entry["groups"]]
    decoys = {bases.get(norm(x), norm(x)) for x in entry.get("decoys", [])}
    first = []  # (flat rank, line) of each group's first member
    for g in groups:
        hit = next(((k, pos[k][0]) for k, ch in enumerate(order) if ch in g), None)
        first.append(hit)
    kind = entry["kind"]
    if any(h is None for h in first):
        ok = False
    elif kind == "single":
        ok = all(k < SINGLE_CELLS for k, _ in first)
    else:
        ok = all(line < LINES[kind] for _, line in first)
    worst = max((h[0] for h in first if h is not None), default=None)
    decoy_hit = None
    if decoys and worst is not None:
        decoy_hit = next((order[k] for k in range(worst) if order[k] in decoys), None)
        ok = ok and decoy_hit is None
    any_acc = set().union(*groups)
    rank1 = next((k for k, ch in enumerate(order) if ch in any_acc), None)
    return {"q": entry["q"], "kind": kind, "pass": ok, "first": first,
            "decoy_before": decoy_hit, "top1": bool(order) and order[0] in any_acc,
            "rr": 0.0 if rank1 is None else 1.0 / (rank1 + 1),
            "top": "".join(order[:12])}


def noise_check(index, noise):
    problems, tops = [], {}
    for q in noise["stopwords"]:
        if index.sections(q) is not None:
            problems.append(f"stopword-only {q!r} did not show the browse view")
    for q in noise["gibberish"]:
        secs = index.sections(q)
        if secs:
            got = "".join(index.emoji[i]["e"] for s in secs for i in s.items[:5])
            problems.append(f"gibberish {q!r} returned results: {got}")
        for s in secs or []:
            for i in s.items[:5]:
                tops[i] = tops.get(i, 0) + 1
    for i, n in tops.items():
        if n > 3:
            problems.append(f"{index.emoji[i]['e']} is in {n} noise top-5 lists")
    return problems


def run(index, key, bases):
    res = {}
    for src, entries in key["sources"].items():
        res[src] = [judge(index, e, bases) for e in entries]
    return res


def summary(rows):
    n = len(rows)
    return {"n": n, "pass": sum(r["pass"] for r in rows),
            "top1": sum(r["top1"] for r in rows),
            "mrr": round(statistics.mean(r["rr"] for r in rows), 3) if rows else 0}


def timing(index, key):
    qs = [e["q"] for src in key["sources"].values() for e in src]
    t = time.perf_counter()
    for q in qs:
        index.sections(q)
    return (time.perf_counter() - t) / len(qs) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enrich", help="enrichment file (default: emoji_picker/data/enrich-en.json)")
    ap.add_argument("--show", action="append", default=[], help="list failures for a source")
    ap.add_argument("--open-test", action="store_true", help="final run: show test-half detail")
    ap.add_argument("--json", help="write full results here")
    ap.add_argument("--tune-only", action="store_true",
                    help="leave the held-out test half out entirely (use while tuning)")
    args = ap.parse_args()

    key = json.load(open(KEY, encoding="utf-8"))
    if args.tune_only:
        key["sources"].pop("heldout_test", None)
    data = load_emoji()
    bases = base_map(data)
    enrichment = load_enrichment(args.enrich)
    variants = {"baseline": Index(data)}
    if enrichment:
        t = time.perf_counter()
        variants["enriched"] = Index(data, enrichment)
        build_ms = (time.perf_counter() - t) * 1000
        print(f"enrichment: {sum(len(v) for v in enrichment.values())} terms on "
              f"{len(enrichment)} emoji; index build {build_ms:.0f} ms")

    results = {name: run(idx, key, bases) for name, idx in variants.items()}
    print(f"\ncolumns per line: {COLUMNS}\n")
    print(f"{'source':14s}" + "".join(f"{name:>30s}" for name in variants))
    for src in key["sources"]:
        line = f"{src:14s}"
        for name in variants:
            s = summary(results[name][src])
            line += f"{'pass %d/%d  top1 %d  mrr %.2f' % (s['pass'], s['n'], s['top1'], s['mrr']):>30s}"
        print(line)
    for name, idx in variants.items():
        probs = noise_check(idx, key["noise"])
        print(f"\nnoise ({name}): " + ("all rules hold" if not probs else f"{len(probs)} problems"))
        for p in probs[:8]:
            print("   ", p)
        print(f"search time ({name}): {timing(idx, key):.2f} ms per query")

    if "enriched" in results:
        better = worse = 0
        regress = []
        for src in key["sources"]:
            for b, e in zip(results["baseline"][src], results["enriched"][src]):
                better += e["rr"] > b["rr"]
                worse += e["rr"] < b["rr"]
                if b["pass"] and not e["pass"]:
                    regress.append((src, e["q"]))
        print(f"\nrank change per query, enriched vs baseline: {better} better, {worse} worse")
        visible = [(s, q) for s, q in regress if s != "heldout_test" or args.open_test]
        hidden = len(regress) - len(visible)
        print(f"queries the baseline passed that now fail: {len(regress)}"
              + (f" ({hidden} in the test half, hidden)" if hidden else ""))
        for s, q in visible:
            print(f"    [{s}] {q}")

    for src in args.show:
        if src == "heldout_test" and not args.open_test:
            print("\n(test half detail is hidden; use --open-test for the final run)")
            continue
        for name in variants:
            fails = [r for r in results[name][src] if not r["pass"]]
            print(f"\nfailures in {src} ({name}): {len(fails)}")
            for r in fails:
                why = "decoy " + r["decoy_before"] if r["decoy_before"] else \
                    "missing/too low " + str([f if f is None else f"rank {f[0]} line {f[1]}" for f in r["first"]])
                print(f"   {r['q']!r:45.45s} {why:40.40s} top: {r['top']}")

    if args.json:
        if not args.open_test:
            for name in results:
                results[name]["heldout_test"] = [{"pass": r["pass"]} for r in results[name]["heldout_test"]]
        json.dump(results, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
