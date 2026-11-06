# Review-loop ledger: production readiness (install, upgrade, uninstall, Super+.)
*Kept by the review-loop skill. Safe to delete this folder once the work is done.*

Success question: can the owner, or a stranger who clones the repo, install with
one command, use Super+. to insert emoji with no extra keyboard indicator, upgrade
by re-running the installer, and uninstall back to their own settings, without
ever losing a working keyboard?
Rules confirmed with: Frank, 2026-11-05 (audience = owner + cloners, no .deb;
take over Super+.; English only; no indicator just because of this tool).
Reviewing: a change, from 9b9275e; old bugs filed in: BUGS.md (none so far).
Mode: started as the light review; two new HIGHs from peers made the design grow,
so plan v2 goes to a fresh peer (skill: "It stops being light when ...").

## Peer pass 1, 2026-11-05, plan v1 (787dc8c)
Cast: critic = Codex gpt-6-luna (plan + prototype); blind solver = Claude Opus 5.5
(PROBLEM.md + prototype at 9b9275e, no plan). Both read-only, fenced.

| # | Finding | Reader (their rating) | Ours | From | How checked | Done |
|---|---|---|---|---|---|---|
| 1 | One user's uninstall removes the shared component and files, breaking another user's sources and launcher | critic (HIGH); solver (registry proposed) | tier 1, HIGH, a setup not in use (one user) | new | read in plan §5 | v2: per-user registry under /usr/local/lib/emoji-picker/users; component = union; files removed only when no user is left |
| 2 | rm -rf old tree then mv new: a failed step leaves no working install | critic (HIGH); solver (versioned dirs + `current` link) | tier 1, HIGH, how it is used now (upgrade) | new | read in plan §1 | v2: versions/<ver>, atomic `current` symlink swap, previous version kept |
| 3 | Uninstall removes the shortcut by name only, losing a user's edit | critic (MEDIUM) | tier 2 → partly accepted: check the command is ours. Declined: keeping it when only the binding changed (its command would point at removed files) | new | read in plan §5 | v2; decline goes to fix auditor |
| 4 | Fresh install has a copy-only period until logout; make it plain | critic (MEDIUM) | tier 2, accepted (installer text). Prototype upgrade avoids the gap: keep the running old engine's source until finish-setup | new | reasoning from measured facts | v2 |
| 5 | Keeping every old engine forever accumulates | critic (LOW) | fixed by #1's registry | new | plan | v2 |
| 6 | `python3` from PATH may be a pyenv/venv without gi; engine dies silently | solver | tier 2, accepted: /usr/bin/python3 -I for engine and launcher | old (prototype has it too) but the change touches both lines, so fixed in passing | read engine.py shebang, bin/emoji-picker | v2 |
| 7 | Update mru-sources along with sources | solver | tier 2, accepted (cheap; GNOME filters mru anyway, read keyboard.js) | new | read GNOME 46 keyboard.js | v2 |
| 8 | `--doctor` command for diagnosing a stranger's or the owner's machine | solver | tier 3 idea, accepted (small, helps round 3) | n/a | n/a | v2 |
| 9 | Lock screen / login screen with only IBus sources | solver (risk) | checked: GNOME 46 keyboard.js keeps IBus enabled for password fields when all sources are IBus; greeter uses localed's system layout. Not a finding; owner checks unlock in round 3 | n/a | read GNOME 46 keyboard.js, gsd-keyboard strings | round 3 checklist |
| 10 | Cut the .desktop entry | critic | declined: on Wayland GNOME matches the window's app id to a .desktop file for its name and icon (Alt+Tab, notifications) | n/a | n/a | decline to fix auditor |
| 11 | Longname "US" so the menu reads exactly "English (US)" | solver | tier 3 (taste): kept "English (US, with emoji)" so the Settings list does not show two identical "English (US)" entries; for the owner | n/a | n/a | ask owner |

Believed, and wrong: "keeping every installed engine protects other users" (plan v1 §2) —
it protected their engines at install time but uninstall still removed everything.
