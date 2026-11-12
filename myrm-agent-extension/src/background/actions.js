/**
 * Requests the server makes of the extension itself: list tabs, attach a debugger, navigate a tab, detach.
 *
 * [INPUT]
 * - state / policy.js (POS: each action re-checks the tab or domain against the access policy)
 * - tabs.js / debugger.js / agent_tabs.js (POS: the operations the actions are made of)
 *
 * [OUTPUT]
 * - executeAction: run one named action and return its result; throws when it is refused or fails
 *
 * [POS] The request/response half of the server protocol (the CDP relay has its own commands in relay.js).
 */

import { claimBackgroundTab } from "./agent_tabs.js";
import { attachDebugger, detachDebugger } from "./debugger.js";
import { extractDomain, isNavigationTargetAuthorized, isTabAuthorized, matchDomain } from "./policy.js";
import { state } from "./state.js";
import { findTabForDomain, getAuthorizedTabs, waitForTabLoad } from "./tabs.js";

export async function executeAction(action, payload) {
  switch (action) {
    case "list_tabs":
      return await getAuthorizedTabs();

    case "attach_debugger": {
      const { domain, tabId, background = false } = payload;

      // Explicit tab targeting bypasses background isolation
      if (tabId) {
        const tabs = await chrome.tabs.query({});
        const target = tabs.find((t) => t.id === tabId && isTabAuthorized(t, state));
        if (!target) {
          throw new Error(`Tab ${tabId} not found or not authorized`);
        }
        return await attachDebugger(tabId);
      }

      // Background mode: create/reuse isolated window to avoid disrupting user
      if (background && domain) {
        const url = `https://${domain}`;
        if (!isNavigationTargetAuthorized(url, state)) {
          throw new Error(`Domain ${domain} is not authorized`);
        }
        const bgTabId = await claimBackgroundTab();
        await chrome.tabs.update(bgTabId, { url });
        return await attachDebugger(bgTabId);
      }

      // Foreground fallback: operate on existing user tab
      const tab = await findTabForDomain(domain);
      if (!tab) {
        throw new Error(`No tab found for domain: ${domain || "(any authorized)"}`);
      }
      return await attachDebugger(tab.id);
    }

    case "navigate_url": {
      const { url, domain, tabId, background = true } = payload;
      if (!url || typeof url !== "string") {
        throw new Error("navigate_url requires a valid url");
      }

      const targetDomain = extractDomain(url).toLowerCase();
      const requestedDomain = (domain || "").toLowerCase();
      if (!targetDomain || !isNavigationTargetAuthorized(url, state)) {
        throw new Error(`Domain ${targetDomain || "(empty)"} is not authorized`);
      }
      if (
        requestedDomain &&
        requestedDomain !== targetDomain &&
        !matchDomain(targetDomain, requestedDomain)
      ) {
        throw new Error(
          `Requested domain ${requestedDomain} does not match navigation target ${targetDomain}`,
        );
      }
      const lookupDomain = requestedDomain || targetDomain;

      let targetTabId = null;
      if (Number.isInteger(tabId) && tabId > 0) {
        const tab = await chrome.tabs.get(tabId);
        if (!isTabAuthorized(tab, state)) {
          throw new Error(`Tab ${tabId} is not authorized`);
        }
        targetTabId = tabId;
      } else if (background) {
        targetTabId = await claimBackgroundTab();
      } else {
        const tab = await findTabForDomain(lookupDomain);
        if (!tab) {
          throw new Error(`No tab found for authorized domain: ${lookupDomain}`);
        }
        targetTabId = tab.id;
      }

      await attachDebugger(targetTabId);
      // The one navigation: a tab claimed for the background is blank until now, so it is never sent to the URL twice.
      const updated = await chrome.tabs.update(targetTabId, background ? { url } : { url, active: true });
      const loaded = await waitForTabLoad(targetTabId, 20000);
      const finalTab = loaded || updated;

      return {
        tabId: targetTabId,
        url: finalTab?.url || url,
        title: finalTab?.title || "",
        domain: extractDomain(finalTab?.url || url),
        active: Boolean(finalTab?.active),
      };
    }

    case "detach_debugger": {
      const { tabId } = payload;
      await detachDebugger(tabId);
      return { success: true };
    }

    default:
      throw new Error(`Unknown action: ${action}`);
  }
}
