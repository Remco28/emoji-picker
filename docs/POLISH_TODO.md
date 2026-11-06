# Polish checklist (branch `polish`; delete this file when done)

From two independent reviews of the before screenshots (Codex; a fresh
Claude agent), each finding checked against the code before it went on the
list. Both reviews found 1-8 on their own. Rules named from
`.claude/skills/desktop-polish/principles.md`.

## Do

1. **Square cells, one cell size.** Cell = emoji + 16 (48 px at default);
   the same value for drawing, columns and paging (`layout.CELL` from
   `design`). Leftover width becomes equal margins, not stretched cells.
   *One set of values; proportional.* Re-run `tools/eval.py` (columns change).
2. **Text by libadwaita roles, not px.** Section titles `.heading` in full
   ink; hints `.caption`; one muted role (70 % ink, about 4.9:1 on light).
   Follows the system font and Large Text. *Readable; platform conventions.*
3. **Search field uses the header width.** Packed at the start, expanding;
   left edge lines up with the chart; native height and radius; a search
   icon. Window controls: close only (minimise closed the picker anyway).
   Placeholder "Search, or try ‘food’". *Nothing cut off.*
4. **Side card** (decided): emoji at about 96 px, name, shortcode, tone line;
   shows the copied confirmation and the insert-fallback reason; skin-tone
   name in tone mode. *Feedback the user can trust.*
5. **Pinned category title** (decided) over the chart, with Ctrl+Up/Down to
   jump between sections; `_scroll_to` keeps the highlight clear of it.
6. **No row cut by a hard edge**: bottom fade; key hints move to a flat
   bottom bar. *Nothing overlaps, nothing is cut off.*
7. **One highlight**: drop the `:hover` cell fill (hover already moves the
   highlight). *One highlight at a time.*
8. **Hints follow the state**: "Esc close" only on an empty search, "Esc
   clear" with text, "Tab or Esc back" in skin tones; the tone heading is
   just "Skin tones"; no Enter/Ctrl+C offered with nothing to act on.
   *Keyboard first; one word per thing.*
9. **No results**: centred "No emoji found" with "Try another word, or a
   category like ‘food’."
10. **Home shows each emoji once**: Frequent leaves out what Recent shows;
    Recent is one row.
11. **Section titles line up with the glyph column.**
12. Small: per-word headings in quotes (“sister”) so they don't read as
    categories; key names stronger than their actions in hints; tidy
    `window.py` leftovers (unused `TONE_NAMES` gets used by the card, no-op
    replace, twin radii and alphas).

## Taste picks (made by Claude; Frank can overrule in the feedback round)

- Highlight: accent ring with a lighter 15 % fill (the 30 % fill goes muddy
  behind dark skin tones in dark mode).
- Minimum window 560 × 400 with the card always visible, rather than a
  second compact layout for very small windows. Default size stays.
- Search text at the normal body size (the 18 px text outweighed
  everything else).

## Later or maybe

- Scroll-rail category names (left out by Frank, 2026-11-06).

## How each item is checked

After screenshots (`capture.sh`, same states as before, light and dark,
default and minimum size) compared side by side with the before set; the
unit tests; `tools/eval.py` for item 1; then a human-feedback round on
Frank's machine (Wayland, Yaru, his scaling).
