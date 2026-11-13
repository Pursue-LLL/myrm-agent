/**
 * Commands the server's CDP relay sends to the browser: attach, detach, forward a CDP call, create a tab, close a tab.
 *
 * [INPUT]
 * - state / policy.js (POS: every command re-checks the tab or domain against the access policy)
 * - debugger.js (POS: attaching and detaching)
 * - agent_tabs.js (POS: opening and closing the Agent's own tabs)
 * - transport.js::send (POS: relay_result back to the server)
 *
 * [OUTPUT]
 * - executeRelayCommand: run one relay command and send its result; throws when it is refused or fails
 * - TabNotAuthorizedError: thrown for a tab that is no longer on an authorized site; its code tells the server to let
 *   go of the tab, where any other error is only a command that failed
 *
 * [POS] The enforcement point for the loopback CDP relay: no tab is attached, driven or created without passing the
 * policy, and only a tab the Agent opened is ever closed.
 */

import { closeAgentTab, openAgentTab } from "./agent_tabs.js";
import { attachDebugger, detachDebugger } from "./debugger.js";
import { extractDomain, isBlankUrl, isNavigationTargetAuthorized, isTabAuthorized } from "./policy.js";
import { state } from "./state.js";
import { send } from "./transport.js";

const RELAY_CDP_NAVIGATE_METHODS = new Set(["Page.navigate"]);

export class TabNotAuthorizedError extends Error {
  constructor(tabId) {
    super(`Tab ${tabId} is not authorized`);
    this.code = "tab_not_authorized";
  }
}

function assertRelayCdpNavigateAuthorized(tabId, method, params) {
  if (!RELAY_CDP_NAVIGATE_METHODS.has(method)) {
    return;
  }
  const rawParams = params && typeof params === "object" ? params : {};
  const url = typeof rawParams.url === "string" ? rawParams.url : "";
  if (!url) {
    return;
  }
  // The browser toolkit discards a document it refused after loading it by taking the tab back to a blank page, so a tab
  // the Agent opened may navigate to blank. A tab the user opened is never navigated away to nothing.
  if (isBlankUrl(url) && state.agentTabIds.has(tabId)) {
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
    throw new TabNotAuthorizedError(tabId);
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
      assertRelayCdpNavigateAuthorized(tabId, method, command.params);
      await assertRelayTabAuthorized(tabId);
      if (!state.attachedTabs.has(tabId)) {
        await attachDebugger(tabId);
      }
      const target = command.sessionId ? { tabId, sessionId: command.sessionId } : { tabId };
      const result = await chrome.debugger.sendCommand(target, method, command.params || {});
      send({ type: "relay_result", seq, result: result ?? {} });
      return;
    }
    case "createTab": {
      const url = typeof command.url === "string" && command.url ? command.url : "about:blank";
      if (!isBlankUrl(url) && !isNavigationTargetAuthorized(url, state)) {
        throw new Error(`Domain ${extractDomain(url).toLowerCase() || "(empty)"} is not authorized`);
      }
      const tabId = await openAgentTab(url, { background: command.background === true });
      send({ type: "relay_result", seq, result: { tabId } });
      return;
    }
    case "closeTab": {
      const tabId = command.tabId;
      if (!Number.isInteger(tabId)) {
        throw new Error("closeTab requires tabId");
      }
      const closed = await closeAgentTab(tabId);
      send({ type: "relay_result", seq, result: { closed } });
      return;
    }
    default:
      throw new Error(`unknown relay command: ${command.type || "(missing)"}`);
  }
}
