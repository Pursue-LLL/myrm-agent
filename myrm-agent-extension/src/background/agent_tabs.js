/**
 * Tabs the Agent opened itself: opening them, remembering which they are, and closing them again.
 *
 * [INPUT]
 * - state (POS: the set of Agent tab ids, persisted for the browser session, and which Agent tab opened which)
 * - policy.js::isBlankUrl / isNavigationTargetAuthorized (POS: what counts as a blank page, which pages the Agent may see)
 * - background_window.js::ensureBackgroundWindow (POS: the window for work that must not disturb the user)
 * - tab_group.js::addToAgentGroup (POS: visual marker)
 *
 * [OUTPUT]
 * - openAgentTab: a new tab, in the user's window or in the background window
 * - claimBackgroundTab: a blank tab of the background window (a free one is reused), now the Agent's
 * - adoptOpenedTab: a tab an Agent tab opened (a link with target=_blank, window.open) is the Agent's too
 * - closeAgentTab: close a tab the Agent opened; any other tab is left open and reported as not closed
 * - forgetAgentTab / pruneAgentTabs: drop ownership of tabs that no longer exist
 *
 * [POS] The one place that decides which tabs are the Agent's. The policy admits an Agent tab while it is blank, so the
 * Agent can take a page it opened to the site it needs; and because only these tabs can be closed on the server's
 * request, a tab the user opened is never closed by the Agent. A tab opened from one of the user's own tabs stays the
 * user's: nothing says whether the user or the Agent made it open. So does a tab headed for a site the user did not
 * authorize.
 */

import { ensureBackgroundWindow } from "./background_window.js";
import { isBlankUrl, isNavigationTargetAuthorized } from "./policy.js";
import { persistAgentTabs, state } from "./state.js";
import { addToAgentGroup } from "./tab_group.js";

function adopt(tabId) {
  state.agentTabIds.add(tabId);
  persistAgentTabs();
}

export async function claimBackgroundTab() {
  const windowId = await ensureBackgroundWindow();
  const tabs = await chrome.tabs.query({ windowId });
  // Selecting and adopting happen without an await in between, so two claims never take the same tab.
  const free = tabs.find((tab) => isBlankUrl(tab.url) && !state.agentTabIds.has(tab.id));
  if (free) {
    adopt(free.id);
    return free.id;
  }
  // The background window is never focused, so making its new tab active does not touch what the user is viewing.
  const created = await chrome.tabs.create({ windowId, url: "about:blank", active: true });
  adopt(created.id);
  return created.id;
}

export async function openAgentTab(url, { background }) {
  if (background) {
    const tabId = await claimBackgroundTab();
    if (!isBlankUrl(url)) {
      await chrome.tabs.update(tabId, { url });
    }
    return tabId;
  }
  const tab = await chrome.tabs.create({ url, active: true });
  adopt(tab.id);
  await addToAgentGroup(tab.id);
  return tab.id;
}

/**
 * Returns whether the tab was adopted: the Agent must see the page its own click opened, unless that page is headed
 * for a site the Agent may not see.
 *
 * The opener comes from the navigation event, not from the tab's `openerTabId`: the browser puts the window's active tab
 * there, which is not the tab whose page opened it when that page was working in the background.
 */
export function adoptOpenedTab(tabId, sourceTabId, url) {
  if (!state.agentTabIds.has(sourceTabId) || !(isBlankUrl(url) || isNavigationTargetAuthorized(url, state))) {
    return false;
  }
  adopt(tabId);
  state.agentTabOpeners.set(tabId, sourceTabId);
  return true;
}

export async function closeAgentTab(tabId) {
  if (!state.agentTabIds.has(tabId)) {
    return false;
  }
  try {
    await chrome.tabs.get(tabId);
  } catch {
    forgetAgentTab(tabId);
    return true;
  }
  await chrome.tabs.remove(tabId);
  return true;
}

export function forgetAgentTab(tabId) {
  state.agentTabOpeners.delete(tabId);
  if (state.agentTabIds.delete(tabId)) {
    persistAgentTabs();
  }
}

export async function pruneAgentTabs() {
  const open = new Set((await chrome.tabs.query({})).map((tab) => tab.id));
  const gone = [...state.agentTabIds].filter((tabId) => !open.has(tabId));
  gone.forEach((tabId) => {
    state.agentTabIds.delete(tabId);
    state.agentTabOpeners.delete(tabId);
  });
  if (gone.length > 0) {
    persistAgentTabs();
  }
}
