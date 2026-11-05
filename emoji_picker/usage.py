"""What you use: recents, frequency, remembered skin tones. Stored locally.

File: $XDG_STATE_HOME/emoji-picker/usage.json (default ~/.local/state/...).
A corrupt file is moved aside (usage.json.corrupt-<time>) and a fresh one
started, so a bad write never stops the picker from opening.

Frequency is "frecency": each use adds 1 and older uses fade with a 14-day
half-life, so what you used a lot last year does not crowd out this week.

Tones: choosing a tone for an emoji remembers it for that emoji, and also
becomes the default for tone-capable emoji you have never set. One-person
emoji have a single tone (1-5); two-person emoji have a pair; each kind has
its own default.
"""
import json
import os
import time

HALF_LIFE = 14 * 24 * 3600
RECENT = 16
FREQUENT = 24


def default_path():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "emoji-picker", "usage.json")


class Usage:
    def __init__(self, path=None, clock=time.time):
        self.path = path or default_path()
        self.clock = clock
        self.emoji = {}  # hexcode -> {"f": frecency at time t, "t": last use, "n": count}
        self.tones = {}  # hexcode -> tone (int) or [a, b]
        self.default_tone = None
        self.default_pair = None
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            self.emoji = {h: {"f": float(v["f"]), "t": float(v["t"]), "n": int(v["n"])}
                          for h, v in raw.get("emoji", {}).items()}
            self.tones = dict(raw.get("tones", {}))
            self.default_tone = raw.get("default_tone")
            self.default_pair = raw.get("default_pair")
        except FileNotFoundError:
            pass
        except (ValueError, KeyError, TypeError, AttributeError):
            stamp = time.strftime("%Y%m%d-%H%M%S")
            try:
                os.replace(self.path, f"{self.path}.corrupt-{stamp}")
            except OSError:
                pass
            self.emoji, self.tones = {}, {}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "emoji": self.emoji, "tones": self.tones,
                       "default_tone": self.default_tone, "default_pair": self.default_pair}, f)
        os.replace(tmp, self.path)

    # ---- use -------------------------------------------------------------

    def record(self, hexcode, tone=None):
        now = self.clock()
        cur = self.emoji.get(hexcode)
        f = 0.0 if cur is None else cur["f"] * 0.5 ** ((now - cur["t"]) / HALF_LIFE)
        self.emoji[hexcode] = {"f": f + 1.0, "t": now, "n": (cur or {"n": 0})["n"] + 1}
        if tone is not None:
            self.set_tone(hexcode, tone)

    def frecency(self, hexcode):
        cur = self.emoji.get(hexcode)
        if cur is None:
            return 0.0
        return cur["f"] * 0.5 ** ((self.clock() - cur["t"]) / HALF_LIFE)

    def recent(self, n=RECENT):
        return sorted(self.emoji, key=lambda h: -self.emoji[h]["t"])[:n]

    def frequent(self, n=FREQUENT):
        return sorted(self.emoji, key=lambda h: (-self.frecency(h), -self.emoji[h]["t"]))[:n]

    # ---- tones ------------------------------------------------------------

    def set_tone(self, hexcode, tone):
        self.tones[hexcode] = tone
        if isinstance(tone, list):
            self.default_pair = tone
        else:
            self.default_tone = tone

    def tone_for(self, hexcode, kinds):
        """The tone to use for an emoji, or None for the plain yellow one.

        `kinds` is the set of tone shapes the emoji offers: "single" and/or
        "pair". A per-emoji choice wins; otherwise the last default of the
        matching shape.
        """
        if hexcode in self.tones:
            return self.tones[hexcode]
        if "pair" in kinds and self.default_pair is not None:
            return self.default_pair
        if "single" in kinds and self.default_tone is not None:
            return self.default_tone
        return None
