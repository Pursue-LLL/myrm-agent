/**
 * Outbound channel to the server and the toolbar badge that shows its state.
 *
 * [INPUT]
 * - state (POS: the live WebSocket)
 *
 * [OUTPUT]
 * - isSocketOpen: the server connection is open
 * - send: JSON-encode a message to the server when connected, drop it otherwise
 * - updateBadge: show connected / connecting / disconnected / error on the toolbar icon
 *
 * [POS] The leaf every module that talks to the server depends on; it depends on nothing but `state`.
 */

import { state } from "./state.js";

export function isSocketOpen() {
  return Boolean(state.ws) && state.ws.readyState === WebSocket.OPEN;
}

export function send(message) {
  if (isSocketOpen()) {
    state.ws.send(JSON.stringify(message));
  }
}

export function updateBadge(status) {
  const colors = {
    connected: "#4CAF50",
    connecting: "#F59E0B",
    disconnected: "#9E9E9E",
    error: "#F44336",
  };
  const texts = {
    connected: "ON",
    connecting: "…",
    disconnected: "",
    error: "!",
  };
  chrome.action.setBadgeBackgroundColor({ color: colors[status] || "#9E9E9E" });
  chrome.action.setBadgeText({ text: texts[status] || "" });
}
