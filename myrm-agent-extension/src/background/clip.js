/**
 * Wiki clip glue: the clip target agent synced from the server and the clip outcome shown to the user.
 *
 * [INPUT]
 * - state (POS: server address, clip target, last clip outcome)
 * - wiki/clip_client.js / wiki/clip_notify.js / wiki/deep_links.js (POS: upload, notification, settings deep links)
 * - transport.js (POS: toolbar badge)
 *
 * [OUTPUT]
 * - applyClipAgentConfig: adopt and persist the clip target agent and WebUI origin
 * - syncClipAgentConfig: fetch the clip target from the server
 * - submitClipToWiki: clip a tab's page or selection and report the outcome (badge, notification, popup status)
 *
 * [POS] Extension → server REST clip flow (zero LLM); the upload itself lives in wiki/clip_client.js.
 */

import { msg } from "../i18n.js";
import { submitClipToWiki as runClipToWiki } from "../wiki/clip_client.js";
import { notifyClipOutcome } from "../wiki/clip_notify.js";
import {
  buildClipRawUrl,
  buildDuplicateReviewUrl,
  buildWikiIgnoreUrl,
  wikiHttpBaseFromServerUrl,
} from "../wiki/deep_links.js";
import { persistClipTarget, state } from "./state.js";
import { isSocketOpen, updateBadge } from "./transport.js";

export function applyClipAgentConfig(agentId, origin) {
  state.clipAgentId = agentId || "";
  state.webUiOrigin = origin || "";
  if (state.webUiOrigin) {
    state.clipSavedWithoutOrigin = false;
  }
  persistClipTarget();
}

export async function syncClipAgentConfig() {
  const httpBase = wikiHttpBaseFromServerUrl(state.serverUrl);
  if (!httpBase) return;
  try {
    const headers = state.authToken ? { Authorization: `Bearer ${state.authToken}` } : {};
    const resp = await fetch(`${httpBase.replace(/\/$/, "")}/api/v1/extension/clip-agent`, { headers });
    if (!resp.ok) return;
    const data = await resp.json();
    applyClipAgentConfig(data.agent_id, data.web_ui_origin);
  } catch {
    // Non-fatal: clip falls back to default vault when sync fails.
  }
}

export async function submitClipToWiki(tab, mode) {
  const result = await runClipToWiki(tab, mode, {
    serverUrl: state.serverUrl,
    authToken: state.authToken,
    clipAgentId: state.clipAgentId,
  });
  if (result.ok) {
    state.lastError = "";
    state.lastClipErrorKind = "";
    state.lastClipSuccessUrl = buildClipRawUrl(state.webUiOrigin, state.clipAgentId, result.relative_path || "");
    state.clipSavedWithoutOrigin = !state.webUiOrigin.trim();
    chrome.action.setBadgeText({ text: "OK" });
    setTimeout(() => updateBadge(isSocketOpen() ? "connected" : "disconnected"), 2000);
    if (state.clipSavedWithoutOrigin) {
      void notifyClipOutcome("success_no_origin");
    } else {
      void notifyClipOutcome("success", { openUrl: state.lastClipSuccessUrl });
    }
    return;
  }
  state.lastClipSuccessUrl = "";
  state.clipSavedWithoutOrigin = false;
  state.lastClipErrorKind = result.conflict ? "duplicate" : result.security_blocked ? "security" : "generic";
  state.lastError = result.error || msg("errClipFailed");
  if (result.conflict) {
    void notifyClipOutcome("duplicate", {
      openUrl: buildDuplicateReviewUrl(state.webUiOrigin, state.clipAgentId),
    });
  } else if (result.security_blocked) {
    void notifyClipOutcome("security", {
      openUrl: buildWikiIgnoreUrl(state.webUiOrigin, state.clipAgentId),
    });
  } else {
    void notifyClipOutcome("error", { errorMessage: state.lastError });
    updateBadge("error");
  }
}
