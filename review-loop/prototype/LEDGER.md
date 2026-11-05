# Review-loop ledger: emoji-picker prototype plan
*Kept by the review-loop skill. Safe to delete this folder once the work is done.*

Mode: **light review** (the owner made the product decisions; this is a new
build, so it escalates to the full loop if a critic, solver or auditor finds a
HIGH that is not old, or if the design grows as peers see it).

Success question: Can Frank press a shortcut, type a few words or a sentence,
see the emoji he means near the top of a big keyboard-navigable chart, press
Enter, and have it appear in the app he was typing in, with nothing left behind?

Rules confirmed with: Frank, in this session's chat (2026-11-03 to 2026-11-05);
quoted in PROBLEM.md "What he decided". Stakes (drafted by the author, not
separately confirmed): a personal prototype on Frank's own laptop; the cost of
failure is his time and, as the probe showed, a broken system emoji shortcut
until he logs out. Nobody else relies on it yet.

Reviewing: a new build, planned from d37e7cd (plan frozen at 5bf8528).

## Peer step: plan, 2026-11-05, plan at 5bf8528

Cast:
- Critic: Codex gpt-6-luna, read-only, got PLAN.md + PROBLEM.md + probe + README.
- Blind solver: Grok grok-4.7, strict sandbox, got PROBLEM.md + probe + README
  from d37e7cd, no plan.

Predictions (written before the readers report):
- The critic will push hardest on window focus under Wayland (section 7) and
  on the fake-context heuristics; I expect at least one HIGH there.
- The critic may object to arrows overriding the text cursor, and to FlowBox
  performance.
- The solver will most likely also choose a passive IBus engine plus a GTK
  window; the interesting difference will be whether it runs the picker as a
  resident process or one process per press, and how it tests enrichment.

