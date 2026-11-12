/**
 * The WebSocket connection to the Myrm Agent server: connect, hello handshake, reconnect with backoff, disconnect.
 *
 * [INPUT]
 * - state (POS: server address, token, live socket, backoff, whether the user wants to stay connected)
 * - server_messages.js::handleServerMessage (POS: inbound messages)
 * - debugger.js::detachAllDebuggers (POS: no tab stays attached without a server)
 * - tabs.js / access_policy.js / clip.js (POS: what the server learns right after the handshake)
 *
 * [OUTPUT]
 * - connect: the user (or the worker's own start-up) wants a connection; open the socket, send `hello`, report tabs, policy and clip target
 * - reconnectIfWanted: reopen the socket unless the user disconnected on purpose
 * - disconnect: the user wants no connection; close the socket, release every debugger and stop all reconnecting
 *
 * [POS] Owner of the connection lifecycle; a socket that closes by itself schedules its own reconnect with exponential
 * backoff, and a disconnect the user asked for is never undone by a timer.
 */

import { msg } from "../i18n.js";
import { sendAccessPolicyUpdate } from "./access_policy.js";
import { syncClipAgentConfig } from "./clip.js";
import { detachAllDebuggers } from "./debugger.js";
import { handleServerMessage } from "./server_messages.js";
import {
  EXTENSION_CAPABILITIES,
  MAX_RECONNECT_DELAY_MS,
  persistConnection,
  RECONNECT_DELAY_MS,
  state,
} from "./state.js";
import { sendTabsUpdate } from "./tabs.js";
import { updateBadge } from "./transport.js";

export function reconnectIfWanted() {
  if (state.autoConnect && state.serverUrl && !state.ws && !state.isConnecting) {
    connect();
  }
}

function scheduleReconnect() {
  setTimeout(reconnectIfWanted, state.reconnectDelay);
  state.reconnectDelay = Math.min(state.reconnectDelay * 1.5, MAX_RECONNECT_DELAY_MS);
}

export function connect() {
  if (state.isConnecting || (state.ws && state.ws.readyState === WebSocket.OPEN)) return;
  if (!state.serverUrl) return;

  if (!state.autoConnect) {
    state.autoConnect = true;
    persistConnection();
  }
  state.isConnecting = true;
  updateBadge("connecting");
  const url = `${state.serverUrl}${state.authToken ? `?token=${encodeURIComponent(state.authToken)}` : ""}`;

  let socket;
  try {
    socket = new WebSocket(url);
  } catch {
    state.isConnecting = false;
    state.lastError = msg("errInvalidWebSocketUrl");
    updateBadge("error");
    return;
  }
  state.ws = socket;

  socket.onopen = () => {
    state.isConnecting = false;
    state.lastError = "";
    state.reconnectDelay = RECONNECT_DELAY_MS;
    updateBadge("connected");

    socket.send(JSON.stringify({
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

  socket.onmessage = async (event) => {
    try {
      await handleServerMessage(JSON.parse(event.data));
    } catch (e) {
      console.error("[Myrm] Failed to handle message:", e);
    }
  };

  socket.onclose = (event) => {
    // A socket the user already replaced or closed on purpose must not undo what replaced it.
    if (state.ws !== socket) return;
    state.ws = null;
    state.isConnecting = false;
    if (!state.lastError) state.lastError = event.reason || msg("errConnectionClosed");
    updateBadge("disconnected");
    detachAllDebuggers();
    scheduleReconnect();
  };

  // A failed socket always closes next, and onclose does the clean-up and schedules the retry.
  socket.onerror = () => {
    state.lastError = msg("errConnectionRefused");
    updateBadge("error");
  };
}

export function disconnect() {
  state.autoConnect = false;
  persistConnection();
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }
  state.isConnecting = false;
  state.lastError = "";
  updateBadge("disconnected");
  detachAllDebuggers();
}
