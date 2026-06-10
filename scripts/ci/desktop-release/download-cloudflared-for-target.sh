#!/usr/bin/env bash
# Download a single cloudflared binary for the current desktop target triple.
set -euo pipefail

TARGET_TRIPLE="${1:-}"
if [[ -z "$TARGET_TRIPLE" ]]; then
  echo "Usage: download-cloudflared-for-target.sh <target-triple>" >&2
  echo "  e.g. aarch64-apple-darwin | x86_64-apple-darwin | x86_64-pc-windows-msvc | x86_64-unknown-linux-gnu" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BIN_DIR="$ROOT/myrm-agent-desktop/src-tauri/binaries"
mkdir -p "$BIN_DIR"
cd "$BIN_DIR"

case "$TARGET_TRIPLE" in
  aarch64-apple-darwin)
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz | tar xz
    mv -f cloudflared cloudflared-aarch64-apple-darwin
    chmod +x cloudflared-aarch64-apple-darwin
    ;;
  x86_64-apple-darwin)
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz | tar xz
    mv -f cloudflared cloudflared-x86_64-apple-darwin
    chmod +x cloudflared-x86_64-apple-darwin
    ;;
  x86_64-pc-windows-msvc)
    curl -fsSL -o cloudflared-x86_64-pc-windows-msvc.exe \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
    ;;
  x86_64-unknown-linux-gnu)
    curl -fsSL -o cloudflared-x86_64-unknown-linux-gnu \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x cloudflared-x86_64-unknown-linux-gnu
    ;;
  *)
    echo "Unsupported cloudflared target: $TARGET_TRIPLE" >&2
    exit 1
    ;;
esac

echo "cloudflared ready: cloudflared-${TARGET_TRIPLE}"
