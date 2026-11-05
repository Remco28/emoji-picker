#!/usr/bin/env bash
# Remove emoji-picker's changes. Removes only its own entries, so input
# sources or shortcuts you changed after installing are kept.
#
#   ./uninstall.sh             uninstall (asks for your password once)
#   ./uninstall.sh --dry-run   show every step without changing anything
#
# Your usage history and settings in ~/.local/state/emoji-picker are kept
# (delete that folder yourself if you want them gone); so is the backup of
# your original settings, for manual recovery.
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

COMPONENT=/usr/share/ibus/component/emoji-picker.xml
SRC_SCHEMA=org.gnome.desktop.input-sources
KB_SCHEMA=org.gnome.settings-daemon.plugins.media-keys
KB_PATH=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/emoji-picker/

step() { printf '\n== %s\n' "$1"; }
run() { if [ "$DRY" = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }

step "1. Remove the engine from your input sources (others are kept)"
NEW_SOURCES=$(python3 -I "$HERE/tools/gsettings_lists.py" remove-source "$(gsettings get $SRC_SCHEMA sources)")
run gsettings set $SRC_SCHEMA sources "$NEW_SOURCES"
echo "   input sources: $NEW_SOURCES"

step "2. Remove the Ctrl+Alt+E shortcut (others are kept)"
NEW_LIST=$(python3 -I "$HERE/tools/gsettings_lists.py" remove-path "$(gsettings get $KB_SCHEMA custom-keybindings)" "$KB_PATH")
run gsettings set $KB_SCHEMA custom-keybindings "$NEW_LIST"
run gsettings reset-recursively "$KB_SCHEMA.custom-keybinding:$KB_PATH"

step "3. Remove the input engine file"
if [ "$SYSTEM" = 1 ]; then
  if [ -f "$COMPONENT" ]; then
    run sudo rm -f "$COMPONENT"
    run ibus write-cache
  else
    echo "   not installed"
  fi
else
  echo "   (skipped: --no-system)"
fi

step "4. Done"
echo "   If \"Keyboard with emoji picker\" is still shown as your input source, log out and back in once."
