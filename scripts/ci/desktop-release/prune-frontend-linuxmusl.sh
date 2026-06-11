#!/usr/bin/env bash
# Remove linuxmusl native packages from Next.js standalone before AppImage bundling.
# linuxdeploy scans all ELF under AppDir; sharp-linuxmusl-x64 needs libc.musl-x86_64.so.1
# which is unreliable on Ubuntu GHA. glibc sharp-linux-x64 remains for runtime.
set -euo pipefail

ROOT="${1:-myrm-agent-frontend/.next/standalone}"

if [[ ! -d "$ROOT" ]]; then
  echo "[prune-frontend-linuxmusl] Standalone root not found: ${ROOT}" >&2
  exit 1
fi

removed=0
while IFS= read -r dir; do
  [[ -n "$dir" ]] || continue
  rm -rf "$dir"
  removed=$((removed + 1))
  echo "[prune-frontend-linuxmusl] removed: ${dir}"
done < <(
  find "$ROOT" -type d \( \
    -path '*/node_modules/@img/sharp-linuxmusl-*' \
    -o -path '*/node_modules/@img/sharp-libvips-linuxmusl-*' \
    -o -path '*/node_modules/@next/swc-linux-*-musl' \
  \) 2>/dev/null | sort -u
)

if [[ "$removed" -eq 0 ]]; then
  echo "[prune-frontend-linuxmusl] no linuxmusl packages found (already clean)"
fi

leftover="$(find "$ROOT" -name '*linuxmusl*.node' -print 2>/dev/null | head -5 || true)"
if [[ -n "$leftover" ]]; then
  echo "[prune-frontend-linuxmusl] ERROR: linuxmusl .node binaries still present:" >&2
  echo "$leftover" >&2
  exit 1
fi

echo "[prune-frontend-linuxmusl] OK"
