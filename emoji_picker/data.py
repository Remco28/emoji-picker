"""Loading the built emoji data and the optional enrichment file."""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def load_emoji(path=None):
    with open(path or os.path.join(DATA_DIR, "emoji.json"), encoding="utf-8") as f:
        return json.load(f)


def load_enrichment(path=None):
    """Return {hexcode: [terms]} or {} when there is no enrichment file."""
    path = path or os.path.join(DATA_DIR, "enrich-en.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("terms", {})
