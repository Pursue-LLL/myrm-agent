#!/usr/bin/env bash
#
# verify-signing.sh — Post-build macOS code signing verifier for the .app / .dmg artifacts of a release.
#
# --level says how far the build was meant to be signed; every check of a level is a hard check:
#
#   sealed      The bundle carries a signature that seals it (an ad-hoc one is enough): the Info.plist and every
#               resource are bound to it. Gatekeeper still stops the first launch, but as an app it cannot verify,
#               with an "Open Anyway" button; an unsealed bundle is reported as damaged, with no way to open it.
#                 1. codesign --verify --deep --strict : seal integrity
#                 2. codesign -dv                      : signature details (audit trail)
#               A .dmg is mounted read-only and the .app inside it gets the same two checks.
#   notarized   Developer ID signature plus Apple notarization:
#                 1. codesign --verify --deep --strict : signature integrity
#                 2. codesign -dv                      : signature details (audit trail)
#                 3. spctl --assess -t exec|open       : Gatekeeper acceptance simulation
#                 4. xcrun stapler validate            : Apple Notary staple presence
#               A .dmg gets checks 3 and 4 only.
#
# Exit code = number of failed checks. Non-zero exit fails the calling step.
# Full verification log is also written to the --log path.
#
# Usage:
#   scripts/verify-signing.sh --level sealed|notarized \
#     --search-root src-tauri/target \
#     --log dist/verification.log \
#     [--list-out dist/artifacts.txt]
#
#   scripts/verify-signing.sh --level sealed --artifact path/to/MyrmAgent.app

set -euo pipefail

search_roots=()
explicit_artifacts=()
list_out=""
log_path=""
level=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --level)
      level="$2"
      shift 2
      ;;
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
      awk 'NR > 1 { if (/^#/) { sub(/^# ?/, ""); print } else exit }' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 64
      ;;
  esac
done

case "$level" in
  sealed|notarized) ;;
  *)
    echo "verify-signing.sh: --level sealed|notarized is required" >&2
    exit 64
    ;;
esac

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
    # A bundle's own content (a .app inside the .app's resources) is not a release artifact.
    while IFS= read -r path; do
      [[ -n "$path" ]] && artifacts+=("$(absolute_path "$path")")
    done < <(
      find "$root" \
        \( \( -path '*/release/bundle/macos/*.app' -type d \) \
        -o \( -path '*/release/bundle/dmg/*.dmg' -type f \) \) \
        ! -path '*.app/*' \
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

# Runs one check; a check that does not pass counts as a failure and never stops the run.
check() {
  run_and_log "$@" || failures=$((failures + 1))
}

verify_app() {
  local app="$1"
  check "codesign --verify --deep --strict" \
    codesign --verify --deep --strict --verbose=4 "$app"
  check "codesign -dv (signature details)" \
    codesign -dv --verbose=4 "$app"
  if [[ "$level" == "notarized" ]]; then
    check "spctl --assess -t exec (Gatekeeper)" \
      spctl --assess --type exec --verbose=2 "$app"
    check "stapler validate (notarization)" \
      xcrun stapler validate "$app"
  fi
}

mount_point=""

detach_dmg() {
  [[ -n "$mount_point" ]] || return 0
  hdiutil detach -quiet "$mount_point" || hdiutil detach -force -quiet "$mount_point" || true
  rmdir "$mount_point" 2>/dev/null || true
  mount_point=""
}
trap detach_dmg EXIT

# What a first-time user opens is the .dmg, so below the notarized level the .app inside it is verified.
verify_dmg() {
  local dmg="$1" app
  local apps=()
  if [[ "$level" == "notarized" ]]; then
    check "spctl --assess -t open (Gatekeeper)" \
      spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
    check "stapler validate (notarization)" \
      xcrun stapler validate "$dmg"
    return
  fi
  mount_point="$(mktemp -d)"
  if ! run_and_log "hdiutil attach (read-only)" \
    hdiutil attach -readonly -nobrowse -noautoopen -mountpoint "$mount_point" "$dmg"; then
    failures=$((failures + 1))
    detach_dmg
    return
  fi
  while IFS= read -r app; do
    apps+=("$app")
  done < <(find "$mount_point" -maxdepth 1 -name '*.app' -type d)
  if [[ ${#apps[@]} -eq 0 ]]; then
    log "✗ the .dmg holds no .app"
    failures=$((failures + 1))
  else
    for app in "${apps[@]}"; do
      log "Inside the .dmg: $(basename "$app")"
      verify_app "$app"
    done
  fi
  detach_dmg
}

for artifact in "${artifacts[@]}"; do
  log "════════════════════════════════════════════════════════════════════"
  log "Artifact: $artifact"
  log "════════════════════════════════════════════════════════════════════"

  case "$artifact" in
    *.app)
      verify_app "$artifact"
      ;;
    *.dmg)
      verify_dmg "$artifact"
      ;;
    *)
      log "✗ Unsupported artifact type: $artifact"
      failures=$((failures + 1))
      ;;
  esac
done

log "════════════════════════════════════════════════════════════════════"
if [[ $failures -gt 0 ]]; then
  log "RESULT: $failures check(s) failed across ${#artifacts[@]} artifact(s) at level $level"
  exit "$failures"
fi
log "RESULT: all ${#artifacts[@]} artifact(s) passed $level verification"
exit 0
