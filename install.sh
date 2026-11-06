#!/usr/bin/env bash
# Install or upgrade emoji-picker for the current user on GNOME.
#
#   ./install.sh                       install or upgrade (asks for your password once)
#   ./install.sh --dry-run             show every step without changing anything
#   ./install.sh --shortcut '<Control><Alt>e'   use another key than Super+.
#   emoji-picker --setup               run this again from the installed copy
#                                      (after adding a keyboard layout)
#
# What it changes (./uninstall.sh, or emoji-picker-uninstall, undoes it all):
#   1. installs the app under /usr/local (needs sudo), and the input engine
#      file /usr/share/ibus/component/emoji-picker.xml (IBus reads only there)
#   2. Super+. opens this picker; IBus's own emoji picker lets go of Super+.
#   3. at your next login, each keyboard layout you use is swapped for the
#      same layout "with emoji", so the picker can type emoji into apps
# Your settings are backed up first, to ~/.local/state/emoji-picker/backup/.
# It never runs `ibus restart`; you log out and back in once instead.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DRY=0
ROOT=""
SHORTCUT='<Super>period'
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --shortcut) SHORTCUT=${2:?--shortcut needs a key, e.g. "<Control><Alt>e"}; shift ;;
    --root) ROOT=${2:?}; shift ;;   # test hook: install under ROOT, without sudo
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

PY=/usr/bin/python3
SYSTEM="$HERE/emoji_picker/system.py"
LIB="$ROOT/usr/local/lib/emoji-picker"
BIN="$ROOT/usr/local/bin"
APPS="$ROOT/usr/local/share/applications"
ICONS="$ROOT/usr/local/share/icons/hicolor/scalable/apps"
COMPONENT="$ROOT/usr/share/ibus/component/emoji-picker.xml"
APP_ID=io.github.remco28.EmojiPicker
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/emoji-picker"
BACKUP="$STATE/backup"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_ID.finish-setup.desktop"
SRC_SCHEMA=org.gnome.desktop.input-sources
KB_SCHEMA=org.gnome.settings-daemon.plugins.media-keys
KB_PATH=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/emoji-picker/
HOTKEY_SCHEMA=org.freedesktop.ibus.panel.emoji
SUPER_DOT='<Super>period'
if [ -n "$ROOT" ]; then SUDO=(); else SUDO=(sudo); fi

step() { printf '\n== %s\n' "$1"; }
say() { printf '   %s\n' "$*"; }
run() {  # run a command, or only print it in dry-run mode
  if [ "$DRY" = 1 ]; then printf '   would run: %s\n' "$*"; else "$@"; fi
}
sys() { "$PY" -I "$SYSTEM" "$@"; }

# ---- checks, before anything changes -----------------------------------
for cmd in gsettings ibus; do
  command -v "$cmd" >/dev/null || { echo "missing: $cmd (is this a GNOME desktop?)" >&2; exit 1; }
done
[ -x "$PY" ] || { echo "missing: $PY" >&2; exit 1; }
"$PY" -I -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); gi.require_version("IBus","1.0"); from gi.repository import Gtk, Adw, IBus' 2>/dev/null \
  || { echo "missing Python GTK 4 / libadwaita / IBus bindings for $PY" >&2;
       echo "on Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-ibus-1.0" >&2; exit 1; }
