I'll read the problem, the probe results, and the repo README before writing the plan.The prototype is two processes. A passive IBus engine stays selected as Frank’s input source and commits the emoji. A short-lived GTK 4 picker, started by a GNOME shortcut, only chooses it.

## Architecture

The engine is the probe engine, kept. IBus loads it only from `/usr/share/ibus/component` (known). GNOME starts it by selecting it as the global engine, not by a per-context `set_engine` (known). `do_process_key_event` returns false, so US typing still reaches the app (known). Another process asks it to `commit_text` over a `0600` socket in `$XDG_RUNTIME_DIR`. That path already delivered 😀 👍🏽 ❤️ 👨‍👩‍👧‍👦 🏳️‍🌈 🇨🇦 into Wayland apps, including the terminal (known).

The picker is a new process per shortcut, as in the probe (known). It is a normal `Gtk.ApplicationWindow`, not a layer-shell overlay and not an IBus lookup table. On Enter or click it hides, waits 150 ms, then retries the commit every 50 ms. In the probe the first try failed and the next try worked within 50 ms (known). It quits after an `ok`. Give up around 2 s and show a failure. No clipboard: copy leaves the emoji behind, and RemoteDesktop Ctrl+V misses the terminal (known).

The engine must refuse two false successes. With no app focused, IBus still sends `focus_in` and accepts a commit that is then dropped (known). The probe’s “focused” flag does not catch that. A `Gtk.Entry` in the picker would be worse: I believe Wayland GTK 4 text widgets take an IBus context through text-input, so a commit could land in the search box. The query is drawn text plus a window `EventControllerKey`. I know an IM context is created for text widgets; I believe a window that only listens to keys does not create one. Confirm both on his machine before building search.

Recents and frequency live in `~/.local/state/emoji-picker/`. The engine never sets a preedit, so closing the picker leaves nothing in the app.

## Search by meaning

Ship one JSON index built on the dev machine. No model at runtime (his decision). Source is emojibase 17? 18.0.0: label, tags, group, order, tones, five shortcode sets.

`claude -p` runs once per emoji, seeing only the CLDR name, tags, and group, and returns at most 25 lowercase keywords a person would type, including inferences (`vet` → hospital, sick). Drop stopwords. Drop any keyword attached to more than a small number of emoji, so “american” cannot glue every flag to football. Keep a separate hand phrase table (“american flag”, “isn’t looking good”) outside the LLM file so it cannot paper over a bad run.

At runtime, tokenize, drop stopwords, and score the sum of per-token weights: exact shortcode, then label word, then enriched keyword, then original tag. A phrase hit adds a bonus. Cap how many top slots one token can fill, then backfill, so a sentence surfaces dog and prayer, not twenty dogs. Empty query: recents, then frequent, then the catalog in emojibase order. A leading `:` searches shortcodes only. Skin tone is a variant of the highlighted base, not its own search hit. The untuned keyword spike was under 10 ms (known); this index stays in memory.

Test the enrichment before the window, or it will grade itself. Write the expectation file first, from his sentences and the failed spike, and do not let `claude` read or edit it. Cases name the emoji that must land in the top N and the decoys that must rank worse: for “american flag happy”, 🇺🇸 and a happy face above 🇦🇸 and 🏈; for “vet” and the dog/vet/pray sentence, dog, hospital or stethoscope, folded hands, and church. Run every case on the base index and the enriched index. Count a win only when the enriched rank is better. Fail the build if any keyword is too common or any emoji exceeds 25 keywords. Twenty nonsense queries must not share a stable top 5. Read keywords for about 30 random emoji by eye. Do not ask the same model to mark its work.

## Window and keys

Large, centered. Top line is the query. Below is a grid: recents, frequent, then hits or the full chart, drawn with Noto Color Emoji (known installed).

Arrows move the highlight. Enter inserts it. Escape or focus-out quits with no insert. Printable keys append to the query. Backspace deletes. Page Up/Down move a page. Tab opens the tone strip when emojibase has variants; arrows move along it; Enter inserts that variant; Tab returns. Click inserts through the same path. Results refresh on each key. I believe `Gtk.GridView` will hold about 2000 cells; check under Xvfb by walking from the first cell to the last.

## Install and uninstall

Same shape as `probe/setup.sh`, which already ran on his machine. Back up `org.gnome.desktop.input-sources` sources and the custom-keybinding list. `sudo install` the component XML. `ibus write-cache`. Append `('ibus', 'emojipick')` with layout `us`. `ibus engine emojipick` to spawn it (known). Add `<Ctrl><Alt>e` to launch the picker.

Do not run `ibus restart`. The probe’s restart killed Super+. until logout (known). If `ibus list-engine` cannot see the new engine, stop and ask for one logout. I believe a login rescans components; I do not know a safer in-session reload.

Uninstall restores both gsettings backups, resets that binding, deletes the component file, and runs `write-cache` only. No `ibus restart`. Ask him to log out if the source is still current. Leave the state directory unless he passes `--purge`.

While this source is selected, Super+. is untouched on purpose (decision 7). I believe the underlined-e picker belongs to the IBus panel; I do not know whether it still fires with this engine. Check that the day the engine is installed.

## Risks, early

1. Delivery with a query line. Shortcut, key-capture window, hide, timed commit into Text Editor, Terminal, and Firefox. Log capabilities for those and for the empty desktop. Pass: one emoji, clipboard unchanged, no commit when nothing is focused. The dev-machine self-test cannot prove Wayland delivery (known).

2. Enrichment. Run the frozen set on the dev machine before any GTK work. If “vet” and the dog sentence do not beat the base index, fix keywords and stop.

3. Living as the input source. After the switch, type, use Ctrl+C/V and Shift, and press Super+.. Plain US typing was fine (known); shortcuts and Super+. were not measured. Then uninstall with no `ibus restart` and confirm the backup actually restores his sources.