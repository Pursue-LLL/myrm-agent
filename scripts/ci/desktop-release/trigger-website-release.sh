#!/usr/bin/env bash
# Tag myrm-agent-brand website-v* on main HEAD and POST CF Pages Deploy Hook after desktop finalize.
# Secrets: BRAND_RELEASE_PAT, CF_PAGES_DEPLOY_HOOK.
# Set REQUIRE_WEBSITE_DEPLOY=false for local dry runs only; CI release tags default to true (fail if missing).
set -euo pipefail

DESKTOP_TAG="${DESKTOP_TAG:?Set DESKTOP_TAG (e.g. v0.1.14)}"
BRAND_REPO="${BRAND_REPO:-Pursue-LLL/myrm-agent-brand}"
WEBSITE_TAG="website-v${DESKTOP_TAG#v}"
REQUIRE_WEBSITE_DEPLOY="${REQUIRE_WEBSITE_DEPLOY:-true}"

missing=()
[[ -z "${BRAND_RELEASE_PAT:-}" ]] && missing+=("BRAND_RELEASE_PAT")
[[ -z "${CF_PAGES_DEPLOY_HOOK:-}" ]] && missing+=("CF_PAGES_DEPLOY_HOOK")

if [[ ${#missing[@]} -gt 0 ]]; then
  msg="[trigger-website-release] Missing secrets: ${missing[*]}"
  if [[ "$REQUIRE_WEBSITE_DEPLOY" == "true" ]]; then
    echo "$msg" >&2
    echo "[trigger-website-release] Set myrm-agent repository secrets or REQUIRE_WEBSITE_DEPLOY=false (local only)." >&2
    exit 1
  fi
  echo "$msg; skipping (REQUIRE_WEBSITE_DEPLOY=false)." >&2
  exit 0
fi

export GH_TOKEN="$BRAND_RELEASE_PAT"

MAIN_SHA="$(gh api "repos/${BRAND_REPO}/commits/main" --jq .sha)"
echo "[trigger-website-release] brand main @ ${MAIN_SHA:0:7}"

resolve_tag_commit() {
  local payload ref_type ref_sha
  payload="$(gh api "repos/${BRAND_REPO}/git/refs/tags/${WEBSITE_TAG}")"
  ref_type="$(jq -r '.object.type' <<<"$payload")"
  ref_sha="$(jq -r '.object.sha' <<<"$payload")"
  if [[ "$ref_type" == "tag" ]]; then
    gh api "repos/${BRAND_REPO}/git/tags/${ref_sha}" --jq .object.sha
  else
    printf '%s' "$ref_sha"
  fi
}

tag_commit=""
if tag_commit="$(resolve_tag_commit 2>/dev/null)"; then
  if [[ "$tag_commit" == "$MAIN_SHA" ]]; then
    echo "[trigger-website-release] Tag ${WEBSITE_TAG} already at main HEAD; redeploy only."
  else
    echo "[trigger-website-release] Tag ${WEBSITE_TAG} points to ${tag_commit:0:7}, main is ${MAIN_SHA:0:7}." >&2
    echo "[trigger-website-release] Push brand main or use a new desktop version tag." >&2
    exit 1
  fi
else
  gh api "repos/${BRAND_REPO}/git/refs" -X POST \
    -f ref="refs/tags/${WEBSITE_TAG}" \
    -f sha="$MAIN_SHA"
  echo "[trigger-website-release] Created tag ${WEBSITE_TAG} on ${MAIN_SHA:0:7}"
fi

hook_response="$(mktemp)"
trap 'rm -f "$hook_response"' EXIT

http_code="$(curl -sS -o "$hook_response" -w '%{http_code}' -X POST "$CF_PAGES_DEPLOY_HOOK")"
if [[ "$http_code" != "200" && "$http_code" != "201" && "$http_code" != "202" ]]; then
  echo "[trigger-website-release] Deploy hook failed: HTTP ${http_code}" >&2
  cat "$hook_response" >&2 || true
  exit 1
fi

echo "[trigger-website-release] Deploy hook accepted (${WEBSITE_TAG} → myrmagent.ai). Check CF Pages → Deployments."
