/**
 * The isolated browser window the Agent uses for work that must not disturb the user's own tabs.
 *
 * [INPUT]
 * - state (POS: id of the background window)
 * - chrome.windows / chrome.tabs (POS: window and tab lifecycle)
 *
 * [OUTPUT]
 * - ensureBackgroundWindow: id of the live background window, created unfocused when missing
 * - getOrCreateBackgroundTab: a tab in that window, reusing a blank one
 * - cleanupBackgroundTabs: close the window's tabs that carry content
 *
 * [POS] Background-window lifecycle; forgets the window when the user closes it.
 */

import { persistBackgroundWindow, state } from "./state.js";

export async function ensureBackgroundWindow() {
  if (state.backgroundWindowId !== null) {
    try {
      await chrome.windows.get(state.backgroundWindowId);
      return state.backgroundWindowId;
    } catch {
      state.backgroundWindowId = null;
    }
  }

  const win = await chrome.windows.create({
    focused: false,
    width: 1280,
    height: 900,
    type: "normal",
    url: "about:blank",
  });
  state.backgroundWindowId = win.id;
  persistBackgroundWindow();
  return state.backgroundWindowId;
}

export async function getOrCreateBackgroundTab(url) {
  const windowId = await ensureBackgroundWindow();
  const tabs = await chrome.tabs.query({ windowId });

  // Reuse existing blank tab if available
  const blankTab = tabs.find((t) => !t.url || t.url === "about:blank" || t.url === "chrome://newtab/");
  if (blankTab) {
    if (url && url !== "about:blank") {
      await chrome.tabs.update(blankTab.id, { url });
    }
    return blankTab.id;
  }

  const newTab = await chrome.tabs.create({ windowId, url: url || "about:blank", active: false });
  return newTab.id;
}

export function cleanupBackgroundTabs() {
  if (state.backgroundWindowId === null) return;
  chrome.tabs.query({ windowId: state.backgroundWindowId }, (tabs) => {
    for (const tab of tabs) {
      if (tab.url && tab.url !== "about:blank" && tab.url !== "chrome://newtab/") {
        chrome.tabs.remove(tab.id).catch(() => {});
      }
    }
  });
}

chrome.windows.onRemoved.addListener((windowId) => {
  if (windowId === state.backgroundWindowId) {
    state.backgroundWindowId = null;
    persistBackgroundWindow();
  }
});
