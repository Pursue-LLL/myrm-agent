#!/bin/bash
set -e

# Define target binaries directory
BIN_DIR="$(dirname "$0")/../src-tauri/binaries"
mkdir -p "$BIN_DIR"
cd "$BIN_DIR"

echo "Downloading cloudflared binaries..."

# macOS ARM64
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz | tar xz
mv cloudflared cloudflared-aarch64-apple-darwin
chmod +x cloudflared-aarch64-apple-darwin

# macOS x86_64
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz | tar xz
mv cloudflared cloudflared-x86_64-apple-darwin
chmod +x cloudflared-x86_64-apple-darwin

# Windows x86_64
curl -L -o cloudflared-x86_64-pc-windows-msvc.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe

echo "Done!"
