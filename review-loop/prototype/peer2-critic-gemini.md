### 1. Built as written, does it reach the goal on Frank’s setup?

**Mostly yes on the primary happy path, with two concrete failure scenarios where it breaks or fails to show the right emoji near the top.**

The core Wayland + IBus insertion architecture in [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L171-L246) is sound for Frank’s setup (Ubuntu 26.04, GNOME 50 on Wayland, IBus 1.5.34):
* **I know** that in GTK 4 on Wayland (`gtk/gtkimcontextwayland.c` and `gtk/gtkimmulticontext.c`), `zwp_text_input_v3` is only enabled when `GtkIMContextWayland` is instantiated. When the search entry uses `gtk-im-context-simple`, the picker never enables `zwp_text_input_v3` and never creates an `IBusInputContext`.
* **I know** that in Mutter / GNOME Shell (`src/wayland/meta-wayland-text-input.c`, `js/misc/inputMethod.js`) and `ibus-daemon` (`bus/ibusimpl.c`), when the picker window opens and takes keyboard focus, the previous app loses focus, sends `focus_out`, and `ibus-daemon` immediately moves the engine to its internal `fake_context` (emitting `focus_in`, which becomes generation `g0`). While Frank types in the picker, the engine stays parked on `fake_context` at `g0`. When Frank presses `Enter` and the picker calls `win.set_visible(False)`, Mutter returns Wayland keyboard focus to the previous app, which re-enables its text-input / IBus context, raising the engine’s generation to `g0 + 1`. Waiting for `>= 150 ms`, `generation > g0`, and `30 ms` of focus quiet will reliably land the commit in the target app with nothing left behind.

However, **built literally as written, it fails in two concrete scenarios**:

1. **Scenario A — Multi-word queries and sentences in search ([PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L150-L168)):**
   * **Greedy phrase collapse:** Section 5 splits the query *"greedily into the longest known phrases of up to 3 words; the rest are one-word concepts."* Once `tools/enrich.py` generates 10–25 terms (of 1–3 words) for 1,958 emoji (~20,000–48,000 phrases), common 2-word combinations that a user intends as **two separate concepts** (e.g. `"happy dog"` or `"tent fire"` from [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L86-L87)) will frequently exist as a 2-word enriched phrase on a single emoji (e.g. `"tent fire"` on 🏕️ `camping`). The greedy splitter collapses `"tent fire"` into **one** concept instead of `["tent", "fire"]`, so the per-concept rows for `"tent"` (⛺) and `"fire"` (🔥) are never created.
   * **Negation + sentence clutter on Frank’s vet story:** When Frank types `"my dog went to the vet and it isn't looking good, please pray for him"`, Section 5 removes English stopwords (`my`, `to`, `the`, `and`, `it`, `isn't`, `for`, `him`). Stripping `"isn't"` turns `"isn't looking good"` into `"looking"`, `"good"` (or the known 2-word phrase `"looking good"`), while non-stopword filler words (`"went"`, `"looking"`, `"good"`, `"please"`) each become concepts BEFORE `"pray"`. Because Section 5 gives each concept *"its own row of at most two lines"* (~20–30 emoji per 2-line FlowBox at 760 px width), the chart shows cheerful thumbs-up / smiling emoji for `"looking good"` / `"good"`, and pushes `"pray"` (🙏) down to the 6th or 7th section (off the bottom of a 560 px window).
2. **Scenario B — Clipboard fallback after hiding the window on Wayland ([PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L224-L241)):**
   * If Frank triggers the picker from an app without IME support (or before logging out after first install, or after accidentally pressing `Super+Space`), Section 7 Step 1 **hides the picker window first**, polls for up to 2 seconds while unfocused (Step 2), and **then** copies the emoji to the clipboard and exits (Step 3).
   * **I know** that in Wayland (`wl_data_device.set_selection`) and Mutter (`src/wayland/meta-wayland-data-device.c`), a client can only set the clipboard selection while it owns focus using a valid input serial from its focused surface. Calling `Gdk.Clipboard.set()` up to 2 seconds *after* `win.set_visible(False)`—when the picker surface is unmapped and the target app owns keyboard focus—is silently rejected by Mutter.
   * **I also know** that on Wayland, `set_selection` only advertises MIME types; Mutter’s clipboard manager (`MetaSelection`) must asynchronously send `wl_data_source.send(mime_type, fd)` back to the client while its GLib main loop is still running. If the process calls `clipboard.set()` and exits immediately, the socket closes before the data pipe is written, leaving the clipboard untouched.

---

### 2. Decisions that are wrong or will not work as described

