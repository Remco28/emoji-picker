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

## Peer pass 2, 2026-11-05, plan v2 (b86e6a0); build started in parallel
Cast: fresh critic = Gemini gemini-4-argon-high (plan v2 + prototype at 9b9275e), read-only.
Predictions (written before it reported, in my notes, not committed first — so weak):
fewer HIGHs than pass 1, findings mostly in edge setups (non-US, multi-user).

| # | Finding | Reader (their rating) | Ours | From | How checked | Done |
|---|---|---|---|---|---|---|
| 12 | With every layout an IBus source, GNOME skips them until IBus is ready (login) or when it crashes, falling back to 'us' | Gemini (HIGH) | tier 1 (read GNOME 46 ibusManager.getEngineDesc / keyboard.js), MEDIUM: no effect on a US layout (owner); non-US users get US briefly at login or during an IBus crash. Inherent to decision 4 | new | read source | README limit; to owner as a decision |
| 13 | longname/language: "German (German, with emoji)"; get_languages_for_layout('de+nodeadkeys') = [] ; multilingual layouts mislabelled | Gemini (HIGH) | (1)(2) false, measured: "German (with emoji)", de+nodeadkeys → deu. (3) true: 'be' → French, 'ch' → gsw. LOW | new | ran XkbInfo on 11 layouts | fixed: language chosen to match the display name, else whole display name in brackets |
| 14 | Prototype user with only ('ibus','emoji-picker') left: component overwritten, source dropped, falls back to 'us', uninstall can't recover the layout | Gemini (HIGH) | tier 1 (traced in code), HIGH, setup not in use (owner kept ('xkb','us')) | new | reproduced in test | fixed: prototype layout read from the old component, becomes emoji-picker:<it>; test |
| 15 | Clone deleted → no installer for a layout added later; helper files missing from install | Gemini (HIGH) | helpers: tier 0 for the build (system.py is in the package). Re-run: tier 1, MEDIUM | new | read build | fixed: installed copy carries install.sh + data; `emoji-picker --setup`; test |
| 16 | sources then mru-sources written separately: GNOME resets the active layout | Gemini (MEDIUM) | tier 2 → checked: GNOME uses its in-memory MRU after start, so write order does not matter; after the login swap the first layout becomes active. LOW, declined | new | read keyboard.js _updateMruSources | decline → fix auditor |
| 17 | `sudo ibus write-cache` writes root's cache | Gemini (MEDIUM) | tier 0: the build never runs write-cache under sudo | n/a | read install/uninstall | none |
| 18 | `gsettings list-recursively` skips custom shortcuts, so the conflict check misses them | Gemini (MEDIUM) | tier 1, reproduced on a keyfile store | old (prototype) — fixed in passing since step 4 was rewritten | reproduced | fixed; test |
| 19 | Copy message tells a Japanese-IME user to rerun the installer | Gemini (MEDIUM) | tier 1 (read), MEDIUM | new | read build | fixed: names the active engine; xkb → `--setup` |
| 20 | `--shortcut` re-run orphans Super+. | Gemini (HIGH, on plan text) | built code already restores it; test added | n/a | test | test |
| 21 | Same-commit re-run writes into the live version dir | Gemini | built code: unique names; already tested | n/a | test | none |
| 22 | Substring match de vs de+nodeadkeys | Gemini | built code matches exact names; unit test added | n/a | test | test |
| 23 | sudo refused/cancelled mid-uninstall leaves half-removed state | Gemini (MEDIUM) | tier 1, LOW (re-run finishes it) | new | read | fixed: `sudo -v` before any change (install and uninstall) |
| 24 | Uninstall duplicates a re-added layout | Gemini | built code dedups; test added | n/a | test | test |
| 25 | A second Super+. while the first picker is inserting/copying is swallowed (window presented, then quits) | Gemini (MEDIUM) | tier 1, reproduced under Xvfb; MEDIUM, how it is used now | old (prototype) | reproduced | fixed: reopen a fresh picker when the first finishes |
| 26 | `-I` hides the script dir from sys.path | Gemini (LOW) | handled: launcher inserts current/; engine imports nothing local; IBus test runs it with -I | n/a | test | none |
| 27 | Cut versioned dirs (direct install + one rename) | Gemini (cut) | declined: one rename of a non-empty dir over another is not atomic (mv -T fails on non-empty); the symlink switch is, and is tested | n/a | n/a | decline → fix auditor |

Also found while building (not from a reader): the engine logged every cursor move,
a disk write on nearly every keystroke (fixed); picker.log never rotated (fixed).

Believed, and wrong: "the conflict check covers custom shortcuts" (prototype install.sh:92) —
`gsettings list-recursively` skips relocatable schemas.

## Fix audit, 2026-11-05, diff 9b9275e..bd3907f
Cast: fix auditor = Codex gpt-6-luna (diff, plan, declines; ran the tests: 63 OK, 1 skipped in its sandbox).

| # | Finding | Reader (their rating) | Ours | From | How checked | Done |
|---|---|---|---|---|---|---|
| 28 | Install overwrites a shortcut at our path named "Emoji Picker" whose command is someone else's | auditor (HIGH, reproduced) | tier 1, HIGH, a setup not in use | old (prototype guard checked the name only) | reproduced in test | fixed: name and command must be ours; test |
| 29 | Non-US layouts fall back to US while IBus is down (= decline 5) | auditor (HIGH, DOES NOT HOLD) | taken to the owner | new | read GNOME source | Frank chose: non-US layouts keep the plain layout as a backup (indicator shows for them); US unchanged |
| — | Round 3 guide missing | auditor | it was being written in parallel | n/a | n/a | human_feedback/round-2026-11-05-production/ |

Second opinions on declines: 1 HOLDS, 2 HOLDS, 3 HOLDS, 4 HOLDS, 5 DOES NOT HOLD (→ #29).
Not re-audited: the backup-layout change (#29) and the guard (#28) came after the audit; both are
small and covered by tests (72 OK). Said so to the owner.

Believed, and wrong: "documenting the US fallback is enough" (decline 5) — the auditor held the
goal I wrote myself ("never lose a working keyboard") against it, and the owner agreed.

## Mistakes the next author will make
- Trusting `gsettings list-recursively` to show every shortcut: it skips custom ones.
- Treating an `xkb` source next to our engine as "to convert": it may be the deliberate backup.
- Testing only with a US layout: GNOME's fallback hides every layout bug for US users.
- Changing the engine name format (`emoji-picker:<xkb id>`): sources in users' settings point at it.
