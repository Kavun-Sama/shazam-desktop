#!/usr/bin/env bash
# Pack an .app into a compressed .dmg with an /Applications shortcut.
#
# Usage: packaging/make_dmg.sh APP_PATH OUTPUT_DMG VOLUME_NAME
set -euo pipefail

app="${1:?usage: make_dmg.sh APP_PATH OUTPUT_DMG VOLUME_NAME}"
output="${2:?missing OUTPUT_DMG}"
volume="${3:?missing VOLUME_NAME}"

staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
cp -R "$app" "$staging/"
ln -s /Applications "$staging/Applications"
rm -f "$output"

# hdiutil occasionally fails with "Resource busy" right after a build; retry a few times.
for attempt in 1 2 3 4 5; do
  if hdiutil create -volname "$volume" -srcfolder "$staging" -fs HFS+ -format UDZO -ov "$output"; then
    exit 0
  fi
  echo "hdiutil failed (attempt $attempt), retrying" >&2
  sleep 5
done
exit 1
