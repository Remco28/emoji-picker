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
