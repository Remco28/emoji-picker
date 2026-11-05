## Findings

- **HIGH, conditional settings damage:** If the fixed custom-keybinding path already contains a shortcut, install overwrites its name, command, and binding; uninstall then removes that path and resets its settings. This can erase a user shortcut. The scripts do not check whether the path is already in use before writing it ([install.sh](/home/frank/.cache/emoji-picker-review/audit.O5lV/copy/install.sh:83), [uninstall.sh](/home/frank/.cache/emoji-picker-review/audit.O5lV/copy/uninstall.sh:37)). I can confirm the code would do this; I have no evidence Frank currently has that path configured.

- **MEDIUM, Ctrl+C copy is broken:** The key handler expects `get_selection_bounds()` to be false when there is no selection ([window.py](/home/frank/.cache/emoji-picker-review/audit.O5lV/copy/emoji_picker/window.py:381)). **I know** PyGObject returns multiple values here—a tuple containing the selection flag and bounds—so the tuple remains truthy when the flag is false. The guard therefore rejects Ctrl+C in the ordinary no-selection case. I couldn’t verify this by creating a GTK widget here: the no-display attempt segfaulted. This breaks the planned copy action, including the copy fallback when insertion preflight fails.

I found no confirmed defect that prevents Enter insertion on Frank’s setup from the code alone. I couldn’t show the window or verify focus timing on GNOME Wayland here, and I did not rerun the test suite.

## Plan compliance

- **Section 6:** The normal Ctrl+C path does not close the picker as specified; after a successful copy it stays open until another key. The broken Ctrl+C guard is a functional failure of that key binding. Other listed key handling appears consistent in the code.
- **Section 7:** The code checks preflight before hiding, waits at least 150 ms, requires the generation to rise and 30 ms of quiet, gives up at 2 seconds, and has no clipboard operation after hiding. The implementation meets those stated checks. **I believe** the unresolved fake-context concern is possible: the engine reports a focused engine instance but does not identify whether it belongs to the real app or IBus’s fake context.
- **Section 8:** The installer does not run `ibus engine emoji-picker` when IBus already lists the engine; it tells the user to switch with Super+Space instead ([install.sh](/home/frank/.cache/emoji-picker-review/audit.O5lV/copy/install.sh:94)). That differs from the plan’s automatic selection step. The fixed shortcut-path collision described above also makes install/uninstall unsafe for that specific existing setting.

## Declined findings

| # | Verdict | Reason |
|---|---|---|
| 9 | **HOLDS** | **I believe** the stated Noto per-version sequence coverage premise is a reasonable basis for this cutoff, though it is not independently verified against Frank’s installed font. The cutoff also hides newer single-code-point emoji that would otherwise render poorly. |
| 14 | **HOLDS** | Keeping a hand-written phrase table out until an evaluation shows a gap preserves the planned measurement of enrichment. |
| 17 | **HOLDS** | **I know** GTK 4 `Gtk.GridView` has no section-header factory; the stated reason for keeping FlowBox is sound. |
| 27 | **DOES NOT HOLD** | Lack of reproduction does not establish safety. The code accepts any focused engine instance with a raised generation; it cannot tell a real app context from a fake one. The plan itself leaves this as an unverified Wayland risk. |

## Changes applied in one place and missed in another

The copy command’s selection guard conflicts with the copy behavior the window advertises and with the preflight fallback that depends on copying. Also, installer and uninstaller use the same fixed shortcut path, but neither protects pre-existing settings at that path.