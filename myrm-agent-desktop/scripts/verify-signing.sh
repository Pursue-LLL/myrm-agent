#!/usr/bin/env bash
#
# verify-signing.sh — Post-build macOS code signing & notarization verifier.
#
# Runs inside the GitHub Actions release workflow after `tauri-action` produces
# .app / .dmg artifacts. Performs four hard checks for each artifact:
#
#   1. codesign --verify --deep --strict           : signature integrity
#   2. codesign -dv                                : signature details (audit trail)
#   3. spctl --assess -t exec|open                 : Gatekeeper acceptance simulation
#   4. xcrun stapler validate                      : Apple Notary staple presence
#
# Exit code = number of failed checks. Non-zero exit fails the CI step.
# Full verification log is also written to --log path for artifact upload.
#
# Usage:
#   scripts/verify-signing.sh \
#     --search-root src-tauri/target \
#     --log dist/verification.log \
#     [--list-out dist/artifacts.txt]
#
#   scripts/verify-signing.sh --artifact path/to/MyrmAgent.app

set -euo pipefail

search_roots=()
explicit_artifacts=()
list_out=""
log_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --search-root)
      search_roots+=("$2")
      shift 2
      ;;
    --artifact)
      explicit_artifacts+=("$2")
      shift 2
      ;;
    --list-out)
      list_out="$2"
      shift 2
      ;;
    --log)
      log_path="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 64
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "verify-signing.sh: macOS-only verifier, current OS is $(uname -s)" >&2
  exit 65
fi

if [[ -n "$log_path" ]]; then
  mkdir -p "$(dirname "$log_path")"
  : > "$log_path"
fi

log() {
  if [[ -n "$log_path" ]]; then
    printf '%s\n' "$1" | tee -a "$log_path"
  else
    printf '%s\n' "$1"
  fi
}

run_and_log() {
  local description="$1"
  shift
  log "▶ $description"
  if [[ -n "$log_path" ]]; then
    if ! "$@" 2>&1 | tee -a "$log_path"; then
      log "✗ $description FAILED"
      return 1
    fi
  elif ! "$@"; then
    log "✗ $description FAILED"
    return 1
  fi
  log "✓ $description OK"
  return 0
}

absolute_path() {
  local raw="$1"
  if [[ "$raw" = /* ]]; then
    printf '%s\n' "$raw"
  else
    printf '%s/%s\n' "$PWD" "$raw"
  fi
}

artifacts=()
if [[ ${#explicit_artifacts[@]} -gt 0 ]]; then
  for art in "${explicit_artifacts[@]}"; do
    artifacts+=("$(absolute_path "$art")")
  done
else
  if [[ ${#search_roots[@]} -eq 0 ]]; then
    echo "verify-signing.sh: at least one --search-root or --artifact is required" >&2
    exit 64
  fi
  for root in "${search_roots[@]}"; do
    [[ -d "$root" ]] || continue
    while IFS= read -r path; do
      [[ -n "$path" ]] && artifacts+=("$(absolute_path "$path")")
    done < <(
      find "$root" \
        \( -path '*/release/bundle/macos/*.app' \
        -o -path '*/release/bundle/dmg/*.dmg' \) \
        -print 2>/dev/null | sort -u
    )
  done
fi

if [[ ${#artifacts[@]} -eq 0 ]]; then
  echo "verify-signing.sh: no .app or .dmg artifacts found under search roots" >&2
  exit 66
fi

if [[ -n "$list_out" ]]; then
  mkdir -p "$(dirname "$list_out")"
  printf '%s\n' "${artifacts[@]}" > "$list_out"
fi

failures=0

for artifact in "${artifacts[@]}"; do
  log "════════════════════════════════════════════════════════════════════"
  log "Artifact: $artifact"
  log "════════════════════════════════════════════════════════════════════"

  case "$artifact" in
    *.app)
      run_and_log "codesign --verify --deep --strict" \
        codesign --verify --deep --strict --verbose=4 "$artifact" \
        || failures=$((failures + 1))
      run_and_log "codesign -dv (signature details)" \
        codesign -dv --verbose=4 "$artifact" \
        || failures=$((failures + 1))
      run_and_log "spctl --assess -t exec (Gatekeeper)" \
        spctl --assess --type exec --verbose=2 "$artifact" \
        || failures=$((failures + 1))
      run_and_log "stapler validate (notarization)" \
        xcrun stapler validate "$artifact" \
        || failures=$((failures + 1))
      ;;
    *.dmg)
      run_and_log "spctl --assess -t open (Gatekeeper)" \
        spctl --assess --type open --context context:primary-signature --verbose=2 "$artifact" \
        || failures=$((failures + 1))
      run_and_log "stapler validate (notarization)" \
        xcrun stapler validate "$artifact" \
        || failures=$((failures + 1))
      ;;
    *)
      log "✗ Unsupported artifact type: $artifact"
      failures=$((failures + 1))
      ;;
  esac
done

log "════════════════════════════════════════════════════════════════════"
if [[ $failures -gt 0 ]]; then
  log "RESULT: $failures check(s) failed across ${#artifacts[@]} artifact(s)"
  exit "$failures"
fi
log "RESULT: all ${#artifacts[@]} artifact(s) passed signing + notarization verification"
exit 0
