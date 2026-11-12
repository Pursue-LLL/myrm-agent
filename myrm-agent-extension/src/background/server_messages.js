/**
 * Dispatch of the messages the server sends over the WebSocket.
 *
 * [INPUT]
 * - access_policy.js / relay.js / actions.js / clip.js / tabs.js / debugger.js (POS: what each message type triggers)
 * - transport.js::send (POS: replies)
 *
 * [OUTPUT]
 * - handleServerMessage: act on one parsed server message (ping, set_domains, set_access_policy, clip_agent_update, relay, request)
 *
 * [POS] The inbound half of the server protocol; failures of relay commands and requests are reported back, never thrown.
 */

import { executeAction } from "./actions.js";
import { applyAccessPolicyPayload, sendAccessPolicyUpdate } from "./access_policy.js";
import { applyClipAgentConfig } from "./clip.js";
import { detachUnauthorizedAttachedTabs } from "./debugger.js";
import { executeRelayCommand } from "./relay.js";
import { persistAccessPolicyLocal, state } from "./state.js";
import { sendTabsUpdate } from "./tabs.js";
import { send } from "./transport.js";

export async function handleServerMessage(message) {
  const { type, id, action, payload, domains } = message;

  if (type === "ping") {
    send({ type: "pong" });
    return;
  }

  if (type === "set_domains") {
    state.authorizedDomains = domains || [];
    await detachUnauthorizedAttachedTabs();
    persistAccessPolicyLocal();
    sendAccessPolicyUpdate();
    return;
  }

  if (type === "set_access_policy") {
    await applyAccessPolicyPayload(message, { notifyServer: false });
    persistAccessPolicyLocal();
    sendTabsUpdate();
    return;
  }

  if (type === "clip_agent_update") {
    applyClipAgentConfig(message.agent_id, message.web_ui_origin);
    return;
  }

  if (type === "relay") {
    try {
      await executeRelayCommand(message.seq, message.command || {});
    } catch (e) {
      send({ type: "relay_error", seq: message.seq, message: e.message || String(e) });
    }
    return;
  }

  if (type === "request") {
    try {
      const result = await executeAction(action, payload || {});
      send({ type: "response", id, data: result });
    } catch (e) {
      send({ type: "response", id, error: e.message });
    }
    return;
  }
}
