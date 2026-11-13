/**
 * Applying and reporting the access policy (authorized domains, allow-all, paused tabs).
 *
 * [INPUT]
 * - state (POS: the access policy)
 * - debugger.js::detachUnauthorizedAttachedTabs (POS: a narrower policy takes effect on tabs already attached)
 * - transport.js::send (POS: access_policy_update to the server)
 *
 * [OUTPUT]
 * - applyAccessPolicyPayload: adopt the fields a payload carries, optionally tell the server, then detach what lost access
 * - sendAccessPolicyUpdate: report the current policy to the server; `initial` marks the copy saved before the server
 *   was heard from, which a server that holds a policy of its own does not adopt
 *
 * [POS] The one path through which a policy change from the server, the popup or the settings page takes effect.
 */

import { detachUnauthorizedAttachedTabs } from "./debugger.js";
import { state } from "./state.js";
import { send } from "./transport.js";

export function sendAccessPolicyUpdate({ initial = false } = {}) {
  send({
    type: "access_policy_update",
    allow_all_eligible_tabs: state.allowAllEligibleTabs,
    domains: state.authorizedDomains,
    paused_tab_ids: [...state.pausedTabIds],
    initial,
  });
}

export async function applyAccessPolicyPayload(payload, { notifyServer = true } = {}) {
  if ("allow_all_eligible_tabs" in payload) {
    state.allowAllEligibleTabs = payload.allow_all_eligible_tabs === true;
  }
  if (Array.isArray(payload.domains)) {
    state.authorizedDomains = payload.domains.map((item) => String(item).trim()).filter(Boolean);
  }
  if (Array.isArray(payload.paused_tab_ids)) {
    state.pausedTabIds = new Set(
      payload.paused_tab_ids.map((item) => Number.parseInt(String(item), 10)).filter((item) => Number.isInteger(item)),
    );
  }
  if (notifyServer) {
    sendAccessPolicyUpdate();
  }
  await detachUnauthorizedAttachedTabs();
}
