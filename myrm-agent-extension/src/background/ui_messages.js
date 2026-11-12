/**
 * Messages the popup and the side panel send to the service worker.
 *
 * [INPUT]
 * - state (POS: what the popup displays and edits)
 * - connection.js (POS: connect / disconnect buttons)
 * - access_policy.js / debugger.js / tabs.js (POS: policy edits and pausing a tab)
 * - wiki/deep_links.js (POS: settings deep links the popup shows)
 *
 * [OUTPUT]
 * - (none; registers the chrome.runtime.onMessage listener when imported)
 *   handled types: get_status, connect, disconnect, update_domains, update_access_policy, toggle_pause_tab,
 *   get_access_policy, glow_control
 *
 * [POS] The UI-facing API of the service worker. Unknown message types are ignored; every handled type answers once,
 * after the saved state is loaded (a message may be what woke the worker).
 */

import { buildDuplicateReviewUrl, buildWikiIgnoreUrl } from "../wiki/deep_links.js";
import { applyAccessPolicyPayload, sendAccessPolicyUpdate } from "./access_policy.js";
import { connect, disconnect } from "./connection.js";
import { detachDebugger } from "./debugger.js";
import { EXTENSION_CAPABILITIES, persistAccessPolicyLocal, persistConnection, state, whenRestored } from "./state.js";
import { sendTabsUpdate } from "./tabs.js";
import { isSocketOpen } from "./transport.js";

function sendGlowToTab(tabId, active) {
  chrome.tabs.sendMessage(tabId, { type: "glow", active }).catch(() => {
    if (active) {
      chrome.scripting.executeScript({ target: { tabId }, files: ["src/content/glow.js"] }).catch(() => {});
      setTimeout(() => chrome.tabs.sendMessage(tabId, { type: "glow", active }).catch(() => {}), 200);
    }
  });
}

function respondWith(sendResponse, task) {
  void (async () => {
    try {
      sendResponse({ ok: true, ...(await task()) });
    } catch (error) {
      sendResponse({ ok: false, error: error?.message || String(error) });
    }
  })();
}

// Each handler answers once through `sendResponse`, possibly after it returned.
const HANDLERS = new Map([
  [
    "get_status",
    (_message, sendResponse) => {
      sendResponse({
        connected: isSocketOpen(),
        connecting: state.isConnecting,
        lastError: state.lastError,
        lastClipErrorKind: state.lastClipErrorKind,
        serverUrl: state.serverUrl,
        authorizedDomains: state.authorizedDomains,
        attachedTabs: Array.from(state.attachedTabs.keys()),
        capabilities: Array.from(EXTENSION_CAPABILITIES),
        clipAgentId: state.clipAgentId,
        webUiOrigin: state.webUiOrigin,
        duplicateReviewUrl: buildDuplicateReviewUrl(state.webUiOrigin, state.clipAgentId),
        wikiIgnoreUrl: buildWikiIgnoreUrl(state.webUiOrigin, state.clipAgentId),
        clipSuccessUrl: state.lastClipSuccessUrl,
        clipSavedWithoutOrigin: state.clipSavedWithoutOrigin,
      });
    },
  ],
  [
    "connect",
    (message, sendResponse) => {
      state.serverUrl = message.serverUrl || state.serverUrl;
      state.authToken = message.authToken || state.authToken;
      persistConnection();
      connect();
      sendResponse({ ok: true });
    },
  ],
  [
    "disconnect",
    (_message, sendResponse) => {
      disconnect();
      sendResponse({ ok: true });
    },
  ],
  [
    "update_domains",
    (message, sendResponse) =>
      respondWith(sendResponse, async () => {
        await applyAccessPolicyPayload({ domains: message.domains || [] }, { notifyServer: true });
        persistAccessPolicyLocal();
        return {};
      }),
  ],
  [
    "update_access_policy",
    (message, sendResponse) =>
      respondWith(sendResponse, async () => {
        await applyAccessPolicyPayload(
          {
            allow_all_eligible_tabs: message.allowAllEligibleTabs,
            domains: message.domains,
            paused_tab_ids: message.pausedTabIds,
          },
          { notifyServer: true },
        );
        persistAccessPolicyLocal();
        sendTabsUpdate();
        return {};
      }),
  ],
  [
    "toggle_pause_tab",
    (message, sendResponse) => {
      const tabId = Number.parseInt(String(message.tabId), 10);
      if (!Number.isInteger(tabId)) {
        sendResponse({ ok: false });
        return;
      }
      respondWith(sendResponse, async () => {
        if (state.pausedTabIds.has(tabId)) {
          state.pausedTabIds.delete(tabId);
        } else {
          state.pausedTabIds.add(tabId);
          await detachDebugger(tabId);
        }
        persistAccessPolicyLocal();
        sendAccessPolicyUpdate();
        sendTabsUpdate();
        return { paused: state.pausedTabIds.has(tabId) };
      });
    },
  ],
  [
    "get_access_policy",
    (_message, sendResponse) => {
      sendResponse({
        authorizedDomains: state.authorizedDomains,
        allowAllEligibleTabs: state.allowAllEligibleTabs,
        pausedTabIds: [...state.pausedTabIds],
      });
    },
  ],
  [
    "glow_control",
    (message, sendResponse) => {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0]) sendGlowToTab(tabs[0].id, message.active);
      });
      sendResponse({ ok: true });
    },
  ],
]);

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handler = HANDLERS.get(message.type);
  if (!handler) return false;
  void whenRestored().then(() => handler(message, sendResponse));
  return true;
});