#### HIGH: Sectioned UI ("up to two lines per concept") vs. flat Top-N ranking in `search.py` and `eval.py`
* **Where:** [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L77-L79), [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L161-L168), [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L188-L196).
* **Why it fails or misleads:** Section 4a defines passing as *"every group has a member in the top N (N = 5 for one concept, 10 for multi-concept queries, 12 for sentences)"*, and Section 4c sends flat top-10 lists to the blind judge. Meanwhile, Sections 5 and 6 state that when no single emoji matches all concepts, the UI displays *"a row per concept"* where *"each concept then gets its own row of at most two lines"*. In a 760 px window, two lines of a FlowBox hold ~20–30 emoji:
  * If `search.py` flattens sections sequentially (Concept 1’s two lines, then Concept 2’s two lines, etc.), Concept 1 alone consumes ranks 1–20+ whenever it has >= 10 matches (e.g., `"happy"` or `"dog"`), making it impossible for Concept 2 to pass `N = 10` or for the 5th–7th concept in a sentence (`"pray"` in the vet sentence) to pass `N = 12`.
  * Conversely, if `search.py` round-robin interleaves concepts to produce a flat list for `eval.py` while `window.py` still renders two full lines per concept section, `eval.py` will score 🙏 as inside the top 12 even though in the actual window 🙏 sits below 5–6 multi-line sections (`dog`, `went`, `vet`, `looking`, `good`, `please`), far from the top of the chart.
* **Fix:** Cap per-concept rows tightly for multi-concept/sentence queries (or drop low-signal sentence words and show one combined row of top-scoring per-concept picks before the per-concept breakdown), and ensure `eval.py` scores the exact visual reading order of the chart.

#### HIGH: Greedy longest-phrase splitting collapses multi-concept queries once enriched phrases exist
* **Where:** [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L105-L111), [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L156-L166).
* **Why it fails:** `tools/enrich.py` adds up to 25 1–3 word phrases per emoji. If a user types two words intending two separate emoji concepts (e.g., `"happy dog"`, `"tent fire"`), and *any* single emoji has that 2-word string as an enriched phrase, greedy longest-phrase matching turns the query into a **single** 2-word concept instead of two 1-word concepts. That suppresses the individual concept rows and hides emoji that match `"tent"` (⛺) or `"fire"` (🔥) individually.
* **Fix:** Only treat a multi-word span as an indivisible phrase concept if it comes from a high-confidence phrase dictionary (labels/CLDR tags or phrases whose constituent words don’t independently form strong concepts), or always allow constituent 1-word concepts to contribute when a multi-word enriched term matches only a tiny number of emoji.

#### MEDIUM: Clipboard fallback in Section 7.3 happens after hiding the window and losing Wayland focus
* **Where:** [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L224-L241).
* **Why it fails:** **I know** that Mutter rejects `wl_data_device.set_selection` from an unmapped, unfocused Wayland client (which is the picker’s state 2 seconds after `win.set_visible(False)`), and that exiting immediately after `Gdk.Clipboard.set()` kills the Wayland connection before `MetaSelection` finishes the async `wl_data_source.send` read.
* **Fix:**
  1. Check whether the engine is reachable and active *before* calling `win.set_visible(False)`; if not, set the clipboard while the picker still has focus and pump the main loop for ~100 ms before hiding/quitting.
  2. For the 2-second focus-timeout fallback (apps with no IME support), either stage the clipboard while still focused before hiding (Wait: staging always clobbers the clipboard, which Section 1 avoids—so only clobber if needed by briefly re-presenting/keep-alive, or understand that on Wayland `wl_data_device` cannot be claimed without focus).

#### MEDIUM: Stopword removal strips negations (`"isn't"`) and leaves filler words as full concept sections in sentences
* **Where:** [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L150-L166).
* **Why it hurts:** In `"my dog went to the vet and it isn't looking good, please pray for him"`, removing `"isn't"` turns `"isn't looking good"` into `"looking good"` / `"good"`, surfacing positive/happy emoji (👍, 😎, 😊) in their own concept section, while words like `"went"` and `"please"` also spawn concept sections ahead of `"pray"`.
* **Fix:** Keep negation tokens (`not`, `no`, `never`, `n't`) attached to the following word (or suppress positive matches following a negation), and rank/filter concept sections in sentence queries by concept specificity (IDF / max match weight) so high-specificity concepts (`dog`, `vet`, `pray`) rank above generic words (`went`, `looking`, `good`).

#### LOW: Desktop notification on fallback will be dropped if sent via `Gio.Application.send_notification` without a `.desktop` file
* **Where:** [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L29), [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L235-L236), [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L248-L263).
* **Why:** **I know** that on GNOME Shell, `Gio.Application.send_notification()` uses `org.gtk.Notifications`, where GNOME Shell’s `GtkNotificationDaemon` resolves `<application-id>.desktop` via `Shell.AppSystem` and silently drops notifications when no matching `.desktop` file is installed. Since `install.sh` does not install a `.desktop` file, `insert.py` must call `org.freedesktop.Notifications.Notify` over D-Bus (or `notify-send`) directly.

