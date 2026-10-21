#!/usr/bin/env bash
# Dummy-swap workaround for tauri-apps/tauri#11898 / linuxdeploy gtk plugin ldd failures
# on Bun/PyInstaller static sidecars during AppImage bundling.
set -euo pipefail

MODE="${1:?Usage: $0 pre-bundle|post-bundle}"

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
BINARIES_DIR="$REPO_ROOT/myrm-agent-desktop/src-tauri/binaries"
BUNDLE_DIR="$REPO_ROOT/myrm-agent-desktop/src-tauri/target/release/bundle/appimage"
DESKTOP_DIR="$REPO_ROOT/myrm-agent-desktop"
SAVE_DIR="${RUNNER_TEMP:-/tmp}/myrm-sidecar-reals"

AGENT_RUNNER_BIN="agent-runner-x86_64-unknown-linux-gnu"
BACKEND_BIN="myrmagent-backend-x86_64-unknown-linux-gnu"
APPDIR_AGENT="agent-runner"
APPDIR_BACKEND="myrmagent-backend"

write_dummy_elf() {
  local out="$1"
  local src
  src="$(mktemp --suffix=.c)"
  cat >"$src" <<'C'
int main(void) { return 0; }
C
  gcc -o "$out" "$src" -static-libgcc
  rm -f "$src"
  chmod +x "$out"
}

save_real_sidecar() {
  local name="$1"
  local src="$BINARIES_DIR/$name"
  if [[ ! -f "$src" ]]; then
    echo "[linux-appimage-sidecar] ERROR: missing sidecar: $src" >&2
    exit 1
  fi
  mkdir -p "$SAVE_DIR"
  cp "$src" "$SAVE_DIR/$name"
  echo "[linux-appimage-sidecar] saved real ${name} ($(stat -c%s "$SAVE_DIR/$name") bytes)"
}

restore_binaries_dir() {
  for name in "$AGENT_RUNNER_BIN" "$BACKEND_BIN"; do
    if [[ -f "$SAVE_DIR/$name" ]]; then
      cp "$SAVE_DIR/$name" "$BINARIES_DIR/$name"
      chmod +x "$BINARIES_DIR/$name"
    fi
  done
}

extract_appimagetool() {
  local plugin
  plugin="$(find "${HOME}/.cache/tauri" -maxdepth 1 -name 'linuxdeploy-plugin-appimage*.AppImage' -print -quit 2>/dev/null || true)"
  if [[ -z "$plugin" ]]; then
    echo "[linux-appimage-sidecar] ERROR: linuxdeploy-plugin-appimage not found under ~/.cache/tauri" >&2
    exit 1
  fi
  local tools_dir
  tools_dir="$(mktemp -d)"
  (
    cd "$tools_dir"
    chmod +x "$plugin"
    APPIMAGE_EXTRACT_AND_RUN=1 "$plugin" --appimage-extract >/dev/null 2>&1
  )
  local tool="$tools_dir/squashfs-root/usr/bin/appimagetool"
  if [[ ! -x "$tool" ]]; then
    echo "[linux-appimage-sidecar] ERROR: appimagetool not found in plugin extract" >&2
    rm -rf "$tools_dir"
    exit 1
  fi
  APP_IMAGETOOL_PATH="$tool"
  APP_IMAGETOOL_WORKDIR="$tools_dir"
}

pre_bundle() {
  for name in "$AGENT_RUNNER_BIN" "$BACKEND_BIN"; do
    save_real_sidecar "$name"
    write_dummy_elf "$BINARIES_DIR/$name"
    echo "[linux-appimage-sidecar] installed dummy ${name} ($(stat -c%s "$BINARIES_DIR/$name") bytes)"
  done
}

post_bundle() {
  local appimage
  appimage="$(find "$BUNDLE_DIR" -maxdepth 1 -name '*.AppImage' -print -quit 2>/dev/null || true)"
  if [[ -z "$appimage" ]]; then
    echo "[linux-appimage-sidecar] ERROR: no .AppImage under ${BUNDLE_DIR}" >&2
    exit 1
  fi

  local extract_dir
  extract_dir="$(mktemp -d)"
  cd "$extract_dir"
  chmod +x "$appimage"
  APPIMAGE_EXTRACT_AND_RUN=1 "$appimage" --appimage-extract >/dev/null 2>&1

  local squashfs="$extract_dir/squashfs-root"
  if [[ ! -d "$squashfs" ]]; then
    echo "[linux-appimage-sidecar] ERROR: AppImage extract failed" >&2
    exit 1
  fi

  for pair in "$APPDIR_AGENT:$AGENT_RUNNER_BIN" "$APPDIR_BACKEND:$BACKEND_BIN"; do
    local app_name="${pair%%:*}"
    local saved_name="${pair##*:}"
    local dest="$squashfs/usr/bin/$app_name"
    if [[ ! -f "$dest" ]]; then
      echo "[linux-appimage-sidecar] ERROR: ${app_name} not found in AppDir" >&2
      exit 1
    fi
    cp "$SAVE_DIR/$saved_name" "$dest"
    chmod +x "$dest"
    echo "[linux-appimage-sidecar] swapped dummy → real ${app_name} in AppDir"
  done

  extract_appimagetool
  echo "[linux-appimage-sidecar] repackaging $(basename "$appimage")..."
  ARCH=x86_64 "$APP_IMAGETOOL_PATH" "$squashfs" "$appimage"

  local tar_gz="${appimage%.AppImage}.AppImage.tar.gz"
  rm -f "$tar_gz" "${appimage}.sig" "${tar_gz}.sig"
  tar -czf "$tar_gz" -C "$(dirname "$appimage")" "$(basename "$appimage")"
  echo "[linux-appimage-sidecar] regenerated $(basename "$tar_gz")"

  restore_binaries_dir
  rm -rf "$extract_dir" "$APP_IMAGETOOL_WORKDIR"
  echo "[linux-appimage-sidecar] post-bundle OK"
}

case "$MODE" in
  pre-bundle) pre_bundle ;;
  post-bundle) post_bundle ;;
  *)
    echo "[linux-appimage-sidecar] ERROR: unknown mode: $MODE" >&2
    exit 1
    ;;
esac
