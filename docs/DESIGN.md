# Design decisions

Taste choices, recorded so nobody asks again. Values live in
`emoji_picker/design.py`.

- **Motion: instant.** Nothing animates; results replace each other on every keystroke.
- **Colours follow the system** (libadwaita roles: accent, window text); light and dark both work.
- **Words**: "emoji" (never "icon" or "symbol"), "skin tone", "insert" (into the app), "copy" (to the clipboard), "Recent", "Frequent", "Best matches", "Related".
- **Esc backs out one level**: skin tones → results; results → empty search; empty search → close.
- **Left/Right move the highlight**, not the text cursor in the search box (Frank: keyboard first, mouse second).
- **Skin tones open in place** (Tab), not in a popover: the chart shows the variants, Tab or Esc returns.
- **The picker never claims an insert it cannot see.** On success it simply closes; a copy is confirmed by reading the clipboard back before it says "Copied".