#### LOW: `Gtk.SearchEntry` does not have an `im-module` property in GTK 4
* **Where:** [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L179-L180).
* **Why:** **I know** that in GTK 4 (`gtk/gtksearchentry.c`), `Gtk.SearchEntry` subclasses `Gtk.Widget` directly (not `Gtk.Entry`) and does not expose an `im-module` GObject property. Setting `gtk-im-module` on `Gtk.Settings.get_default()` (or setting `im-module` on `Gtk.Entry` or on `search_entry`'s internal `Gtk.Text` child) works as intended. (Also, **I know** the window’s `Gtk.EventControllerKey` must use `Gtk.PropagationPhase.CAPTURE` so `Left`/`Right`/`Tab`/`Enter` are caught before `Gtk.Text` handles them.)

#### LOW: Emoji 15.1 has zero single-code-point emoji for `fonts.py` version detection
* **Where:** [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L60-L68).
* **Why:** **I know** from Unicode Emoji 15.1 (UTR #51) that Emoji 15.1 (like 12.1 and 13.1) added **zero** single-code-point emoji—all 118 new emoji in 15.1 are ZWJ sequences of older code points (`🙂‍↔️`, `🐦‍��`, `🍋‍🟩`, `🍄‍🟫`, `⛓️‍💥`). If `fonts.py` checks per-version single-code-point sets and skips empty sets, it will detect `15.0` instead of `15.1` on the dev machine’s Noto 2.047 and hide Emoji 15.1. Checking cumulative single-code-point coverage up to version `V` avoids dropping 15.1 on Noto 2.047.

---

### 3. Does the enrichment evaluation (Section 4) really test what it claims?

**Partially—the pre-committed answer key, cross-vendor held-out set, noise rules, and blind A/B judge are well-designed, but three gaps can allow `eval.py` to pass while the real UI underperforms:**

1. **Flat Top-N in `eval.py` vs. multi-row concept layout in the UI (see HIGH finding above):**
   Unless `eval.py` scores the exact flattened order of the visual sections rendered by `window.py` (including all items shown in earlier concept rows), `eval.py` can report a top-10 or top-12 pass for multi-concept/sentence queries whose later concepts are actually pushed far down the window by earlier 2-line concept rows.
2. **No decoys on the vet sentence in Section 4a ([PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L82-L84)):**
   `"american flag happy"` specifies decoys (`🇦🇸` and `🏈`), which forces 🇺🇸 and a happy face to outrank those decoys. The vet sentence (`"my dog went to the vet and it isn't looking good, please pray for him"`) has **no decoys**, and a decoy only fails a query if it outranks the *first* acceptable emoji of any group. If `"isn't looking good"` (after stopword removal of `"isn't"`) pulls 👍, 😊, or 😎 into the top 12 alongside 🐕, 🏥, and 🙏, the test still passes.
3. **Iterative prompt/ranking tuning against the 60 held-out queries ([PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L128-L144)):**
   Section 4c prints the regressing/failing queries on each run and says: *"If targets are missed I change the prompt or the ranking (never the answer key) and rerun."* Once the author inspects which of the 60 held-out queries failed and adjusts the prompt or ranking weights to fix them, the held-out set becomes a validation set rather than a true blind test set (though recording every run in `LEDGER.md` makes this visible).

---

### 4. Does anything contradict `PROBLEM.md`?

All of Frank’s 8 scope and product decisions in [PROBLEM.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PROBLEM.md#L11-L38) are respected.

There is **one contradiction with the measured facts** in [PROBLEM.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PROBLEM.md#L54):
* [PLAN.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PLAN.md#L237-L238) justifies copying to the clipboard *after* hiding the window and waiting up to 2 seconds by claiming: *"(The probe showed the clipboard keeps the text after the process exits.)"*
* In reality, [PROBLEM.md](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/plan/PROBLEM.md#L54) measured [picker_sim.py](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/probe/picker_sim.py#L215-L222) in `--mode copy`, where [`App.on_pick`](file:///home/frank/.cache/emoji-picker-review/plan-r2.yslb/gemini/probe/picker_sim.py#L215-L222) called `Gdk.Display.get_default().get_clipboard().set(char)` **while the window was still visible and focused** (during the button click handler) and **returned without hiding or exiting** until Frank manually closed the window later. Inferring that a Wayland client can hide its window, wait 2 seconds unfocused, call `clipboard.set()`, and immediately exit is not what the probe measured and does not work under Wayland.

