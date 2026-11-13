/**
 * Shared runtime state of the service worker and the storage that keeps it across restarts.
 *
 * [INPUT]
 * - chrome.storage.local (POS: settings that outlive a browser restart)
 * - chrome.storage.session (POS: Agent tab ownership, which outlives a service-worker restart but not the browser session)
 *
 * [OUTPUT]
 * - state: the one mutable object every background module reads and writes
 * - ALARM_NAME / RECONNECT_DELAY_MS / MAX_RECONNECT_DELAY_MS / EXTENSION_CAPABILITIES: connection constants
 * - whenRestored: resolves once the persisted state is loaded into `state`; every entry point awaits it
 * - persistAccessPolicyLocal / persistConnection / persistClipTarget / persistBackgroundWindow / persistAgentTabs: write one concern back
 *
 * [POS] Single home of mutable service-worker state, so the modules that act on it stay free of module-level variables.
 * The browser may stop the worker at any time and start a fresh one with an empty `state`; this is how it gets refilled.
 */

export const ALARM_NAME = "myrm-keepalive";
export const KEEP_ALIVE_PERIOD_MINUTES = 0.5;
export const RECONNECT_DELAY_MS = 3000;
export const MAX_RECONNECT_DELAY_MS = 30000;
export const EXTENSION_CAPABILITIES = Object.freeze([
  "navigate_url",
  "list_tabs",
  "attach_debugger",
  "detach_debugger",
  "agent_tab_control",
]);

const PERSISTED_KEYS = [
  "serverUrl",
  "authToken",
  "autoConnect",
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
  autoConnect: true, // false once the user disconnects: no timer may reconnect until they connect again
  clipAgentId: "",
  webUiOrigin: "",
  reconnectDelay: RECONNECT_DELAY_MS,
  isConnecting: false,
  lastError: "",
  /** @type {string[]} */
  authorizedDomains: [],
  allowAllEligibleTabs: false,
  pausedTabIds: new Set(),
  attachedTabs: new Map(), // tabId -> debugger target id
  agentTabIds: new Set(), // tabs the Agent opened itself, or whose page it opened
  agentTabOpeners: new Map(), // tab -> the Agent tab whose page opened it; only needed while the page is new, so not persisted
  tabGroupQueue: Promise.resolve(), // serializes tab-group edits so concurrent tabs share one group
  backgroundWindowId: null, // Isolated background window for non-disruptive automation
  backgroundWindowOpening: null, // in-flight creation of that window, shared by concurrent callers
  lastClipSuccessUrl: "",
  clipSavedWithoutOrigin: false,
  lastClipErrorKind: "",
};

async function restoreState() {
  const [data, session] = await Promise.all([
    chrome.storage.local.get(PERSISTED_KEYS),
    chrome.storage.session.get("agentTabIds"),
  ]);
  state.serverUrl = data.serverUrl || "";
  state.authToken = data.authToken || "";
  state.autoConnect = data.autoConnect !== false;
  state.authorizedDomains = data.authorizedDomains || [];
  state.allowAllEligibleTabs = data.allowAllEligibleTabs === true;
  state.pausedTabIds = new Set(Array.isArray(data.pausedTabIds) ? data.pausedTabIds : []);
  state.backgroundWindowId = data.backgroundWindowId || null;
  state.clipAgentId = data.clipAgentId || "";
  state.webUiOrigin = data.webUiOrigin || "";
  state.agentTabIds = new Set(Array.isArray(session.agentTabIds) ? session.agentTabIds : []);
}

let restoring = null;

export function whenRestored() {
  restoring ??= restoreState();
  return restoring;
}

export function persistAccessPolicyLocal() {
  chrome.storage.local.set({
    authorizedDomains: state.authorizedDomains,
    allowAllEligibleTabs: state.allowAllEligibleTabs,
    pausedTabIds: [...state.pausedTabIds],
  });
}

export function persistConnection() {
  chrome.storage.local.set({
    serverUrl: state.serverUrl,
    authToken: state.authToken,
    autoConnect: state.autoConnect,
  });
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

export function persistAgentTabs() {
  chrome.storage.session.set({ agentTabIds: [...state.agentTabIds] });
}
