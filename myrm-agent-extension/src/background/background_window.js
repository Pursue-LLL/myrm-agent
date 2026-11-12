/**
 * The isolated browser window the Agent uses for work that must not disturb the user's own tabs.
 *
 * [INPUT]
 * - state (POS: id of the background window)
 * - policy.js::isBlankUrl (POS: which of the window's tabs are unused)
 * - chrome.windows / chrome.tabs (POS: window and tab lifecycle)
 *
 * [OUTPUT]
 * - ensureBackgroundWindow: id of the live background window, created unfocused when missing
 * - cleanupBackgroundTabs: close the window's tabs that carry content
 *
 * [POS] Background-window lifecycle; forgets the window when the user closes it. Which of its tabs the Agent
 * owns is agent_tabs.js's business.
 */

import { isBlankUrl } from "./policy.js";
import { persistBackgroundWindow, state } from "./state.js";

async function openBackgroundWindow() {
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

export function ensureBackgroundWindow() {
  // Callers that arrive while the window is being opened wait for it instead of opening another.
  state.backgroundWindowOpening ??= openBackgroundWindow().finally(() => {
    state.backgroundWindowOpening = null;
  });
  return state.backgroundWindowOpening;
}

export function cleanupBackgroundTabs() {
  if (state.backgroundWindowId === null) return;
  chrome.tabs.query({ windowId: state.backgroundWindowId }, (tabs) => {
    for (const tab of tabs) {
      if (!isBlankUrl(tab.url)) {
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
