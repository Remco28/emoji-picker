#!/usr/bin/env bash
# Installs / removes the probe's IBus engine and three test shortcuts.
# Everything it changes is backed up first and restored by `uninstall`.
#
#   ./setup.sh install     add engine + shortcuts
#   ./setup.sh uninstall   restore your original settings
#   ./setup.sh status      show what is installed
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/emojitest"
# IBus only loads engines from /usr/share/ibus/component (tested: per-user
# data dirs are ignored), so this one step needs sudo.
COMP_FILE=/usr/share/ibus/component/emojitest.xml
SRC_SCHEMA=org.gnome.desktop.input-sources
KB_SCHEMA=org.gnome.settings-daemon.plugins.media-keys
KB_BASE=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
# name : binding : mode
KEYS=("emojitest-ime:<Ctrl><Alt>1:ime" "emojitest-portal:<Ctrl><Alt>2:portal" "emojitest-copy:<Ctrl><Alt>3:copy")

mkdir -p "$STATE"

pylist() { # pylist <gsettings-value> -> python list repr
  python3 -I - "$1" <<'PY'
import ast, sys
v = sys.argv[1].strip()
if v.startswith("@"):
    v = v.split(" ", 1)[1]
print(repr(ast.literal_eval(v)))
PY
}

install() {
  chmod +x "$HERE/ibus/engine.py" "$HERE/picker_sim.py"

  # 1. Back up originals (only the first time, so reinstalling is safe)
  [ -f "$STATE/sources.orig" ] || gsettings get $SRC_SCHEMA sources > "$STATE/sources.orig"
  [ -f "$STATE/keybindings.orig" ] || gsettings get $KB_SCHEMA custom-keybindings > "$STATE/keybindings.orig"
  echo "Backed up originals to $STATE"

  # 2. IBus component
  sed "s|@EXEC@|$HERE/ibus/engine.py|" "$HERE/ibus/emojitest.xml.in" > "$STATE/emojitest.xml"
  echo "Installing $COMP_FILE (sudo will ask for your password)"
  sudo install -m 644 "$STATE/emojitest.xml" "$COMP_FILE"
  ibus write-cache || true
  echo "Restarting IBus (typing may flicker for a second)..."
  ibus restart || true
  sleep 3
  if ibus list-engine 2>/dev/null | grep -q emojitest; then
    echo "OK: IBus sees the emojitest engine"
  else
    cat <<MSG
WARNING: IBus restarted but does not list the emojitest engine.
Try logging out and back in, then run: ./setup.sh status
MSG
  fi

  # 3. Add the engine as an input source (keeps your existing ones)
  python3 -I - "$STATE/sources.orig" <<'PY' > "$STATE/sources.new"
import ast, sys
raw = open(sys.argv[1]).read().strip()
if raw.startswith("@"):
    raw = raw.split(" ", 1)[1]
src = ast.literal_eval(raw)
if ("ibus", "emojitest") not in src:
    src.append(("ibus", "emojitest"))
print(repr(src))
PY
  gsettings set $SRC_SCHEMA sources "$(cat "$STATE/sources.new")"
  echo "Input sources now: $(gsettings get $SRC_SCHEMA sources)"
  echo "  -> switch to 'Emoji Probe (passive)' with Super+Space before the IME test"

  # 4. Shortcuts
  local list; list=$(pylist "$(cat "$STATE/keybindings.orig")")
  local entry name bind mode path
  for entry in "${KEYS[@]}"; do
    IFS=: read -r name bind mode <<<"$entry"
    path="$KB_BASE/$name/"
    gsettings set "$KB_SCHEMA.custom-keybinding:$path" name "$name"
    gsettings set "$KB_SCHEMA.custom-keybinding:$path" command "python3 $HERE/picker_sim.py --mode $mode"
    gsettings set "$KB_SCHEMA.custom-keybinding:$path" binding "$bind"
    list=$(python3 -I - "$list" "$path" <<'PY'
import ast, sys
l = ast.literal_eval(sys.argv[1])
if sys.argv[2] not in l:
    l.append(sys.argv[2])
print(repr(l))
PY
)
  done
  gsettings set $KB_SCHEMA custom-keybindings "$list"
  echo "Shortcuts: Ctrl+Alt+1 = IME, Ctrl+Alt+2 = portal paste, Ctrl+Alt+3 = copy only"
}

uninstall() {
  local entry name bind mode
  if [ -f "$STATE/sources.orig" ]; then
    gsettings set $SRC_SCHEMA sources "$(cat "$STATE/sources.orig")"
    echo "Restored input sources"
  fi
  if [ -f "$STATE/keybindings.orig" ]; then
    gsettings set $KB_SCHEMA custom-keybindings "$(cat "$STATE/keybindings.orig")"
    echo "Restored shortcuts list"
  fi
  for entry in "${KEYS[@]}"; do
    IFS=: read -r name bind mode <<<"$entry"
    gsettings reset-recursively "$KB_SCHEMA.custom-keybinding:$KB_BASE/$name/" 2>/dev/null || true
  done
  sudo rm -f "$COMP_FILE"
  ibus write-cache || true
  ibus restart || true
  echo "Removed engine. Logs and backups remain in $STATE (safe to delete)."
}

status() {
  echo "component file: $([ -f "$COMP_FILE" ] && echo present || echo absent)"
  echo "ibus sees engine: $(ibus list-engine 2>/dev/null | grep -q emojitest && echo yes || echo no)"
  echo "input sources: $(gsettings get $SRC_SCHEMA sources)"
  echo "active engine: $(ibus engine 2>/dev/null || echo '?')"
  echo "custom shortcuts: $(gsettings get $KB_SCHEMA custom-keybindings)"
  echo "logs: $STATE/engine.log  $STATE/picker.log"
}

case "${1:-}" in
  install) install ;; uninstall) uninstall ;; status) status ;;
  *) echo "usage: $0 install|uninstall|status"; exit 2 ;;
esac
