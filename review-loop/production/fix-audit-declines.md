# Findings the author declined, with reasons (give each a second opinion)

1. "Uninstall removes our shortcut by name only; keep it if the user changed it."
   Taken in part: uninstall now also requires the command to be ours. Declined part:
   when only the key (binding) was changed, it is still removed, because its command
   points at /usr/local/bin/emoji-picker, which uninstall deletes; keeping it would
   leave a dead shortcut.
2. "Cut the .desktop app entry." Declined: on Wayland GNOME matches the window's app id
   to a .desktop file for the window's name and icon (Alt+Tab, notifications).
3. "Write mru-sources before sources, or in one change-set, or GNOME resets the active
   layout." Declined: GNOME Shell's InputSourceManager keeps its MRU in memory after
   start (_updateMruSources uses this._mruSources when non-empty and only reads the
   setting when it is empty), so write order cannot change the result; after the login
   swap the first layout becomes active, which is rated LOW.
4. "Cut the versioned directories + `current` symlink; install straight into
   /usr/local/lib/emoji-picker via a staged dir and one mv -T." Declined: mv -T of a
   directory onto an existing non-empty directory fails, so that path needs rm then mv
   (not atomic, which the first review flagged HIGH); the symlink switch is atomic and tested.
5. "With every layout an IBus source, GNOME falls back to 'us' until IBus is ready or
   if it crashes." Not fixed: keeping the plain layout as well would show the keyboard
   indicator, which the owner decided against. Documented as a limit; no effect on a US
   layout (the owner's). Will be put to the owner.
