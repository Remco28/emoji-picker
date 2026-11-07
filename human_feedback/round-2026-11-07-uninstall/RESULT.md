# Round 5 result: uninstall leaves no trace

Tested by Frank on 2026-11-07, Ubuntu 26.04 (GNOME 50, Wayland), branch
clean-uninstall at c898a85. Results came back in chat, no ZIP.

- Upgraded to the branch, uninstalled, logged out and in. `trace.py leftovers`
  listed only the empty folders the v1.0 installer had made (before it kept a
  list); Frank removed them with `sudo rmdir`, and the check came back clean.
- Snapshot A, install, log out and in, use, uninstall, snapshot B:

  ```
  saved /tmp/ep-trace-B: 283 settings, 602 files, 978 engines
  == Settings: no change
  == Files and folders: no change
    (10 changes inside ~/.local/state/emoji-picker: your history, kept on purpose)
  == IBus input engines: no change
    (emoji-picker:us: IBus forgets it at your next login)

  RESULT: no trace left
  ```

- Found along the way: step 5 of the uninstaller printed nothing although it
  removed the app, and step 6 printed nothing when there was no cache. Both
  now say what they did.
- The guide's commands did not say to run them inside the emoji-picker
  folder; the first snapshot B attempt ran from the home folder and failed.
  For a future round: say where to run commands, every time.

Verdict: passed.
