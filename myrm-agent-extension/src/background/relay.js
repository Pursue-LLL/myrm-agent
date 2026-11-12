/**
 * Commands the server's CDP relay sends to the browser: attach, detach, forward a CDP call, create a tab.
 *
 * [INPUT]
 * - state / policy.js (POS: every command re-checks the tab or domain against the access policy)
 * - debugger.js (POS: attaching and detaching)
 * - background_window.js (POS: background tab creation)
 * - transport.js::send (POS: relay_result back to the server)
 *
 * [OUTPUT]
 * - executeRelayCommand: run one relay command and send its result; throws when it is refused or fails
 *
 * [POS] The enforcement point for the loopback CDP relay: no tab is attached, driven or created without passing the policy.
 */

import { getOrCreateBackgroundTab } from "./background_window.js";
import { attachDebugger, detachDebugger } from "./debugger.js";
import { extractDomain, isNavigationTargetAuthorized, isTabAuthorized } from "./policy.js";
import { state } from "./state.js";
import { send } from "./transport.js";

const RELAY_CDP_NAVIGATE_METHODS = new Set(["Page.navigate"]);

function assertRelayCdpNavigateAuthorized(method, params) {
  if (!RELAY_CDP_NAVIGATE_METHODS.has(method)) {
    return;
  }
  const rawParams = params && typeof params === "object" ? params : {};
  const url = typeof rawParams.url === "string" ? rawParams.url : "";
  if (!url) {
    return;
  }
  if (!isNavigationTargetAuthorized(url, state)) {
    const targetDomain = extractDomain(url).toLowerCase();
    throw new Error(`Domain ${targetDomain || "(empty)"} is not authorized`);
  }
}

async function assertRelayTabAuthorized(tabId) {
  const tab = await chrome.tabs.get(tabId);
  if (!isTabAuthorized(tab, state)) {
    throw new Error(`Tab ${tabId} is not authorized`);
  }
}

export async function executeRelayCommand(seq, command) {
  if (!Number.isInteger(seq)) {
    throw new Error("relay command requires integer seq");
  }
  switch (command.type) {
    case "attach": {
      const tabId = command.tabId;
      if (!Number.isInteger(tabId)) {
        throw new Error("attach requires tabId");
      }
      await assertRelayTabAuthorized(tabId);
      const result = await attachDebugger(tabId);
      send({ type: "relay_result", seq, result });
      return;
    }
    case "detach": {
      const tabId = command.tabId;
      if (Number.isInteger(tabId)) {
        await detachDebugger(tabId);
      }
      send({ type: "relay_result", seq, result: {} });
      return;
    }
    case "cdp": {
      const tabId = command.tabId;
      const method = command.method;
      if (!Number.isInteger(tabId) || typeof method !== "string") {
        throw new Error("cdp requires tabId and method");
      }
      assertRelayCdpNavigateAuthorized(method, command.params);
      await assertRelayTabAuthorized(tabId);
      if (!state.attachedTabs.has(tabId)) {
        await attachDebugger(tabId);
      }
      const target = command.sessionId
        ? { tabId, sessionId: command.sessionId }
        : { tabId };
      const result = await chrome.debugger.sendCommand(
        target,
        method,
        command.params || {},
      );
      send({ type: "relay_result", seq, result: result ?? {} });
      return;
    }
    case "createTab": {
      const url = typeof command.url === "string" && command.url ? command.url : "about:blank";
      const targetDomain = extractDomain(url).toLowerCase();
      if (targetDomain && !isNavigationTargetAuthorized(url, state)) {
        throw new Error(`Domain ${targetDomain} is not authorized`);
      }
      const background = command.background === true;
      let tabId;
      if (background) {
        tabId = await getOrCreateBackgroundTab(url);
      } else {
        const created = await chrome.tabs.create({ url, active: true });
        tabId = created.id;
      }
      if (!Number.isInteger(tabId)) {
        throw new Error("createTab failed to allocate tabId");
      }
      send({ type: "relay_result", seq, result: { tabId } });
      return;
    }
    default:
      throw new Error(`unknown relay command: ${command.type || "(missing)"}`);
  }
}