VERSION=$("$PY" -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import emoji_picker; print(emoji_picker.__version__)' "$HERE")
COMMIT=$(git -C "$HERE" rev-parse --short HEAD 2>/dev/null || cut -s -d' ' -f2 "$HERE/VERSION" 2>/dev/null || true)
COMMIT=${COMMIT:-nogit}

# Never take over a shortcut someone else put at our settings path.
EXISTING=$(gsettings get "$KB_SCHEMA.custom-keybinding:$KB_PATH" name)
if [ "$EXISTING" != "''" ] && [ "$EXISTING" != "'Emoji Picker'" ]; then
  echo "A shortcut named $EXISTING already uses $KB_PATH; nothing was changed." >&2
  echo "Rename or remove that shortcut first." >&2
  exit 1
fi

SOURCES=$(gsettings get $SRC_SCHEMA sources)
# a prototype (0.1) install had one engine, typing with one layout: carry that layout over
PROTO_ID=""
if printf '%s' "$SOURCES" | grep -qF "('ibus', 'emoji-picker')"; then
  PROTO_ID=$(sys prototype-layout "$COMPONENT"); PROTO_ID=${PROTO_ID:-us}
fi
mapfile -t LAYOUTS < <(sys engines "$SOURCES" --proto "$PROTO_ID")
echo "emoji-picker $VERSION ($COMMIT)"
if [ ${#LAYOUTS[@]} -eq 0 ]; then
  say "NOTE: you have no plain keyboard layout among your input sources, so there is"
  say "no keyboard to add emoji to. The picker will copy emoji for you to paste."
else
  say "keyboard layouts to add emoji to: ${LAYOUTS[*]}"
fi

if [ "$DRY" = 0 ] && [ -z "$ROOT" ]; then
  # ask for the password before changing anything
  sudo -v || { echo "Nothing was changed." >&2; exit 1; }
fi

# ---- 1. backup ---------------------------------------------------------
step "1. Back up your current settings (first install only)"
if [ "$DRY" = 1 ]; then
  say "would save your input sources, shortcut list and IBus emoji hotkey to $BACKUP"
else
  mkdir -p "$BACKUP"
  save() { [ -f "$BACKUP/$1" ] || gsettings get "$2" "$3" > "$BACKUP/$1"; }
  save input-sources.txt $SRC_SCHEMA sources
  save mru-sources.txt $SRC_SCHEMA mru-sources
  save custom-keybindings.txt $KB_SCHEMA custom-keybindings
  save ibus-emoji-hotkey.txt $HOTKEY_SCHEMA hotkey
  say "kept in $BACKUP"
fi

# ---- 2. files ------------------------------------------------------------
step "2. Install the app to $LIB (asks for your password)"
NAME="$VERSION-$COMMIT-$(date +%Y%m%d%H%M%S)"
while [ -e "$LIB/versions/$NAME" ]; do NAME="$NAME.1"; done
DEST="$LIB/versions/$NAME"
TMP=$(mktemp -d)
trap 'rm -rf -- "${TMP:?}"' EXIT
if [ "$DRY" = 1 ]; then
  say "would copy the app to $DEST, compile it, and point $LIB/current at it"
  say "would write $BIN/emoji-picker, $BIN/emoji-picker-uninstall, the app entry and icon"
else
  # stage everything in a new directory; the switch to it is one rename
  "${SUDO[@]}" mkdir -p "$LIB/versions" "$LIB/users"
  "${SUDO[@]}" rm -rf -- "${DEST:?}.tmp"
  "${SUDO[@]}" mkdir -p "$DEST.tmp"
  tar -C "$HERE" --exclude=__pycache__ -cf - emoji_picker engine/engine.py install.sh uninstall.sh \
      LICENSE data \
    | "${SUDO[@]}" tar -C "$DEST.tmp" --no-same-owner -xf -
  printf '%s %s\n' "$VERSION" "$COMMIT" | "${SUDO[@]}" tee "$DEST.tmp/VERSION" >/dev/null
  "${SUDO[@]}" "$PY" -I -m compileall -q -s "$DEST.tmp" -p "$DEST" "$DEST.tmp" >/dev/null
  "${SUDO[@]}" chmod -R u=rwX,go=rX "$DEST.tmp"
  "${SUDO[@]}" chmod 755 "$DEST.tmp/engine/engine.py" "$DEST.tmp/install.sh" "$DEST.tmp/uninstall.sh"
  "${SUDO[@]}" mv -T "$DEST.tmp" "$DEST"
  PREVIOUS=$(readlink "$LIB/current" 2>/dev/null || true)
  "${SUDO[@]}" ln -sfn "versions/$NAME" "$LIB/current.new"
  "${SUDO[@]}" mv -T "$LIB/current.new" "$LIB/current"
  # keep the new version and the one before it (a running engine may use it)
  for d in "$LIB"/versions/*; do
    [ -d "$d" ] || continue
    case "versions/$(basename "$d")" in "versions/$NAME"|"$PREVIOUS") ;; *) "${SUDO[@]}" rm -rf -- "${d:?}" ;; esac
  done

  cat > "$TMP/emoji-picker" <<EOF
#!/usr/bin/python3 -I
# Emoji Picker launcher, written by install.sh. Runs the installed version.
import sys
sys.path.insert(0, "$LIB/current")
from emoji_picker.__main__ import main
sys.exit(main())
EOF
  cat > "$TMP/emoji-picker-uninstall" <<EOF
#!/bin/sh
# Removes Emoji Picker. Written by install.sh.
exec "$LIB/current/uninstall.sh" "\$@"
EOF
  sed "s#@BIN@#$BIN/emoji-picker#" "$HERE/data/$APP_ID.desktop.in" > "$TMP/$APP_ID.desktop"
  "${SUDO[@]}" install -D -m 755 "$TMP/emoji-picker" "$BIN/emoji-picker"
  "${SUDO[@]}" install -D -m 755 "$TMP/emoji-picker-uninstall" "$BIN/emoji-picker-uninstall"
  "${SUDO[@]}" install -D -m 644 "$TMP/$APP_ID.desktop" "$APPS/$APP_ID.desktop"
  "${SUDO[@]}" install -D -m 644 "$HERE/data/$APP_ID.svg" "$ICONS/$APP_ID.svg"
  say "installed $VERSION to $DEST"
fi

step "3. Install the input engine (IBus reads engines only from /usr/share/ibus/component)"
if [ "$DRY" = 1 ]; then
  say "would record your layouts in $LIB/users/$(id -u)"
  say "would write $COMPONENT with an engine for each layout any user installed it for"
else
  printf '%s\n' "${LAYOUTS[@]}" > "$TMP/layouts"
  "${SUDO[@]}" install -D -m 644 "$TMP/layouts" "$LIB/users/$(id -u)"
  sys component "$VERSION" "$PY -I $LIB/current/engine/engine.py" "$LIB/users" > "$TMP/component.xml"
  "${SUDO[@]}" install -D -m 644 "$TMP/component.xml" "$COMPONENT"
  [ -n "$ROOT" ] || ibus write-cache 2>/dev/null || true
  say "engines: $(grep -o '<name>emoji-picker:[^<]*' "$TMP/component.xml" | sed 's/<name>//' | tr '\n' ' ')"
fi

# ---- 4. shortcut -------------------------------------------------------------
step "4. Shortcut: $SHORTCUT opens the picker"
HOTKEY=$(gsettings get $HOTKEY_SCHEMA hotkey)
REMOVED=$("$PY" -I -c 'import json,sys
try: print("1" if json.load(open(sys.argv[1])).get("removed_ibus_hotkey") else "0")
except Exception: print("0")' "$STATE/installed.json")
if [ "$SHORTCUT" = "$SUPER_DOT" ]; then
  if sys has "$HOTKEY" "$SUPER_DOT"; then
    NEW_HOTKEY=$(sys hotkey-remove "$HOTKEY" "$SUPER_DOT")
    run gsettings set $HOTKEY_SCHEMA hotkey "$NEW_HOTKEY"
    say "IBus's emoji picker no longer uses Super+. (it keeps $NEW_HOTKEY)"
    REMOVED=1
  fi
elif [ "$REMOVED" = 1 ]; then
  run gsettings set $HOTKEY_SCHEMA hotkey "$(sys hotkey-restore "$HOTKEY" "$SUPER_DOT")"
  say "gave Super+. back to IBus's emoji picker"
  REMOVED=0
fi
# list-recursively skips custom shortcuts (a relocatable schema), so check those one by one
TAKEN=$(gsettings list-recursively 2>/dev/null | grep -F "'$SHORTCUT'" \
  | grep -vE "^$HOTKEY_SCHEMA hotkey " || true)
while read -r p; do
  [ -n "$p" ] && [ "$p" != "$KB_PATH" ] || continue
  if [ "$(gsettings get "$KB_SCHEMA.custom-keybinding:$p" binding)" = "'$SHORTCUT'" ]; then
    TAKEN="$TAKEN${TAKEN:+$'\n'}custom shortcut $(gsettings get "$KB_SCHEMA.custom-keybinding:$p" name) ($p)"
  fi
done < <("$PY" -I -c 'import ast,sys
t = sys.argv[1].split(" ", 1)[1] if sys.argv[1].startswith("@") else sys.argv[1]
print("\n".join(ast.literal_eval(t)))' "$(gsettings get $KB_SCHEMA custom-keybindings)")
if [ -n "$TAKEN" ]; then
  say "WARNING: $SHORTCUT is also used by:"; echo "$TAKEN" | sed 's/^/     /'
fi
run gsettings set "$KB_SCHEMA.custom-keybinding:$KB_PATH" name "Emoji Picker"
run gsettings set "$KB_SCHEMA.custom-keybinding:$KB_PATH" command "$BIN/emoji-picker"
run gsettings set "$KB_SCHEMA.custom-keybinding:$KB_PATH" binding "$SHORTCUT"
run gsettings set $KB_SCHEMA custom-keybindings \
  "$(sys add-path "$(gsettings get $KB_SCHEMA custom-keybindings)" "$KB_PATH")"
if [ "$DRY" = 0 ]; then
  "$PY" -I -c 'import json,sys
v, c, lib, key, cmd, removed, proto, path = sys.argv[1:]
json.dump({"version": v, "commit": c, "lib": lib, "shortcut": key, "command": cmd,
           "removed_ibus_hotkey": removed == "1", "prototype_layout": proto},
          open(path, "w"), indent=1)' \
    "$VERSION" "$COMMIT" "$LIB" "$SHORTCUT" "$BIN/emoji-picker" "$REMOVED" "$PROTO_ID" "$STATE/installed.json"
fi

# ---- 5. input sources ------------------------------------------------------
step "5. Swap your keyboard layouts for the same layouts with emoji"
ENGINES=$(ibus list-engine 2>/dev/null || true)
MISSING=$(sys missing "$SOURCES" "$ENGINES" --proto "$PROTO_ID")
if [ ${#LAYOUTS[@]} -eq 0 ]; then
  say "nothing to swap"
  PENDING=0
else
  for key in sources mru-sources; do
    BEFORE=$(gsettings get $SRC_SCHEMA $key)
    AFTER=$(sys convert "$BEFORE" --known "$ENGINES" --proto "$PROTO_ID")   # only engines IBus knows
    [ "$AFTER" = "$BEFORE" ] || run gsettings set $SRC_SCHEMA $key "$AFTER"
  done
  if [ -n "$MISSING" ]; then
    PENDING=1
    if [ "$DRY" = 1 ]; then
      say "would add a one-time login step: $AUTOSTART"
    else
      mkdir -p "$(dirname "$AUTOSTART")"
      cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Emoji Picker setup
Comment=Finishes installing Emoji Picker once, then removes itself
Exec=$BIN/emoji-picker --finish-setup
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
    fi
    say "IBus loads the new engines at your next login; your layouts are swapped then"
  else
    PENDING=0
    if [ -f "$AUTOSTART" ]; then run rm -f -- "$AUTOSTART"; fi   # an earlier install's, now done
    say "input sources: $(gsettings get $SRC_SCHEMA sources)"
  fi
fi

step "Done"
NICE=$([ "$SHORTCUT" = "$SUPER_DOT" ] && echo "Super+." || echo "$SHORTCUT")
if [ "$PENDING" = 1 ]; then
  if printf '%s' "$SOURCES" | grep -qF "('ibus', 'emoji-picker')"; then
    say "$NICE now opens the picker, and Enter keeps typing emoji as before."
  else
    say "$NICE now opens the picker. Until you log out and back in, Enter copies the"
    say "emoji (paste with Ctrl+V) instead of typing it."
  fi
  say "Log out and back in once to finish."
else
  say "$NICE opens the picker."
fi
say "Check the setup any time: emoji-picker --doctor"
say "Added a keyboard layout later? emoji-picker --setup gives it emoji too."
say "To remove it: emoji-picker-uninstall"
