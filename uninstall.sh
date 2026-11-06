#!/usr/bin/env bash
# Remove emoji-picker for the current user. Puts back plain keyboard layouts
# and IBus's Super+. emoji hotkey, removes the shortcut, and removes the app
# from /usr/local once no user on this computer still has it installed.
#
#   emoji-picker-uninstall             (or ./uninstall.sh in a clone)
#   emoji-picker-uninstall --dry-run   show every step without changing anything
#
# Only its own entries are removed, so input sources or shortcuts you changed
# since installing are kept. Your history, settings and the backup of your
# original settings stay in ~/.local/state/emoji-picker.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DRY=0
ROOT=""
ARGS=("$@")
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --root) ROOT=${2:?}; shift ;;   # test hook: matches install.sh --root
    --relocated) ;;                 # internal: already running from a temporary copy
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

LIB="$ROOT/usr/local/lib/emoji-picker"

# When run from the installed copy, run from a temporary copy instead: the
# installed one is deleted below.
case "$HERE/" in
  "$LIB"/*)
    case " ${ARGS[*]-} " in *" --relocated "*) ;; *)
      COPY=$(mktemp -d)
      mkdir -p "$COPY/emoji_picker"
      cp "$HERE/uninstall.sh" "$COPY/"
      cp "$HERE/emoji_picker/system.py" "$COPY/emoji_picker/"
      exec bash "$COPY/uninstall.sh" "${ARGS[@]}" --relocated
    esac ;;
esac
case " ${ARGS[*]-} " in *" --relocated "*) trap 'rm -rf -- "${HERE:?}"' EXIT ;; esac

PY=/usr/bin/python3
SYSTEM="$HERE/emoji_picker/system.py"
BIN="$ROOT/usr/local/bin"
APPS="$ROOT/usr/local/share/applications"
ICONS="$ROOT/usr/local/share/icons/hicolor/scalable/apps"
COMPONENT="$ROOT/usr/share/ibus/component/emoji-picker.xml"
APP_ID=io.github.remco28.EmojiPicker
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/emoji-picker"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_ID.finish-setup.desktop"
SRC_SCHEMA=org.gnome.desktop.input-sources
KB_SCHEMA=org.gnome.settings-daemon.plugins.media-keys
KB_PATH=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/emoji-picker/
HOTKEY_SCHEMA=org.freedesktop.ibus.panel.emoji
SUPER_DOT='<Super>period'
if [ -n "$ROOT" ]; then SUDO=(); else SUDO=(sudo); fi

step() { printf '\n== %s\n' "$1"; }
say() { printf '   %s\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }
sys() { "$PY" -I "$SYSTEM" "$@"; }
installed() {  # a field of installed.json, or empty
  "$PY" -I -c 'import json,sys
try: v = json.load(open(sys.argv[1])).get(sys.argv[2], "")
except Exception: v = ""
print({True: "1", False: "0"}.get(v, v))' "$STATE/installed.json" "$1"
}

step "1. Put back your plain keyboard layouts (other input sources are kept)"
for key in sources mru-sources; do
  BEFORE=$(gsettings get $SRC_SCHEMA $key)
  AFTER=$(sys restore "$BEFORE")
  [ "$AFTER" = "$BEFORE" ] || run gsettings set $SRC_SCHEMA $key "$AFTER"
done
say "input sources: $(sys restore "$(gsettings get $SRC_SCHEMA sources)")"

step "2. Remove the shortcut (others are kept)"
NAME=$(gsettings get "$KB_SCHEMA.custom-keybinding:$KB_PATH" name)
COMMAND=$(gsettings get "$KB_SCHEMA.custom-keybinding:$KB_PATH" command)
OURS_CMD="'$(installed command)'"
if [ "$NAME" = "'Emoji Picker'" ] && { [ "$COMMAND" = "'$BIN/emoji-picker'" ] \
     || [ "$COMMAND" = "$OURS_CMD" ] || [[ "$COMMAND" == */bin/emoji-picker\' ]]; }; then
  run gsettings set $KB_SCHEMA custom-keybindings \
    "$(sys remove-path "$(gsettings get $KB_SCHEMA custom-keybindings)" "$KB_PATH")"
  run gsettings reset-recursively "$KB_SCHEMA.custom-keybinding:$KB_PATH"
  say "removed"
elif [ "$NAME" = "''" ]; then
  say "none set"
else
  say "the shortcut at $KB_PATH ($NAME, $COMMAND) was changed since; left alone"
fi

step "3. Give Super+. back to IBus's emoji picker"
HOTKEY=$(gsettings get $HOTKEY_SCHEMA hotkey)
if [ "$(installed removed_ibus_hotkey)" = 1 ] && ! sys has "$HOTKEY" "$SUPER_DOT"; then
  run gsettings set $HOTKEY_SCHEMA hotkey "$(sys hotkey-restore "$HOTKEY" "$SUPER_DOT")"
  say "done"
else
  say "nothing to give back"
fi

step "4. Remove the one-time login step, if it is still there"
if [ -f "$AUTOSTART" ]; then run rm -f -- "$AUTOSTART"; say "removed"; else say "not there"; fi
[ "$DRY" = 1 ] || rm -f -- "$STATE/installed.json" "$STATE/finish-setup-notified"

step "5. Remove the app (asks for your password)"
ME="$LIB/users/$(id -u)"
if [ -f "$ME" ]; then run "${SUDO[@]}" rm -f -- "$ME"; fi
OTHERS=$(ls -A "$LIB/users" 2>/dev/null | grep -vx "$(id -u)" || true)
if [ -n "$OTHERS" ]; then
  say "other users on this computer still use it; keeping the app and their engines"
  if [ "$DRY" = 0 ] && [ -e "$LIB/current" ]; then
    VERSION=$(cut -d' ' -f1 "$LIB/current/VERSION" 2>/dev/null || echo 1)
    TMP=$(mktemp)
    sys component "$VERSION" "$PY -I $LIB/current/engine/engine.py" "$LIB/users" > "$TMP"
    "${SUDO[@]}" install -m 644 "$TMP" "$COMPONENT"
    rm -f -- "$TMP"
  fi
else
  for f in "$COMPONENT" "$BIN/emoji-picker" "$BIN/emoji-picker-uninstall" \
           "$APPS/$APP_ID.desktop" "$ICONS/$APP_ID.svg"; do
    if [ -e "$f" ]; then run "${SUDO[@]}" rm -f -- "$f"; fi
  done
  if [ -d "$LIB" ]; then run "${SUDO[@]}" rm -rf -- "${LIB:?}"; fi
fi
if [ -z "$ROOT" ]; then run ibus write-cache 2>/dev/null || true; fi

step "Done"
say "Log out and back in once so IBus forgets the emoji keyboard."
say "Your emoji history, settings and the backup of your original settings are in"
say "$STATE (delete that folder if you want them gone)."
