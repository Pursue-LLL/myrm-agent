/**
 * Browser tab events: keep the server's tab list and the paused-tab set in step with what the user does.
 *
 * [INPUT]
 * - chrome.tabs.onUpdated / onRemoved (POS: navigation, load completion and tab closing)
 * - tabs.js::sendTabsUpdate / access_policy.js::sendAccessPolicyUpdate (POS: reports to the server)
 *
 * [OUTPUT]
 * - (none; registers listeners when imported)
 *
 * [POS] Listener registration for tab changes. Importing it from the service-worker entry arms the listeners.
 */

import { sendAccessPolicyUpdate } from "./access_policy.js";
import { persistAccessPolicyLocal, state } from "./state.js";
import { sendTabsUpdate } from "./tabs.js";

chrome.tabs.onUpdated.addListener((_tabId, changeInfo) => {
  if (changeInfo.url || changeInfo.status === "complete") {
    sendTabsUpdate();
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  state.attachedTabs.delete(tabId);
  if (state.pausedTabIds.delete(tabId)) {
    persistAccessPolicyLocal();
    sendAccessPolicyUpdate();
  }
  sendTabsUpdate();
});
