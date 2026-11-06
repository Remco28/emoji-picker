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
- **Keyboards are replaced, not added** (Frank, 2026-11-05): each layout becomes the same layout "with emoji", so a single US layout shows no keyboard indicator. A non-US layout also keeps its plain version as a backup, because GNOME types US whenever IBus is down (Frank chose safety over hiding the indicator for those users).
- **Super+. belongs to the picker**; IBus's own emoji picker keeps Super+; and gets Super+. back on uninstall.
- **Categories are words, never icons** (Frank, 2026-11-06): no icon tab bar. Category words are search words ("food", "flags"); the search box hints at this; the current category title stays pinned at the top of the chart while scrolling, and Ctrl+Up/Down jumps between categories. A scroll-rail of names was considered and left out.
- **The selected emoji is previewed in a side card** on the right, at roughly passport-photo size, with its name and shortcode (Frank, 2026-11-06: a laptop has more spare width than height).
