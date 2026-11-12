/**
 * Shared runtime state of the service worker and the storage that keeps it across restarts.
 *
 * [INPUT]
 * - chrome.storage.local (POS: settings that outlive a service-worker restart)
 *
 * [OUTPUT]
 * - state: the one mutable object every background module reads and writes
 * - ALARM_NAME / RECONNECT_DELAY_MS / MAX_RECONNECT_DELAY_MS / EXTENSION_CAPABILITIES: connection constants
 * - restoreState: load the persisted settings into `state`
 * - persistAccessPolicyLocal / persistConnection / persistClipTarget / persistBackgroundWindow: write one concern back
 *
 * [POS] Single home of mutable service-worker state, so the modules that act on it stay free of module-level variables.
 */

export const ALARM_NAME = "myrm-keepalive";
export const RECONNECT_DELAY_MS = 3000;
export const MAX_RECONNECT_DELAY_MS = 30000;
export const EXTENSION_CAPABILITIES = Object.freeze([
  "navigate_url",
  "list_tabs",
  "attach_debugger",
  "detach_debugger",
]);

const PERSISTED_KEYS = [
  "serverUrl",
  "authToken",
  "authorizedDomains",
  "allowAllEligibleTabs",
  "pausedTabIds",
  "backgroundWindowId",
  "clipAgentId",
  "webUiOrigin",
];

export const state = {
  ws: null,
  serverUrl: "",
  authToken: "",
  clipAgentId: "",
  webUiOrigin: "",
  reconnectDelay: RECONNECT_DELAY_MS,
  isConnecting: false,
  lastError: "",
  authorizedDomains: [],
  allowAllEligibleTabs: false,
  pausedTabIds: new Set(),
  attachedTabs: new Map(), // tabId -> debugger target
  backgroundWindowId: null, // Isolated background window for non-disruptive automation
  lastClipSuccessUrl: "",
  clipSavedWithoutOrigin: false,
  lastClipErrorKind: "",
};

export async function restoreState() {
  const data = await chrome.storage.local.get(PERSISTED_KEYS);
  state.serverUrl = data.serverUrl || "";
  state.authToken = data.authToken || "";
  state.authorizedDomains = data.authorizedDomains || [];
  state.allowAllEligibleTabs = data.allowAllEligibleTabs === true;
  state.pausedTabIds = new Set(Array.isArray(data.pausedTabIds) ? data.pausedTabIds : []);
  state.backgroundWindowId = data.backgroundWindowId || null;
  state.clipAgentId = data.clipAgentId || "";
  state.webUiOrigin = data.webUiOrigin || "";
}

export function persistAccessPolicyLocal() {
  chrome.storage.local.set({
    authorizedDomains: state.authorizedDomains,
    allowAllEligibleTabs: state.allowAllEligibleTabs,
    pausedTabIds: [...state.pausedTabIds],
  });
}

export function persistConnection() {
  chrome.storage.local.set({ serverUrl: state.serverUrl, authToken: state.authToken });
}

export function persistClipTarget() {
  chrome.storage.local.set({ clipAgentId: state.clipAgentId, webUiOrigin: state.webUiOrigin });
}

export function persistBackgroundWindow() {
  if (state.backgroundWindowId === null) {
    chrome.storage.local.remove("backgroundWindowId");
  } else {
    chrome.storage.local.set({ backgroundWindowId: state.backgroundWindowId });
  }
}
