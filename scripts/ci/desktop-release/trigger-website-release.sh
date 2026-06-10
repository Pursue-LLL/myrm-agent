#!/usr/bin/env bash
# After a desktop GitHub Release is finalized, tag myrm-agent-brand and POST CF Pages Deploy Hook.
# Requires secrets: BRAND_RELEASE_PAT (contents:write on brand repo), CF_PAGES_DEPLOY_HOOK.
set -euo pipefail

DESKTOP_TAG="${DESKTOP_TAG:?Set DESKTOP_TAG (e.g. v0.1.14)}"
BRAND_REPO="${BRAND_REPO:-Pursue-LLL/myrm-agent-brand}"
WEBSITE_TAG="website-v${DESKTOP_TAG#v}"

if [[ -z "${BRAND_RELEASE_PAT:-}" ]]; then
  echo "[trigger-website-release] BRAND_RELEASE_PAT not set; skipping website deploy trigger." >&2
  exit 0
fi

if [[ -z "${CF_PAGES_DEPLOY_HOOK:-}" ]]; then
  echo "[trigger-website-release] CF_PAGES_DEPLOY_HOOK not set; skipping website deploy trigger." >&2
  exit 0
fi

export GH_TOKEN="$BRAND_RELEASE_PAT"

MAIN_SHA="$(gh api "repos/${BRAND_REPO}/commits/main" --jq .sha)"
echo "[trigger-website-release] brand main @ ${MAIN_SHA:0:7}"

resolve_tag_commit() {
  local ref_type ref_sha
  ref_type="$(gh api "repos/${BRAND_REPO}/git/refs/tags/${WEBSITE_TAG}" --jq '.object.type')"
  ref_sha="$(gh api "repos/${BRAND_REPO}/git/refs/tags/${WEBSITE_TAG}" --jq '.object.sha')"
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

http_code="$(curl -sS -o /tmp/cf-hook-response.txt -w '%{http_code}' -X POST "$CF_PAGES_DEPLOY_HOOK")"
if [[ "$http_code" != "200" && "$http_code" != "201" && "$http_code" != "202" ]]; then
  echo "[trigger-website-release] Deploy hook failed: HTTP ${http_code}" >&2
  cat /tmp/cf-hook-response.txt >&2 || true
  exit 1
fi

echo "[trigger-website-release] Deploy hook accepted (${WEBSITE_TAG} → myrmagent.ai). Check CF Pages → Deployments."
