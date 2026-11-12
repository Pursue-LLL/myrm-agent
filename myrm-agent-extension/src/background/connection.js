/**
 * The WebSocket connection to the Myrm Agent server: connect, hello handshake, reconnect with backoff, disconnect.
 *
 * [INPUT]
 * - state (POS: server address, token, live socket, backoff)
 * - server_messages.js::handleServerMessage (POS: inbound messages)
 * - debugger.js::detachAllDebuggers (POS: no tab stays attached without a server)
 * - tabs.js / access_policy.js / clip.js (POS: what the server learns right after the handshake)
 *
 * [OUTPUT]
 * - connect: open the socket, send `hello`, report tabs, policy and clip target
 * - disconnect: close the socket and release every debugger
 *
 * [POS] Owner of the connection lifecycle; a closed socket schedules its own reconnect with exponential backoff.
 */

import { msg } from "../i18n.js";
import { sendAccessPolicyUpdate } from "./access_policy.js";
import { syncClipAgentConfig } from "./clip.js";
import { detachAllDebuggers } from "./debugger.js";
import { handleServerMessage } from "./server_messages.js";
import { EXTENSION_CAPABILITIES, MAX_RECONNECT_DELAY_MS, RECONNECT_DELAY_MS, state } from "./state.js";
import { sendTabsUpdate } from "./tabs.js";
import { updateBadge } from "./transport.js";

function scheduleReconnect() {
  setTimeout(() => {
    if (!state.ws && state.serverUrl) connect();
  }, state.reconnectDelay);
  state.reconnectDelay = Math.min(state.reconnectDelay * 1.5, MAX_RECONNECT_DELAY_MS);
}

export function connect() {
  if (state.isConnecting || (state.ws && state.ws.readyState === WebSocket.OPEN)) return;
  if (!state.serverUrl) return;

  state.isConnecting = true;
  updateBadge("connecting");
  const url = `${state.serverUrl}${state.authToken ? `?token=${encodeURIComponent(state.authToken)}` : ""}`;

  try {
    state.ws = new WebSocket(url);
  } catch {
    state.isConnecting = false;
    state.lastError = msg("errInvalidWebSocketUrl");
    updateBadge("error");
    return;
  }

  state.ws.onopen = () => {
    state.isConnecting = false;
    state.lastError = "";
    state.reconnectDelay = RECONNECT_DELAY_MS;
    updateBadge("connected");

    state.ws.send(JSON.stringify({
      type: "hello",
      version: chrome.runtime.getManifest().version,
      browser: navigator.userAgent.includes("Edg/") ? "Edge" : "Chrome",
      userAgent: navigator.userAgent,
      browserVersion: navigator.userAgent.match(/Chrome\/[\d.]+|Edg\/[\d.]+/)?.[0] || "Chrome/unknown",
      capabilities: EXTENSION_CAPABILITIES,
    }));

    sendTabsUpdate();
    sendAccessPolicyUpdate();
    syncClipAgentConfig();
  };

  state.ws.onmessage = async (event) => {
    try {
      await handleServerMessage(JSON.parse(event.data));
    } catch (e) {
      console.error("[Myrm] Failed to handle message:", e);
    }
  };

  state.ws.onclose = (event) => {
    state.ws = null;
    state.isConnecting = false;
    if (!state.lastError) state.lastError = event.reason || msg("errConnectionClosed");
    updateBadge("disconnected");
    detachAllDebuggers();
    scheduleReconnect();
  };

  state.ws.onerror = () => {
    state.ws = null;
    state.isConnecting = false;
    state.lastError = msg("errConnectionRefused");
    updateBadge("error");
  };
}

export function disconnect() {
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }
  state.lastError = "";
  updateBadge("disconnected");
  detachAllDebuggers();
}
