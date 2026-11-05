#!/usr/bin/env python3
"""Generate extra search terms per emoji with an LLM, once, at build time.

    python3 tools/enrich.py                 # generate missing batches, write the file
    python3 tools/enrich.py --jobs 6        # parallel calls
    python3 tools/enrich.py --sample 30     # print 30 random emoji with their terms

Each batch of emoji (label, tags, category) goes to `claude -p` run from an
empty scratch directory, so no project instructions are loaded. Answers are
validated strictly; a failing batch is retried once, then reported, never
skipped silently. Batches are cached under ~/.cache keyed by the prompt's
hash and the model, so changing either regenerates everything.

The answer key (tests/eval_queries.json) is never read here.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from emoji_picker.data import load_emoji  # noqa: E402

MODEL = "claude-sonnet-5-5"
BATCH = 60
MAX_TERMS = 25
GENERIC_LIMIT = 40  # a term on more emoji than this is too generic and is dropped
OUT = os.path.join(ROOT, "emoji_picker", "data", "enrich-en.json")
CACHE_ROOT = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                          "emoji-picker-enrich")
TERM_RE = re.compile(r"^[a-z0-9][a-z0-9'\-]*( [a-z0-9][a-z0-9'\-]*){0,2}$")

PROMPT = """You are writing search keywords for an emoji picker. People open the picker and type a few words about what they want to say; the picker matches those words against keywords. Each emoji already has its official name and some tags (given below). Your job is to add the OTHER words people would actually type when this emoji is what they want.

Think about what the person is writing about when they pick this emoji: the places, people, events, moods and everyday situations it gets sent for.

For each emoji, give 10 to 25 extra search terms. Each term is 1 to 3 lowercase words. Include:
- everyday synonyms and casual or slang words ("lmao" for a laughing face),
- situations and occasions where people use it ("surgery", "get well" or "visiting hours" for a hospital; "funeral" for a coffin),
- feelings and reactions it expresses,
- short phrases people type in messages, when this emoji fits them ("good night", "on my way"),
- for flags: the country's common short names, abbreviations, demonyms and nicknames, and the phrases "<demonym> flag" and "<short name> flag" (for France: "france", "french", "french flag", "les bleus"),
- for objects, foods, animals and activities: closely related things people would search for.

Do not include:
- words that would fit hundreds of emoji ("emoji", "symbol", "icon", "thing", "nice"),
- the official name or tags again,
- offensive or sexual associations,
- anything you would not expect a real person to type.

Answer with JSON only: one object whose keys are the hexcodes below and whose values are lists of terms. No text before or after it.

Emoji:
{items}"""


def prompt_hash():
    return hashlib.sha256((PROMPT + MODEL).encode()).hexdigest()[:12]


def batches(emoji):
    return [emoji[k:k + BATCH] for k in range(0, len(emoji), BATCH)]


def render(batch, groups, subgroups):
    lines = []
    for e in batch:
        cat = f'{groups.get(str(e["g"]), "")} / {subgroups.get(str(e["sg"]), "")}'
        lines.append(f'{e["h"]}: {e["e"]} | name: {e["n"]} | tags: {", ".join(e.get("t", []))} | category: {cat}')
    return PROMPT.replace("{items}", "\n".join(lines))


def ask(prompt):
    with tempfile.TemporaryDirectory(prefix="enrich-") as empty:
        r = subprocess.run(
            ["claude", "-p", "--model", MODEL, "--no-session-persistence",
             "--disallowedTools", "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Agent"],
            input=prompt, capture_output=True, text=True, cwd=empty, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"claude exited {r.returncode}: {r.stderr.strip()[:300]}")
    return r.stdout


def validate(text, batch):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in the answer")
    obj = json.loads(text[start:end + 1])
    want = {e["h"] for e in batch}
    if set(obj) != want:
        missing, extra = want - set(obj), set(obj) - want
        raise ValueError(f"hexcodes differ: missing {sorted(missing)[:5]}, extra {sorted(extra)[:5]}")
    out, rejected = {}, 0
    for e in batch:
        existing = {e["n"].lower()} | {t.lower() for t in e.get("t", [])}
        seen, terms = set(), []
        for t in obj[e["h"]]:
            if not isinstance(t, str):
                rejected += 1
                continue
            t = " ".join(t.lower().replace("’", "'").split())
            if not TERM_RE.match(t) or t in existing or t in seen:
                rejected += 1
                continue
            seen.add(t)
            terms.append(t)
        out[e["h"]] = terms[:MAX_TERMS]
    return out, rejected


def run_batch(n, batch, groups, subgroups, cache_dir):
    path = os.path.join(cache_dir, f"batch-{n:03d}.json")
    if os.path.exists(path):
        return n, json.load(open(path, encoding="utf-8")), "cached"
    prompt = render(batch, groups, subgroups)
    last = None
    for attempt in (1, 2):
        try:
            t = time.time()
            terms, rejected = validate(ask(prompt), batch)
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(terms, f, ensure_ascii=False)
            os.replace(path + ".tmp", path)
            return n, terms, f"ok in {time.time() - t:.0f}s, {rejected} terms rejected, attempt {attempt}"
        except Exception as ex:  # noqa: BLE001
            last = ex
    return n, None, f"FAILED twice: {last}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--sample", type=int, default=0)
    args = ap.parse_args()

    data = load_emoji()
    emoji = data["emoji"]
    cache_dir = os.path.join(CACHE_ROOT, f"{prompt_hash()}-{MODEL}")
    os.makedirs(cache_dir, exist_ok=True)
    bs = batches(emoji)
    print(f"{len(emoji)} emoji in {len(bs)} batches; cache {cache_dir}", flush=True)

    results, failed = {}, []
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = [pool.submit(run_batch, n, b, data["groups"], data["subgroups"], cache_dir)
                for n, b in enumerate(bs)]
        for fut in cf.as_completed(futs):
            n, terms, msg = fut.result()
            print(f"batch {n:3d}: {msg}", flush=True)
            if terms is None:
                failed.append(n)
            else:
                results.update(terms)
    if failed:
        sys.exit(f"{len(failed)} batches failed: {sorted(failed)}; rerun to retry them")

    # Drop terms attached to too many emoji: they would match everything.
    counts = {}
    for terms in results.values():
        for t in terms:
            counts[t] = counts.get(t, 0) + 1
    generic = sorted((t for t, c in counts.items() if c > GENERIC_LIMIT), key=lambda t: -counts[t])
    for h in results:
        results[h] = [t for t in results[h] if t not in generic]
    print(f"dropped {len(generic)} generic terms: " +
          ", ".join(f"{t} ({counts[t]})" for t in generic[:20]))

    meta = {"model": MODEL, "prompt_sha256_12": prompt_hash(), "date": time.strftime("%Y-%m-%d"),
            "source": data["source"], "generic_limit": GENERIC_LIMIT, "dropped_generic": generic}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "terms": results}, f, ensure_ascii=False, sort_keys=True, indent=0)
    total = sum(len(v) for v in results.values())
    print(f"wrote {total} terms for {len(results)} emoji to {os.path.relpath(OUT, ROOT)}")

    if args.sample:
        by_h = {e["h"]: e for e in emoji}
        for h in random.Random(7).sample(sorted(results), args.sample):
            print(f'{by_h[h]["e"]} {by_h[h]["n"]}: {", ".join(results[h])}')


if __name__ == "__main__":
    main()
