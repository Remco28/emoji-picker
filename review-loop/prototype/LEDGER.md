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
