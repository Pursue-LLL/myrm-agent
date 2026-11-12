/**
 * The "Myrm Agent" tab group: the visual marker that tells the user which tabs the Agent is working in.
 *
 * [INPUT]
 * - state (POS: queue that serializes group edits)
 * - i18n.js::msg (POS: the group's title in the browser's language)
 * - chrome.tabs / chrome.tabGroups (POS: group membership)
 *
 * [OUTPUT]
 * - addToAgentGroup: put a tab into the window's Agent group, creating the group when the window has none
 *
 * [POS] A marker only, never an access boundary: the policy never reads group membership, and a tab that cannot be
 * grouped (the user ungrouped it, the browser has no tab groups) works exactly the same.
 */

import { msg } from "../i18n.js";
import { state } from "./state.js";

const GROUP_COLOR = "blue";

async function group(tabId) {
  const { windowId } = await chrome.tabs.get(tabId);
  const title = msg("tabGroupTitle");
  const [existing] = await chrome.tabGroups.query({ windowId, title });
  // Pinning the window keeps a new group where the tab is, not in whichever window the browser considers current.
  const groupId = await chrome.tabs.group(
    existing ? { tabIds: tabId, groupId: existing.id } : { tabIds: tabId, createProperties: { windowId } },
  );
  if (!existing) {
    await chrome.tabGroups.update(groupId, { title, color: GROUP_COLOR });
  }
}

export function addToAgentGroup(tabId) {
  // One edit at a time: tabs opened together must find the group the first of them created.
  state.tabGroupQueue = state.tabGroupQueue
    .then(() => group(tabId))
    .catch((error) => console.warn("[Myrm] Could not group the Agent tab:", error));
  return state.tabGroupQueue;
}
