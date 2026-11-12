/**
 * chrome.debugger attachment to tabs and the events that come back from them.
 *
 * [INPUT]
 * - state (POS: attached tabs, access policy)
 * - policy.js::isTabAuthorized (POS: tabs the Agent may keep attached)
 * - background_window.js (POS: closing the background window's tabs when their debugger goes)
 * - transport.js::send (POS: forwarding CDP events and detach notices to the server)
 *
 * [OUTPUT]
 * - attachDebugger: attach to a tab once and report it, with the browser's own id for the tab's page target
 * - detachDebugger / detachAllDebuggers: release tabs; tabs in the background window are closed with their debugger
 * - detachUnauthorizedAttachedTabs: release every attached tab the policy no longer admits
 * - releaseStaleDebuggers: release attachments a previous service-worker instance left behind
 *
 * [POS] The only module that attaches or detaches chrome.debugger. Tabs the policy stops admitting lose their debugger here.
 */

import { cleanupBackgroundTabs } from "./background_window.js";
import { isTabAuthorized } from "./policy.js";
import { state } from "./state.js";
import { send } from "./transport.js";

const DEBUGGER_PROTOCOL_VERSION = "1.3";

// The CDP client matches this id against the page's main frame, so it must be the browser's own, never a made-up one.
async function findPageTargetId(tabId) {
  const targets = await chrome.debugger.getTargets();
  const page = targets.find((target) => target.tabId === tabId && target.type === "page");
  if (!page) {
    throw new Error(`The browser reports no page target for tab ${tabId}`);
  }
  return page.id;
}

export async function attachDebugger(tabId) {
  let targetId = state.attachedTabs.get(tabId);
  if (targetId === undefined) {
    await chrome.debugger.attach({ tabId }, DEBUGGER_PROTOCOL_VERSION);
    try {
      targetId = await findPageTargetId(tabId);
    } catch (error) {
      await chrome.debugger.detach({ tabId }).catch(() => {});
      throw error;
    }
    state.attachedTabs.set(tabId, targetId);
  }

  return { attached: true, tabId, targetId };
}

export async function detachUnauthorizedAttachedTabs() {
  // Snapshot: detaching awaits, and tabs attached meanwhile are not this pass's business.
  for (const tabId of Array.from(state.attachedTabs.keys())) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (!isTabAuthorized(tab, state)) {
        await detachDebugger(tabId);
      }
    } catch {
      await detachDebugger(tabId);
    }
  }
}

export async function detachDebugger(tabId) {
  if (state.attachedTabs.has(tabId)) {
    try {
      await chrome.debugger.detach({ tabId });
    } catch {
      // Tab may already be closed
    }
    state.attachedTabs.delete(tabId);

    // Close tab in background window to prevent accumulation
    if (state.backgroundWindowId !== null) {
      try {
        const tab = await chrome.tabs.get(tabId);
        if (tab.windowId === state.backgroundWindowId) {
          await chrome.tabs.remove(tabId);
        }
      } catch {
        // Tab already closed
      }
    }
  }
}

export function detachAllDebuggers() {
  for (const [tabId] of state.attachedTabs) {
    chrome.debugger.detach({ tabId }).catch(() => {});
  }
  state.attachedTabs.clear();
  cleanupBackgroundTabs();
}

// The browser keeps a tab attached when the service worker that attached it is stopped, and refuses a second attach.
export async function releaseStaleDebuggers() {
  const targets = await chrome.debugger.getTargets();
  await Promise.all(
    targets
      .filter((target) => target.attached && Number.isInteger(target.tabId) && !state.attachedTabs.has(target.tabId))
      // Another client (the user's DevTools) may be the one attached; the detach then fails and changes nothing.
      .map((target) => chrome.debugger.detach({ tabId: target.tabId }).catch(() => {})),
  );
}

chrome.debugger.onEvent.addListener((source, method, params) => {
  if (!source.tabId || !state.attachedTabs.has(source.tabId)) {
    return;
  }
  send({
    type: "cdp_event",
    tabId: source.tabId,
    sessionId: source.sessionId || undefined,
    method,
    params: params || {},
  });
});

chrome.debugger.onDetach.addListener((source, reason) => {
  if (source.tabId && state.attachedTabs.has(source.tabId)) {
    state.attachedTabs.delete(source.tabId);
    send({
      type: "debugger_detached",
      tabId: source.tabId,
      reason,
    });
  }
});
