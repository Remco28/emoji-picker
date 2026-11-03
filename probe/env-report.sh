#!/usr/bin/env bash
# Read-only environment report for the emoji-picker probe.
# Changes nothing. Writes ./emoji-probe-report.txt and prints it.
set -u
OUT="${1:-emoji-probe-report.txt}"

section() { printf '\n## %s\n' "$1"; }
have()    { command -v "$1" >/dev/null 2>&1; }
try()     { "$@" 2>&1 || echo "(failed: $*)"; }

{
echo "# emoji-picker probe: environment report"
echo "date: $(date -Is)"

section "Session"
echo "XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-}"
echo "XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP:-}"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}  DISPLAY=${DISPLAY:-}"
echo "GTK_IM_MODULE=${GTK_IM_MODULE:-} QT_IM_MODULE=${QT_IM_MODULE:-} XMODIFIERS=${XMODIFIERS:-}"
have lsb_release && lsb_release -ds
uname -r
have gnome-shell && gnome-shell --version

section "IBus"
if have ibus; then
  ibus version
  echo "running daemon: $(pgrep -x ibus-daemon >/dev/null && echo yes || echo NO)"
  echo "active engine: $(try ibus engine)"
  echo "input sources: $(try gsettings get org.gnome.desktop.input-sources sources)"
  echo "per-window source: $(try gsettings get org.gnome.desktop.input-sources per-window)"
else
  echo "ibus not installed"
fi

section "Portals (Wayland insertion needs RemoteDesktop)"
if have gdbus; then
  for p in version AvailableDeviceTypes; do
    printf 'RemoteDesktop.%s: ' "$p"
    gdbus call --session --dest org.freedesktop.portal.Desktop \
      --object-path /org/freedesktop/portal/desktop \
      --method org.freedesktop.DBus.Properties.Get \
      org.freedesktop.portal.RemoteDesktop "$p" 2>&1 | head -1
  done
  printf 'GlobalShortcuts.version: '
  gdbus call --session --dest org.freedesktop.portal.Desktop \
    --object-path /org/freedesktop/portal/desktop \
    --method org.freedesktop.DBus.Properties.Get \
    org.freedesktop.portal.GlobalShortcuts version 2>&1 | head -1
else
  echo "gdbus missing"
fi
have xdg-desktop-portal && echo "xdg-desktop-portal on PATH" 
dpkg -l 2>/dev/null | awk '/xdg-desktop-portal/ {print $2, $3}'

section "Injection helpers"
for t in wl-copy wl-paste wtype ydotool xdotool xclip; do
  printf '%s: ' "$t"; command -v "$t" || echo "no"
done
ls -l /dev/uinput 2>&1
echo "groups: $(id -nG)"

section "Python / GTK bindings"
python3 --version
python3 - <<'PY' 2>&1
import gi
for ns, ver in (("Gtk","4.0"),("Adw","1"),("IBus","1.0"),("Gio","2.0")):
    try:
        gi.require_version(ns, ver)
        print(f"{ns} {ver}: ok")
    except Exception as e:
        print(f"{ns} {ver}: MISSING ({e})")
PY

section "Apps for the test matrix (snap/flatpak change IME and portal behaviour)"
for a in firefox chromium chromium-browser google-chrome code slack discord gnome-terminal kgx ptyxis gnome-text-editor gedit libreoffice; do
  p=$(command -v "$a" 2>/dev/null) && echo "$a: $p"
done
have snap && snap list 2>/dev/null | awk 'NR>1 {print "snap: "$1" "$2}' | head -20
have flatpak && flatpak list --app 2>/dev/null | head -20
} 2>&1 | tee "$OUT"

echo
echo "Saved to: $(pwd)/$OUT"
