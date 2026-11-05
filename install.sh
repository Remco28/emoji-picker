#!/usr/bin/env bash
# Install emoji-picker for the current user on GNOME.
#
#   ./install.sh             install (asks for your password once, for one file)
#   ./install.sh --dry-run   show every step without changing anything
#
# What it changes, all undone by ./uninstall.sh:
#   1. /usr/share/ibus/component/emoji-picker.xml   (needs sudo: IBus only reads engines there)
#   2. your input sources: adds "Keyboard with emoji picker" first, keeps yours after it
#   3. a custom shortcut, Ctrl+Alt+E, that opens the picker
# Your original input sources and shortcut list are backed up first, to
# ~/.local/state/emoji-picker/backup/ (only on the first install).
# It never runs `ibus restart` (that broke the system emoji shortcut once);
# you log out and back in once instead.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DRY=0
SYSTEM=1
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --no-system) SYSTEM=0 ;;   # test hook: skip the sudo step
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

STATE="${XDG_STATE_HOME:-$HOME/.local/state}/emoji-picker"
BACKUP="$STATE/backup"
COMPONENT=/usr/share/ibus/component/emoji-picker.xml
SRC_SCHEMA=org.gnome.desktop.input-sources
KB_SCHEMA=org.gnome.settings-daemon.plugins.media-keys
KB_PATH=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/emoji-picker/
BINDING='<Control><Alt>e'
LAUNCHER="$HERE/bin/emoji-picker"

step() { printf '\n== %s\n' "$1"; }
run() {  # run a command, or only print it in dry-run mode
  if [ "$DRY" = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi
}

for cmd in python3 gsettings ibus; do
  command -v "$cmd" >/dev/null || { echo "missing: $cmd" >&2; exit 1; }
done
python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); gi.require_version("IBus","1.0")' \
  || { echo "missing Python GTK 4 / libadwaita / IBus bindings" >&2; exit 1; }

step "1. Back up your current settings"
if [ -f "$BACKUP/input-sources.txt" ]; then
  echo "   backup already exists (from the first install); keeping it"
else
  run mkdir -p "$BACKUP"
  if [ "$DRY" = 1 ]; then
    echo "   would save: $(gsettings get $SRC_SCHEMA sources)"
  else
    gsettings get $SRC_SCHEMA sources > "$BACKUP/input-sources.txt"
    gsettings get $KB_SCHEMA custom-keybindings > "$BACKUP/custom-keybindings.txt"
    echo "   saved to $BACKUP"
  fi
fi

step "2. Install the input engine (IBus reads engines only from /usr/share/ibus/component)"
# keyboard layout: copied from your first plain keyboard source, e.g. ('xkb', 'us') or ('xkb', 'us+intl')
read -r LAYOUT VARIANT < <(python3 -I "$HERE/tools/gsettings_lists.py" layout "$(gsettings get $SRC_SCHEMA sources)")
echo "   keyboard layout: $LAYOUT${VARIANT:+ (variant $VARIANT)}"
TMPXML=$(mktemp)
trap 'rm -f "$TMPXML"' EXIT
python3 -I "$HERE/tools/gsettings_lists.py" component "$HERE/engine/emoji-picker.xml.in" \
  "$HERE/engine/engine.py" "$LAYOUT" "$VARIANT" > "$TMPXML"
chmod +x "$HERE/engine/engine.py" "$LAUNCHER"
if [ "$SYSTEM" = 1 ]; then
  run sudo install -m 644 "$TMPXML" "$COMPONENT"
  run ibus write-cache
else
  echo "   (skipped: --no-system)"
fi

step "3. Add the engine as your first input source"
NEW_SOURCES=$(python3 -I "$HERE/tools/gsettings_lists.py" add-source "$(gsettings get $SRC_SCHEMA sources)")
run gsettings set $SRC_SCHEMA sources "$NEW_SOURCES"
echo "   input sources: $NEW_SOURCES"

step "4. Add the shortcut Ctrl+Alt+E"
TAKEN=$(gsettings list-recursively 2>/dev/null | grep -iE "'<(Control|Primary)><Alt>e'" | grep -v "custom-keybindings/emoji-picker" || true)
if [ -n "$TAKEN" ]; then
  echo "   WARNING: Ctrl+Alt+E is already used by:"; echo "$TAKEN" | sed 's/^/     /'
fi
run gsettings set "$KB_SCHEMA.custom-keybinding:$KB_PATH" name "Emoji Picker"
run gsettings set "$KB_SCHEMA.custom-keybinding:$KB_PATH" command "$LAUNCHER"
run gsettings set "$KB_SCHEMA.custom-keybinding:$KB_PATH" binding "$BINDING"
NEW_LIST=$(python3 -I "$HERE/tools/gsettings_lists.py" add-path "$(gsettings get $KB_SCHEMA custom-keybindings)" "$KB_PATH")
run gsettings set $KB_SCHEMA custom-keybindings "$NEW_LIST"

step "5. Done"
if [ "$SYSTEM" = 1 ] && [ "$DRY" = 0 ] && ibus list-engine 2>/dev/null | grep -q "emoji-picker"; then
  echo "   IBus already sees the engine. Pick \"Keyboard with emoji picker\" with Super+Space, then press Ctrl+Alt+E."
else
  echo "   Log out and back in once, so IBus loads the new engine. Then press Ctrl+Alt+E."
fi
echo "   To undo everything: $HERE/uninstall.sh"
