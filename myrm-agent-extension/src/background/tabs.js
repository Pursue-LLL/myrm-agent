/**
 * Tab queries the Agent sees and the tab list pushed to the server.
 *
 * [INPUT]
 * - state (POS: access policy)
 * - policy.js (POS: which tabs the policy admits)
 * - transport.js::send (POS: tabs_update to the server)
 *
 * [OUTPUT]
 * - getAuthorizedTabs: tabs the Agent may act on right now
 * - getListableTabs: tabs the policy admits, paused ones included (what the settings page lists)
 * - findTabForDomain: the active (else first) authorized tab on a domain
 * - waitForTabLoad: resolve with the tab once it finishes loading, or when the timeout hits
 * - sendTabsUpdate: push the listable tabs to the server
 *
 * [POS] Read side of tab access; opening, attaching and closing tabs live elsewhere.
 */

import { extractDomain, isTabAuthorized, isTabEligibleForPolicy } from "./policy.js";
import { state } from "./state.js";
import { send } from "./transport.js";

function describeTab(tab) {
  return {
    id: tab.id,
    url: tab.url || "",
    title: tab.title || "",
    domain: extractDomain(tab.url || ""),
    active: tab.active,
  };
}

export async function getAuthorizedTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs.filter((tab) => isTabAuthorized(tab, state)).map(describeTab);
}

export async function getListableTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs.filter((tab) => isTabEligibleForPolicy(tab, state)).map(describeTab);
}

export async function findTabForDomain(domain) {
  const tabs = await chrome.tabs.query({});
  const authorized = tabs.filter((tab) => isTabAuthorized(tab, state));

  if (domain) {
    const matching = authorized.filter((tab) => extractDomain(tab.url || "") === domain);
    return matching.find((tab) => tab.active) || matching[0] || null;
  }

  return authorized.find((tab) => tab.active) || authorized[0] || null;
}

export async function waitForTabLoad(tabId, timeoutMs = 20000) {
  return await new Promise((resolve) => {
    let done = false;
    const finish = (tab) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      resolve(tab || null);
    };

    const onUpdated = (updatedTabId, changeInfo, tab) => {
      if (updatedTabId !== tabId) return;
      if (changeInfo.status === "complete") {
        finish(tab);
      }
    };

    const timer = setTimeout(async () => {
      try {
        const tab = await chrome.tabs.get(tabId);
        finish(tab);
      } catch {
        finish(null);
      }
    }, timeoutMs);

    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}

export function sendTabsUpdate() {
  getListableTabs().then((tabs) => {
    send({ type: "tabs_update", tabs });
  });
}
