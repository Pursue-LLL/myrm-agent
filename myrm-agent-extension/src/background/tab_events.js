/**
 * Browser tab events: keep the server's tab list, the paused-tab set and the Agent's tabs in step with what the user does.
 *
 * [INPUT]
 * - chrome.webNavigation.onCreatedNavigationTarget (POS: a tab created to host a navigation, with the tab that triggered it)
 * - chrome.tabs.onUpdated / onRemoved (POS: navigation, load completion and tab closing)
 * - agent_tabs.js::adoptOpenedTab / forgetAgentTab (POS: a tab an Agent tab opened is the Agent's; a closed tab is not)
 * - tabs.js::sendTabsUpdate / access_policy.js::sendAccessPolicyUpdate (POS: reports to the server)
 *
 * [OUTPUT]
 * - (none; registers listeners when imported)
 *
 * [POS] Listener registration for tab changes. Importing it from the service-worker entry arms the listeners.
 */

import { sendAccessPolicyUpdate } from "./access_policy.js";
import { adoptOpenedTab, forgetAgentTab } from "./agent_tabs.js";
import { persistAccessPolicyLocal, state, whenRestored } from "./state.js";
import { sendTabsUpdate } from "./tabs.js";

chrome.webNavigation.onCreatedNavigationTarget.addListener(async ({ tabId, sourceTabId, url }) => {
  // A worker woken by this event starts with empty state; the source is only known as an Agent tab once it is restored.
  await whenRestored();
  if (adoptOpenedTab(tabId, sourceTabId, url)) {
    sendTabsUpdate();
  }
});

chrome.tabs.onUpdated.addListener((_tabId, changeInfo) => {
  if (changeInfo.url || changeInfo.status === "complete") {
    sendTabsUpdate();
  }
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  // A worker woken by this event starts with empty state; editing it before it is restored would persist the blanks.
  await whenRestored();
  state.attachedTabs.delete(tabId);
  forgetAgentTab(tabId);
  if (state.pausedTabIds.delete(tabId)) {
    persistAccessPolicyLocal();
    sendAccessPolicyUpdate();
  }
  sendTabsUpdate();
});