| # | Finding | Reader (their rating) | Ours | From | How checked | Done |
|---|---|---|---|---|---|---|
| 1 | Insertion race: the plan's "new focus + 60 ms quiet" rule can fire before the measured 150 ms and commit into IBus's fake context | Codex (HIGH); Grok independently: "the engine must refuse false successes" | HIGH, tier 1 | new | Read: plan section 7 vs measured probe timing (150 ms delay, 7/7 ok) | Plan v2: never commit before the measured 150 ms; require the focus generation to advance; search box kept out of IBus (row 2); engine logs everything. Residual timing risk goes to Frank's test |
| 2 | A commit could land in the picker's own search box, which has an IBus context | Grok ("believe") | MEDIUM, fixed as a precaution | new | Read: plan step 1 relies on the picker's context; checked Gtk.Entry has `im-module` in GTK 4.14 | Plan v2: search entry uses `gtk-im-context-simple`, so IBus never sees the picker |
| 3 | Resident app + activation-token forwarding is unmeasured; a new process per shortcut is the measured path | Codex (MEDIUM); Grok chose per-process unprompted | MEDIUM, tier 1 | new | Two readers on different models; probe data | Plan v2: one process per press (measured to focus). Cold start measured under Xvfb; resident mode only if start is too slow. Cuts autostart, D-Bus service and token code |
| 4 | Clipboard fallback is not insertion | Codex (gap); Grok: "no clipboard" | MEDIUM, owner decision | new | Read | Plan v2: kept as an explicit degraded mode that is reported as a failure, never counted as success. Flagged to Frank as a default he can change |
| 5 | Uninstall restores the whole saved lists, discarding changes made after install | Codex (MEDIUM) | MEDIUM, tier 1 | new (also in probe/setup.sh, which is old and not used again) | Read probe/setup.sh: restores the full saved `sources` and keybinding lists | Plan v2: remove only our own entries |
| 6 | Eval rewards presence in top N, ignores junk; noise rule undefined; same model must not grade itself | Codex (MEDIUM); Grok (decoys, rank comparison, nonsense must not share a stable top 5) | MEDIUM, tier 1 | new | Two readers | Plan v2: decoys that must rank below, rank comparison per query, hit@1 + MRR, defined noise rules, a blind A/B relevance judge from another vendor on a sample |
| 7 | The held-out set is model-written, not real searches | Codex | LOW | new | Read | Plan v2: Frank's own 10 queries go into his test round |
| 8 | "Fake context sends no cursor location" is unsupported | Codex | tier 1 | new | Checked: the selftest client never sent cursor locations, so the observation proves nothing | Plan v2: dropped from the logic; logged only |
| 9 | Font cutoff can't validate sequences; cut it | Codex (MEDIUM) | **Declined** | new | Checked: data has 25 emoji of versions 16-18; this machine's Noto 2.047 stops at 15.1, so without a cutoff they draw as boxes. Noto ships every RGI sequence up to its version, so a per-version cutoff covers sequences | Kept. Decline goes to the fix auditor for a second opinion |
| 10 | Cut typo tolerance | Codex | Accepted | new | Taste plus junk risk | Cut; add later if missed |
| 11 | `claude -p` may not accept the Sonnet 5.5 id | Codex (uncertain) | Dies | new | Ran it: `claude-sonnet-5-5` answered in 3.2 s | none |
| 12 | Headless scripted focus test does not prove Wayland timing | Codex (LOW) | Agreed, already in plan | new | Read | Kept as a regression test only; stated so |
| 13 | Engine must be the active global source; confirm after install | Codex; Grok | Accepted | new | Read | Plan v2: installer checks `ibus list-engine`; selects the engine with `ibus engine` if visible, else asks for one logout |
| 14 | Keep a separate hand-written phrase table | Grok | **Declined** | new | Reason: the eval must measure the LLM enrichment alone; a hand table is added only when a measured gap needs it | Decline goes to the fix auditor |
| 15 | Tab, not Ctrl+Enter, for skin tones | Grok | tier 3 (taste), adopted | new | | Plan v2: Tab opens tones |
| 16 | Super+., Ctrl+C/V, Shift while the engine is selected are unmeasured | Grok | Accepted | new | | Into Frank's test round |
| 17 | GridView for 2000 cells | Grok ("believe") | Declined | new | Checked: GridView has no section headers in GTK 4.14 (`header-factory` only on ListView) | FlowBox kept, speed measured |

What happened against the predictions: focus on show and the fake context drew the HIGH, as predicted, but from the insertion side, not the show side. The solver did choose a passive engine + GTK window, and chose one process per press, which is what the plan moved to. Arrow keys and FlowBox speed drew no objection.
Believed, and wrong: "real text fields send a cursor location, the fake context did not in testing" (row 8): my own test client never sent one.

Escalation: row 1 is a HIGH that is not old, so this is no longer a light review. Per the skill's peer step, the plan is revised and given to a fresh group; it got **smaller** (no resident app, no D-Bus service, no token forwarding, no typo tolerance), which the skill reads as "build it" once a fresh pass finds only details.

## Peer step: plan v2, 2026-11-05, plan at 826e059

