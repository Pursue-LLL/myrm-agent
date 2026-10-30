#!/usr/bin/env bash
# Export the Apple signing / notarization secrets to later steps only when they are configured.
# Tauri treats a defined-but-empty APPLE_* variable as "signing requested" and fails the bundle on its
# keychain import, so an unsigned build must not define them at all.
set -euo pipefail

: "${GITHUB_ENV:?must run inside GitHub Actions}"

exported=0
for name in APPLE_CERTIFICATE APPLE_CERTIFICATE_PASSWORD APPLE_SIGNING_IDENTITY APPLE_ID APPLE_PASSWORD APPLE_TEAM_ID; do
  value="${!name:-}"
  if [[ -n "$value" ]]; then
    # The delimiter form of GITHUB_ENV keeps a multi-line value (a line-wrapped base64 certificate) in
    # one variable; the plain NAME=value form would turn its extra lines into bogus entries.
    delimiter="gh_env_${name}_${RANDOM}${RANDOM}"
    printf '%s<<%s\n%s\n%s\n' "$name" "$delimiter" "$value" "$delimiter" >>"$GITHUB_ENV"
    exported=$((exported + 1))
  fi
done

if [[ "$exported" -eq 0 ]]; then
  echo "[apple-signing-env] no Apple signing secrets configured; building unsigned"
else
  echo "[apple-signing-env] exported ${exported} Apple signing variable(s)"
fi