Cast (fresh group, neither saw v1 or the first pass's reports):
- Critic: Gemini gemini-4-argon-high (agy), read-only, PLAN v2 + PROBLEM + probe + README.
- Critic: Grok grok-4.7 (new instance), strict sandbox, same materials.

Predictions (written before the readers report):
- No new HIGH on insertion; the 150 ms floor + generation rule matches what was measured.
- Most likely MEDIUMs: cold start of a fresh Python/GTK process (the 400 ms target may be tight), and whether `gtk-im-context-simple` still handles dead keys/compose (it does compose; Frank uses plain US).
- Possible: a question on whether the generation can advance from the fake context alone (it should not after hide, since the fake context already had focus while the picker showed).

Note: the first attempt to prepare this round's copies was declined by Frank after T3 Code flagged the command as unsafe (unquoted `rm -rf $R` on a computed path, no guard). Redone with quoted paths, `${R:?}` guards, a new `mktemp` folder and no deletes of existing folders.

Runs: Gemini's first run produced no answer (it read a file outside its copy, headless mode auto-denied it and discarded the reply; log kept as gemini.run1). Rerun with one added brief line: read only inside the working directory. Grok timed out at 20 minutes (exit 124) mid-deliberation with no answer; its unfinished reasoning is kept and used only as leads, each checked against the plan before it counts.

| # | Finding | Reader (their rating) | Ours | From | How checked | Done |
|---|---|---|---|---|---|---|
| 18 | Eval scores a flat top-N, the window shows a row per concept of up to two lines: a pass can leave 🙏 below the fold | Gemini (HIGH); Grok's reasoning reached it too | HIGH, tier 1 | new (v2) | Read plan v2: no rule for how sections become a ranking | v3: search returns ordered sections; eval scores the exact display order, in cells, at the default window's column count; one line per concept row |
| 19 | Greedy longest-phrase splitting collapses "tent fire" into one concept once enrichment adds such phrases | Gemini (HIGH); Grok reasoned the same about "american" | HIGH, tier 1 | new (v2) | Read plan v2 section 5 | v3: no segmentation. Every content word is a concept; emoji matching the most concepts rank first; a label or keyword phrase found contiguously in the query adds a bonus |
| 20 | Clipboard fallback after hiding cannot work on Wayland; the plan's "probe showed the clipboard survives" is not what the probe measured | Gemini (MEDIUM, "know") | MEDIUM, tier 1 | new (v2) | Read probe/picker_sim.py: copy mode set the clipboard in the click handler while the window was visible and focused | v3: engine checked before hiding; if it can't insert, copy while still focused and say so in the window; Ctrl+C copies the highlighted emoji; a post-hide timeout only notifies |
| 21 | Stopword removal keeps "looking good" after "isn't"; filler words get rows above "pray" | Gemini (MEDIUM); Grok reasoned the vet sentence ends below the fold | MEDIUM, tier 1 | new (v2) | Read plan v2 section 5 | v3: a negation drops the next content word; concept rows ordered most specific first; vet sentence gets decoys 👍 😊 😎 |
| 22 | Tuning on the 60 held-out queries makes them a validation set | Gemini; Grok reasoning | MEDIUM, tier 1 | new (v2) | Read plan v2 4c | v3: held-out split into a tuning half (failures visible) and a test half (totals only until the final run) |
| 23 | Enrichment cache is not invalidated when the prompt or model changes | Grok reasoning only | MEDIUM, tier 1 | new (v2) | Read plan v2 4b ("rerun only fills gaps") | v3: cache keyed by prompt hash + model |
| 24 | `Gtk.SearchEntry` has no `im-module`; key controller must use the capture phase | Gemini (LOW, "know") | LOW, tier 1 | new (v2) | Checked: GTK 4.14 SearchEntry has no `im-module` and is not an Entry subclass | v3: plain `Gtk.Entry` with `im-module`; key controller in CAPTURE phase |
| 25 | GNotification is dropped without a .desktop file | Gemini (LOW, "know") | LOW, tier 2, fixed cheaply | new (v2) | Not reproduced; the fix costs nothing | v3: org.freedesktop.Notifications over D-Bus |
| 26 | Emoji 15.1 has no single-code-point emoji, so per-version detection drops it; fallback fonts fool a rendering check | Gemini (LOW, "know") | LOW, tier 1 | new (v2) | Checked: data's v15.1 entries are all sequences; Pango drew v17/18 from Unifont, passing a width test; `fc-list :charset` shows Noto 2.047 has U+1FAE9 (16.0) but not U+1FAEA (17.0) | v3: cumulative check over single code points in the Noto font file's own charset |
| 27 | Generation counter could be inflated by a fake-context focus_in after hiding | Grok reasoning only | Not reproduced; logged | new (v2) | Read: the fake focus_in happens when the picker takes focus, before Enter; the 30 ms quiet rule covers churn. Unmeasured on Wayland | Kept as is; engine logs settle it in Frank's test. Goes to the fix auditor as a decline |
| 28 | "150 ms measured to work" overstates it: the measured success was the first retry, 150 ms + up to 50 ms | Grok reasoning | LOW, tier 1 | new (v2) | Read PROBLEM.md | v3 wording fixed |

What happened against the predictions: no new HIGH on insertion (right). The predicted MEDIUMs (cold start, compose) did not come up; instead both HIGHs were in search segmentation and in how the eval reads the layout, which I did not foresee.
Believed, and wrong: "this machine's Noto (2.047) stops at 15.1" (row 9's reason): it has 16.0, lacks 17 and 18. The decline in row 9 still holds (the cutoff is needed for 17-18). Also "the probe showed the clipboard keeps the text after the process exits" (row 20): it showed that only for a copy made while focused.

Decision: no third reading pass. Both HIGHs concern ranking and the eval, which the frozen eval measures directly once built; a reader predicting ranking quality is weaker evidence than running it. The plan did not grow (segmentation removed; clipboard path narrowed). Frank was told the second pass was on the cautious side and accepted it; he was not asked about a third.

## Build notes
- 2026-11-05: answer key frozen at 634d1ed (stories 2, personas 50, shortcodes 5, held-out 60 by Codex split 30/30 seed 20261105, noise 20). Codex's held-out set needed no edits (every emoji exists).
- 2026-11-05, before the first eval run: the pass rule for multi-concept queries and sentences changed from "within the first N cells" to "within the first 3 / 5 lines". Reason: each section starts on a new line and a one-line concept row is a full line (14 cells), so a cell count would fail emoji that are plainly on the first screen. Single-concept queries keep "first 5 cells". No results existed when this was changed.
- Discipline slip (2026-11-05): during the first tuning runs, `tools/eval.py` printed the held-out **test** half's totals (never its failures) on every run, and I saw them while choosing ranking changes. From here on, variants are chosen with `--tune-only`, which leaves the test half out entirely; the test half is opened once at the end. Its final number should be read with this in mind.

## Enrichment results (2026-11-05)

Final settings chosen with `--tune-only`; the test half was then opened once (`eval-final.json`).

| source | baseline | enriched |
|---|---|---|
| held-out test half (main number) | 19/30 | **27/30 (90%)** |
| held-out tuning half | 21/30 | 28/30 |
| personas | 50/50 | 50/50 (top-1 39 -> 42) |
| shortcodes | 5/5 | 5/5 |
| stories | 0/2 | 0/2 |

Targets (plan v3 4c): test half >= 85%: **met**. Enriched beats baseline on pass, hit@1 and MRR for every source: met except stories (pass 0/2 both; MRR 0.67 -> 1.00) and personas pass (50/50 both). Regressions <= 2: **met (0)**. Both stories pass: **missed**. Noise rules: **met**. Blind judge prefers enriched on >= 2/3 of 30 queries: **missed** (14 enriched, 4 baseline, 12 split or same; relevant of top 10: 5.5 vs 3.1). Baseline won at least once mostly on multi-word queries, where the new first line mixes all-words matches and each word's pick.

Stories, as they now behave: "american flag happy" shows 🇺🇸 first and the happy faces within the first three lines, but fails the frozen decoy rule because 🇦🇸 is second. The vet sentence shows 🙏 first and dogs on the first line but no hospital: no generated term links "vet" to 🏥 (the prompt deliberately does not mention "vet", which is an answer-key word). A variant that passed story 1 (evidence bonus off, one all-words match before the picks) cost a tuning query and a regression, so it was not taken.

Prompt v1 used "american" and "vet" as examples, which are story words; prompt v2 removed every example that appears in the answer key (checked by script) and its results are the ones reported.

Bugs the build's own tests caught: an empty `<layout_variant>` in the engine file makes IBus refuse to activate the engine ("Set global engine failed: Operation was cancelled") - the installer would have produced exactly that for Frank's plain "us" layout; the engine template comment contained the placeholders and got rewritten by the substitution; the search box grabbed focus with its text selected.

## Fix auditor on the build, 2026-11-05, at 4d6454a

Cast: Codex gpt-6-luna, workspace-write in a fenced copy (checksummed before and after: nothing changed; repo unchanged). Got PLAN v3, the code, the list of changed files, and the four declined findings (rows 9, 14, 17, 27). Report: fix-audit-codex.md.

| # | Finding | Reader (their rating) | Ours | From | How checked | Done |
|---|---|---|---|---|---|---|
| 29 | Installer writes to a fixed shortcut path; a shortcut already there would be overwritten, and uninstall would reset it | Codex (HIGH, conditional) | MEDIUM: a setup not in use (GNOME names user shortcuts custom0, custom1...), fixed because it is cheap | new | Read install.sh / uninstall.sh | Install refuses before changing anything if the path holds a shortcut not named "Emoji Picker"; uninstall touches the path only if it is ours. Tested on a throwaway settings store |
| 30 | Ctrl+C guard broken: `get_selection_bounds()` returns a truthy tuple | Codex (MEDIUM, "know") | **Declined: does not reproduce** | new | Reproduced under Xvfb: no selection returns `()`, falsy; Ctrl+C copied in the real window, read back and confirmed | Sent back once: Codex says HOLDS, caveat that a newer PyGObject might return (flag, start, end). Guard now handles both shapes (`has_selection`) |
| 31 | Ctrl+C does not close the picker, unlike plan section 6 | Codex | LOW, tier 1 | new | Read window.py | Ctrl+C now closes 1.2 s after the copy is confirmed; tested in the window under Xvfb |
| 32 | Installer does not run `ibus engine` when IBus already lists the engine (plan section 8 says it does) | Codex | Deviation kept, recorded | new | Read install.sh | Deliberate: GNOME owns input-source switching; calling `ibus engine` behind its back can leave the top-bar indicator wrong. The installer tells the user to pick it with Super+Space instead |
| 27 (second opinion) | My decline "fake-context focus may raise the generation: not reproduced, logged" | Codex: DOES NOT HOLD ("lack of reproduction does not establish safety") | **Accepted; fixed** | | Found that IBus 1.5.27+ names the focused client to engines created with has-focus-id; tested with a private daemon: the internal context reports client "fake" | Engine now created with has-focus-id; status reports the client; the picker never counts "fake" as an app; the engine refuses commits into it. New test 3b covers it. Older IBus falls back to the generation rule |
| 9, 14, 17 (second opinion) | font cutoff kept; no hand phrase table; FlowBox not GridView | Codex: HOLDS, HOLDS, HOLDS | declines stand | | | |

Believed, and wrong: "the engine cannot tell IBus's fake context from a real app" (said in plan v1-v3, the probe and row 27). It can, with has-focus-id, on IBus 1.5.27+.

## Mistakes the next author will make
- Writing a Unix socket under the session scratchpad: its path is longer than the 108-byte limit and ibus-daemon silently never starts.
- Putting an empty `<layout_variant>` in the engine component: IBus refuses to activate the engine with "Operation was cancelled". Leave the element out.
- Naming template placeholders inside a comment of the same template: the substitution rewrites the comment.
- Watching the held-out test half's totals while tuning: use `tools/eval.py --tune-only`.
- Trusting a Pango rendering test for emoji support: Pango silently falls back to Unifont, so missing emoji "render". Check the emoji font's own charset.
- Running `ibus restart` in an installer: it broke Frank's Super+. until he logged out.
