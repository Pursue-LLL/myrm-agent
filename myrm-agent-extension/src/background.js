/**
 * Myrm Agent Extension — Background Service Worker (MV3)
 *
 * Maintains a persistent WebSocket connection to the Myrm Agent Server,
 * handles CDP proxy requests, manages tab lifecycle, context menus,
 * keyboard shortcuts, and Side Panel ↔ content script communication.
 */

import {
  buildClipRawUrl,
  buildDuplicateReviewUrl,
  buildWikiIgnoreUrl,
  wikiHttpBaseFromServerUrl,
} from "./wiki/deep_links.js";
import { submitClipToWiki as runClipToWiki } from "./wiki/clip_client.js";
import { notifyClipOutcome } from "./wiki/clip_notify.js";
import { msg } from "./i18n.js";

const ALARM_NAME = "myrm-keepalive";
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_DELAY_MS = 30000;
const EXTENSION_CAPABILITIES = Object.freeze([
  "navigate_url",
  "list_tabs",
  "attach_debugger",
  "detach_debugger",
]);

let ws = null;
let serverUrl = "";
let authToken = "";
let clipAgentId = "";
let webUiOrigin = "";
let reconnectDelay = RECONNECT_DELAY_MS;
let isConnecting = false;
let lastError = "";
let authorizedDomains = [];
let allowAllEligibleTabs = false;
let pausedTabIds = new Set();
let attachedTabs = new Map(); // tabId -> debugger target
let backgroundWindowId = null; // Isolated background window for non-disruptive automation
let lastClipSuccessUrl = "";
let clipSavedWithoutOrigin = false;
let lastClipErrorKind = "";

// --- Lifecycle ---

function restoreState() {
  chrome.storage.local.get(
    ["serverUrl", "authToken", "authorizedDomains", "allowAllEligibleTabs", "pausedTabIds", "backgroundWindowId", "clipAgentId", "webUiOrigin"],
    (data) => {
    serverUrl = data.serverUrl || "";
    authToken = data.authToken || "";
    authorizedDomains = data.authorizedDomains || [];
    allowAllEligibleTabs = data.allowAllEligibleTabs === true;
    pausedTabIds = new Set(Array.isArray(data.pausedTabIds) ? data.pausedTabIds : []);
    backgroundWindowId = data.backgroundWindowId || null;
    clipAgentId = data.clipAgentId || "";
    webUiOrigin = data.webUiOrigin || "";
    if (serverUrl) connect();
  });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: 0.4 });
  setupContextMenu();
  restoreState();
});

chrome.runtime.onStartup.addListener(() => {
  setupContextMenu();
  restoreState();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    if (!ws && serverUrl && !isConnecting) {
      connect();
    }
  }
});

// --- Wiki clip config sync ---

function applyClipAgentConfig(agentId, origin) {
  clipAgentId = agentId || "";
  webUiOrigin = origin || "";
  if (webUiOrigin) {
    clipSavedWithoutOrigin = false;
  }
  chrome.storage.local.set({ clipAgentId, webUiOrigin });
}

async function syncClipAgentConfig() {
  const httpBase = wikiHttpBaseFromServerUrl(serverUrl);
  if (!httpBase) return;
  try {
    const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
    const resp = await fetch(`${httpBase.replace(/\/$/, "")}/api/v1/extension/clip-agent`, { headers });
    if (!resp.ok) return;
    const data = await resp.json();
    applyClipAgentConfig(data.agent_id, data.web_ui_origin);
  } catch (_) {
    // Non-fatal: clip falls back to default vault when sync fails.
  }
}

// --- WebSocket Connection ---

function connect() {
  if (isConnecting || (ws && ws.readyState === WebSocket.OPEN)) return;
  if (!serverUrl) return;

  isConnecting = true;
  updateBadge("connecting");
  const url = `${serverUrl}${authToken ? `?token=${encodeURIComponent(authToken)}` : ""}`;

  try {
    ws = new WebSocket(url);
  } catch (e) {
    isConnecting = false;
    lastError = msg("errInvalidWebSocketUrl");
    updateBadge("error");
    return;
  }

  ws.onopen = () => {
    isConnecting = false;
    lastError = "";
    reconnectDelay = RECONNECT_DELAY_MS;
    updateBadge("connected");

    ws.send(JSON.stringify({
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

  ws.onmessage = async (event) => {
    try {
      const msg = JSON.parse(event.data);
      await handleServerMessage(msg);
    } catch (e) {
      console.error("[Myrm] Failed to handle message:", e);
    }
  };

  ws.onclose = (event) => {
    ws = null;
    isConnecting = false;
    if (!lastError) lastError = event.reason || msg("errConnectionClosed");
    updateBadge("disconnected");
    detachAllDebuggers();
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws = null;
    isConnecting = false;
    lastError = msg("errConnectionRefused");
    updateBadge("error");
  };
}

function disconnect() {
  if (ws) {
    ws.close();
    ws = null;
  }
  lastError = "";
  updateBadge("disconnected");
  detachAllDebuggers();
}

function scheduleReconnect() {
  setTimeout(() => {
    if (!ws && serverUrl) connect();
  }, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_RECONNECT_DELAY_MS);
}

// --- Message Handling ---

async function handleServerMessage(msg) {
  const { type, id, action, payload, domains } = msg;

  if (type === "ping") {
    send({ type: "pong" });
    return;
  }

  if (type === "set_domains") {
    authorizedDomains = domains || [];
    await detachUnauthorizedAttachedTabs();
    persistAccessPolicyLocal();
    sendAccessPolicyUpdate();
    return;
  }

  if (type === "set_access_policy") {
    await applyAccessPolicyPayload(msg, { notifyServer: false });
    persistAccessPolicyLocal();
    sendTabsUpdate();
    return;
  }

  if (type === "clip_agent_update") {
    applyClipAgentConfig(msg.agent_id, msg.web_ui_origin);
    return;
  }

  if (type === "relay") {
    try {
      await executeRelayCommand(msg.seq, msg.command || {});
    } catch (e) {
      send({ type: "relay_error", seq: msg.seq, message: e.message || String(e) });
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

async function executeRelayCommand(seq, command) {
  if (!Number.isInteger(seq)) {
    throw new Error("relay command requires integer seq");
  }
  switch (command.type) {
    case "attach": {
      const tabId = command.tabId;
      if (!Number.isInteger(tabId)) {
        throw new Error("attach requires tabId");
      }
      await assertRelayTabAuthorized(tabId);
      const result = await attachDebugger(tabId);
      send({ type: "relay_result", seq, result });
      return;
    }
    case "detach": {
      const tabId = command.tabId;
      if (Number.isInteger(tabId)) {
        await detachDebugger(tabId);
      }
      send({ type: "relay_result", seq, result: {} });
      return;
    }
    case "cdp": {
      const tabId = command.tabId;
      const method = command.method;
      if (!Number.isInteger(tabId) || typeof method !== "string") {
        throw new Error("cdp requires tabId and method");
      }
      assertRelayCdpNavigateAuthorized(method, command.params);
      await assertRelayTabAuthorized(tabId);
      if (!attachedTabs.has(tabId)) {
        await attachDebugger(tabId);
      }
      const target = command.sessionId
        ? { tabId, sessionId: command.sessionId }
        : { tabId };
      const result = await chrome.debugger.sendCommand(
        target,
        method,
        command.params || {},
      );
      send({ type: "relay_result", seq, result: result ?? {} });
      return;
    }
    case "createTab": {
      const url = typeof command.url === "string" && command.url ? command.url : "about:blank";
      const targetDomain = extractDomain(url).toLowerCase();
      if (targetDomain && !isNavigationTargetAuthorized(url)) {
        throw new Error(`Domain ${targetDomain} is not authorized`);
      }
      const background = command.background === true;
      let tabId;
      if (background) {
        tabId = await getOrCreateBackgroundTab(url);
      } else {
        const created = await chrome.tabs.create({ url, active: true });
        tabId = created.id;
      }
      if (!Number.isInteger(tabId)) {
        throw new Error("createTab failed to allocate tabId");
      }
      send({ type: "relay_result", seq, result: { tabId } });
      return;
    }
    default:
      throw new Error(`unknown relay command: ${command.type || "(missing)"}`);
  }
}

async function executeAction(action, payload) {
  switch (action) {
    case "list_tabs":
      return await getAuthorizedTabs();

    case "attach_debugger": {
      const { domain, tabId, background = false } = payload;

      // Explicit tab targeting bypasses background isolation
      if (tabId) {
        const tabs = await chrome.tabs.query({});
        const target = tabs.find((t) => t.id === tabId && isTabAuthorized(t));
        if (!target) {
          throw new Error(`Tab ${tabId} not found or not authorized`);
        }
        return await attachDebugger(tabId);
      }

      // Background mode: create/reuse isolated window to avoid disrupting user
      if (background && domain) {
        const url = `https://${domain}`;
        const bgTabId = await getOrCreateBackgroundTab(url);
        return await attachDebugger(bgTabId);
      }

      // Foreground fallback: operate on existing user tab
      const tab = await findTabForDomain(domain);
      if (!tab) {
        throw new Error(`No tab found for domain: ${domain || "(any authorized)"}`);
      }
      return await attachDebugger(tab.id);
    }

    case "navigate_url": {
      const { url, domain, tabId, background = true } = payload;
      if (!url || typeof url !== "string") {
        throw new Error("navigate_url requires a valid url");
      }

      const targetDomain = extractDomain(url).toLowerCase();
      const requestedDomain = (domain || "").toLowerCase();
      if (!targetDomain || !isNavigationTargetAuthorized(url)) {
        throw new Error(`Domain ${targetDomain || "(empty)"} is not authorized`);
      }
      if (
        requestedDomain &&
        requestedDomain !== targetDomain &&
        !matchDomain(targetDomain, requestedDomain)
      ) {
        throw new Error(
          `Requested domain ${requestedDomain} does not match navigation target ${targetDomain}`,
        );
      }
      const lookupDomain = requestedDomain || targetDomain;

      let targetTabId = null;
      if (Number.isInteger(tabId) && tabId > 0) {
        const tab = await chrome.tabs.get(tabId);
        if (!isTabAuthorized(tab)) {
          throw new Error(`Tab ${tabId} is not authorized`);
        }
        targetTabId = tabId;
      } else if (background) {
        targetTabId = await getOrCreateBackgroundTab(url);
      } else {
        const tab = await findTabForDomain(lookupDomain);
        if (!tab) {
          throw new Error(`No tab found for authorized domain: ${lookupDomain}`);
        }
        targetTabId = tab.id;
      }

      await attachDebugger(targetTabId);
      const updated = await chrome.tabs.update(targetTabId, {
        url,
        active: !background,
      });
      const loaded = await waitForTabLoad(targetTabId, 20000);
      const finalTab = loaded || updated;

      return {
        tabId: targetTabId,
        url: finalTab?.url || url,
        title: finalTab?.title || "",
        domain: extractDomain(finalTab?.url || url),
        active: Boolean(finalTab?.active),
      };
    }

    case "detach_debugger": {
      const { tabId } = payload;
      await detachDebugger(tabId);
      return { success: true };
    }

    default:
      throw new Error(`Unknown action: ${action}`);
  }
}

// --- Tab Management ---

async function getAuthorizedTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs
    .filter((tab) => isTabAuthorized(tab))
    .map((tab) => ({
      id: tab.id,
      url: tab.url || "",
      title: tab.title || "",
      domain: extractDomain(tab.url || ""),
      active: tab.active,
    }));
}

async function getListableTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs
    .filter((tab) => isTabEligibleForPolicy(tab))
    .map((tab) => ({
      id: tab.id,
      url: tab.url || "",
      title: tab.title || "",
      domain: extractDomain(tab.url || ""),
      active: tab.active,
    }));
}

async function findTabForDomain(domain) {
  const tabs = await chrome.tabs.query({});
  const authorized = tabs.filter((tab) => isTabAuthorized(tab));

  if (domain) {
    const matching = authorized.filter((tab) => extractDomain(tab.url || "") === domain);
    return matching.find((tab) => tab.active) || matching[0] || null;
  }

  return authorized.find((tab) => tab.active) || authorized[0] || null;
}

async function waitForTabLoad(tabId, timeoutMs = 20000) {
  return await new Promise((resolve) => {
    let done = false;
    const finish = (tab) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      resolve(tab || null);
    };

    const onUpdated = (updatedTabId, changeInfo, tab) => {
      if (updatedTabId !== tabId) return;
      if (changeInfo.status === "complete") {
        finish(tab);
      }
    };

    const timer = setTimeout(async () => {
      try {
        const tab = await chrome.tabs.get(tabId);
        finish(tab);
      } catch {
        finish(null);
      }
    }, timeoutMs);

    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}

const RELAY_CDP_NAVIGATE_METHODS = new Set(["Page.navigate"]);

function isInternalBrowserUrl(url) {
  const trimmed = (url || "").trim();
  if (!trimmed) return true;
  const lowered = trimmed.toLowerCase();
  if (lowered === "about:blank" || lowered === "about:newtab") return false;
  return (
    lowered.startsWith("chrome://")
    || lowered.startsWith("chrome-extension://")
    || lowered.startsWith("devtools://")
    || lowered.startsWith("edge://")
    || lowered.startsWith("brave://")
  );
}

function isEligibleHttpUrl(url) {
  const trimmed = (url || "").trim();
  if (!trimmed || isInternalBrowserUrl(trimmed)) return false;
  try {
    const parsed = new URL(trimmed);
    const scheme = (parsed.protocol || "").replace(":", "").toLowerCase();
    if (!["http", "https", "file"].includes(scheme)) return false;
    return Boolean(parsed.hostname) || scheme === "file";
  } catch {
    return false;
  }
}

async function applyAccessPolicyPayload(payload, { notifyServer = true } = {}) {
  if ("allow_all_eligible_tabs" in payload) {
    allowAllEligibleTabs = payload.allow_all_eligible_tabs === true;
  }
  if (Array.isArray(payload.domains)) {
    authorizedDomains = payload.domains.map((item) => String(item).trim()).filter(Boolean);
  }
  if (Array.isArray(payload.paused_tab_ids)) {
    pausedTabIds = new Set(
      payload.paused_tab_ids
        .map((item) => Number.parseInt(String(item), 10))
        .filter((item) => Number.isInteger(item)),
    );
  }
  if (notifyServer) {
    sendAccessPolicyUpdate();
  }
  await detachUnauthorizedAttachedTabs();
}

function persistAccessPolicyLocal() {
  chrome.storage.local.set({
    authorizedDomains,
    allowAllEligibleTabs,
    pausedTabIds: [...pausedTabIds],
  });
}

function sendAccessPolicyUpdate() {
  send({
    type: "access_policy_update",
    allow_all_eligible_tabs: allowAllEligibleTabs,
    domains: authorizedDomains,
    paused_tab_ids: [...pausedTabIds],
  });
}

function assertRelayCdpNavigateAuthorized(method, params) {
  if (!RELAY_CDP_NAVIGATE_METHODS.has(method)) {
    return;
  }
  const rawParams = params && typeof params === "object" ? params : {};
  const url = typeof rawParams.url === "string" ? rawParams.url : "";
  if (!url) {
    return;
  }
  if (!isNavigationTargetAuthorized(url)) {
    const targetDomain = extractDomain(url).toLowerCase();
    throw new Error(`Domain ${targetDomain || "(empty)"} is not authorized`);
  }
}

async function assertRelayTabAuthorized(tabId) {
  const tab = await chrome.tabs.get(tabId);
  if (!isTabAuthorized(tab)) {
    throw new Error(`Tab ${tabId} is not authorized`);
  }
}

function isTabAuthorized(tab) {
  if (!tab || !Number.isInteger(tab.id)) return false;
  if (pausedTabIds.has(tab.id)) return false;
  return isTabEligibleForPolicy(tab);
}

function isTabEligibleForPolicy(tab) {
  if (!tab || !Number.isInteger(tab.id)) return false;
  const url = tab.url || "";
  if (isInternalBrowserUrl(url)) return false;
  if (allowAllEligibleTabs) {
    return isEligibleHttpUrl(url);
  }
  if (!authorizedDomains.length) return false;
  const domain = extractDomain(url);
  return isDomainAuthorized(domain);
}

function isNavigationTargetAuthorized(url) {
  if (isInternalBrowserUrl(url)) return false;
  if (allowAllEligibleTabs) {
    return isEligibleHttpUrl(url);
  }
  if (!authorizedDomains.length) return false;
  const domain = extractDomain(url).toLowerCase();
  return domain ? isDomainAuthorized(domain) : false;
}

function isDomainAuthorized(domain) {
  return authorizedDomains.some((pattern) => matchDomain(domain, pattern));
}

function matchDomain(domain, pattern) {
  if (pattern.startsWith("*.")) {
    const suffix = pattern.slice(2);
    return domain === suffix || domain.endsWith("." + suffix);
  }
  return domain === pattern;
}

function extractDomain(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

function sendTabsUpdate() {
  getListableTabs().then((tabs) => {
    send({ type: "tabs_update", tabs });
  });
}

chrome.tabs.onUpdated.addListener((_tabId, changeInfo) => {
  if (changeInfo.url || changeInfo.status === "complete") {
    sendTabsUpdate();
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (attachedTabs.has(tabId)) {
    attachedTabs.delete(tabId);
  }
  let pauseChanged = false;
  if (pausedTabIds.has(tabId)) {
    pausedTabIds.delete(tabId);
    pauseChanged = true;
  }
  if (pauseChanged) {
    persistAccessPolicyLocal();
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendAccessPolicyUpdate();
    }
  }
  sendTabsUpdate();
});

// --- Background Window Isolation ---

async function ensureBackgroundWindow() {
  if (backgroundWindowId !== null) {
    try {
      await chrome.windows.get(backgroundWindowId);
      return backgroundWindowId;
    } catch {
      backgroundWindowId = null;
    }
  }

  const win = await chrome.windows.create({
    focused: false,
    width: 1280,
    height: 900,
    type: "normal",
    url: "about:blank",
  });
  backgroundWindowId = win.id;
  chrome.storage.local.set({ backgroundWindowId });
  return backgroundWindowId;
}

async function getOrCreateBackgroundTab(url) {
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

chrome.windows.onRemoved.addListener((windowId) => {
  if (windowId === backgroundWindowId) {
    backgroundWindowId = null;
    chrome.storage.local.remove("backgroundWindowId");
  }
});

// --- Debugger Management ---

async function attachDebugger(tabId) {
  const target = { tabId };

  if (!attachedTabs.has(tabId)) {
    await chrome.debugger.attach(target, "1.3");
    attachedTabs.set(tabId, target);
  }

  return { attached: true, tabId, targetId: `tab-${tabId}` };
}

async function detachUnauthorizedAttachedTabs() {
  for (const tabId of [...attachedTabs.keys()]) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (!isTabAuthorized(tab)) {
        await detachDebugger(tabId);
      }
    } catch {
      await detachDebugger(tabId);
    }
  }
}

async function detachDebugger(tabId) {
  if (attachedTabs.has(tabId)) {
    try {
      await chrome.debugger.detach({ tabId });
    } catch {
      // Tab may already be closed
    }
    attachedTabs.delete(tabId);

    // Close tab in background window to prevent accumulation
    if (backgroundWindowId !== null) {
      try {
        const tab = await chrome.tabs.get(tabId);
        if (tab.windowId === backgroundWindowId) {
          await chrome.tabs.remove(tabId);
        }
      } catch {
        // Tab already closed
      }
    }
  }
}

function detachAllDebuggers() {
  for (const [tabId] of attachedTabs) {
    chrome.debugger.detach({ tabId }).catch(() => {});
  }
  attachedTabs.clear();
  cleanupBackgroundTabs();
}

function cleanupBackgroundTabs() {
  if (backgroundWindowId === null) return;
  chrome.tabs.query({ windowId: backgroundWindowId }, (tabs) => {
    for (const tab of tabs) {
      if (tab.url && tab.url !== "about:blank" && tab.url !== "chrome://newtab/") {
        chrome.tabs.remove(tab.id).catch(() => {});
      }
    }
  });
}

// --- Chrome Debugger Events ---

chrome.debugger.onEvent.addListener((source, method, params) => {
  if (!source.tabId || !attachedTabs.has(source.tabId)) {
    return;
  }
  send({
    type: "cdp_event",
    tabId: source.tabId,
    sessionId: source.sessionId || undefined,
    method,
    params: params || {},
  });
});

chrome.debugger.onDetach.addListener((source, reason) => {
  if (source.tabId && attachedTabs.has(source.tabId)) {
    attachedTabs.delete(source.tabId);
    send({
      type: "debugger_detached",
      tabId: source.tabId,
      reason,
    });
  }
});

// --- Utility ---

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

function updateBadge(status) {
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

// --- Wiki clip (extension → server REST, zero LLM) ---

async function submitClipToWiki(tab, mode) {
  const result = await runClipToWiki(tab, mode, { serverUrl, authToken, clipAgentId });
  if (result.ok) {
    lastError = "";
    lastClipErrorKind = "";
    lastClipSuccessUrl = buildClipRawUrl(webUiOrigin, clipAgentId, result.relative_path || "");
    clipSavedWithoutOrigin = !webUiOrigin.trim();
    chrome.action.setBadgeText({ text: "OK" });
    setTimeout(() => updateBadge(ws && ws.readyState === WebSocket.OPEN ? "connected" : "disconnected"), 2000);
    if (clipSavedWithoutOrigin) {
      void notifyClipOutcome("success_no_origin");
    } else {
      void notifyClipOutcome("success", { openUrl: lastClipSuccessUrl });
    }
    return;
  }
  lastClipSuccessUrl = "";
  clipSavedWithoutOrigin = false;
  lastClipErrorKind = result.conflict ? "duplicate" : result.security_blocked ? "security" : "generic";
  lastError = result.error || msg("errClipFailed");
  if (result.conflict) {
    void notifyClipOutcome("duplicate", {
      openUrl: buildDuplicateReviewUrl(webUiOrigin, clipAgentId),
    });
  } else if (result.security_blocked) {
    void notifyClipOutcome("security", {
      openUrl: buildWikiIgnoreUrl(webUiOrigin, clipAgentId),
    });
  } else {
    void notifyClipOutcome("error", { errorMessage: lastError });
    updateBadge("error");
  }
}

// --- Context Menu + Keyboard Shortcut + Glow ---

function setupContextMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "ask-myrm-agent", title: msg("ctxAskMyrmAgent"), contexts: ["selection"] });
    chrome.contextMenus.create({ id: "ask-myrm-agent-page", title: msg("ctxAskMyrmAgentPage"), contexts: ["page"] });
    chrome.contextMenus.create({ id: "clip-wiki-selection", title: msg("ctxClipWikiSelection"), contexts: ["selection"] });
    chrome.contextMenus.create({ id: "clip-wiki-page", title: msg("ctxClipWikiPage"), contexts: ["page"] });
  });
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab?.id) return;
  if (info.menuItemId === "clip-wiki-selection") {
    submitClipToWiki(tab, "selection");
    return;
  }
  if (info.menuItemId === "clip-wiki-page") {
    submitClipToWiki(tab, "full_page");
    return;
  }
  if (info.menuItemId === "ask-myrm-agent" && info.selectionText) {
    chrome.sidePanel.open({ tabId: tab.id }).then(() => {
      setTimeout(() => {
        chrome.runtime.sendMessage({
          type: "context_menu_query", text: info.selectionText,
          prompt: "", url: tab.url, title: tab.title,
        }).catch(() => {});
      }, 300);
    }).catch(() => {});
  }
  if (info.menuItemId === "ask-myrm-agent-page") {
    chrome.sidePanel.open({ tabId: tab.id }).catch(() => {});
  }
});

chrome.commands.onCommand.addListener((command) => {
  if (command === "toggle-sidepanel") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) chrome.sidePanel.open({ tabId: tabs[0].id }).catch(() => {});
    });
  }
});

function sendGlowToTab(tabId, active) {
  chrome.tabs.sendMessage(tabId, { type: "glow", active }).catch(() => {
    if (active) {
      chrome.scripting.executeScript({ target: { tabId }, files: ["src/content/glow.js"] }).catch(() => {});
      setTimeout(() => chrome.tabs.sendMessage(tabId, { type: "glow", active }).catch(() => {}), 200);
    }
  });
}

// --- External Message API (for popup and side panel) ---

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "get_status") {
    sendResponse({
      connected: ws && ws.readyState === WebSocket.OPEN,
      connecting: isConnecting,
      lastError,
      lastClipErrorKind,
      serverUrl,
      authorizedDomains,
      attachedTabs: Array.from(attachedTabs.keys()),
      capabilities: Array.from(EXTENSION_CAPABILITIES),
      clipAgentId,
      webUiOrigin,
      duplicateReviewUrl: buildDuplicateReviewUrl(webUiOrigin, clipAgentId),
      wikiIgnoreUrl: buildWikiIgnoreUrl(webUiOrigin, clipAgentId),
      clipSuccessUrl: lastClipSuccessUrl,
      clipSavedWithoutOrigin,
    });
    return true;
  }

  if (msg.type === "connect") {
    serverUrl = msg.serverUrl || serverUrl;
    authToken = msg.authToken || authToken;
    chrome.storage.local.set({ serverUrl, authToken });
    connect();
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "disconnect") {
    disconnect();
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "update_domains") {
    void (async () => {
      try {
        await applyAccessPolicyPayload(
          { domains: msg.domains || [] },
          { notifyServer: true },
        );
        persistAccessPolicyLocal();
        sendResponse({ ok: true });
      } catch (error) {
        sendResponse({ ok: false, error: error?.message || String(error) });
      }
    })();
    return true;
  }

  if (msg.type === "update_access_policy") {
    void (async () => {
      try {
        await applyAccessPolicyPayload(
          {
            allow_all_eligible_tabs: msg.allowAllEligibleTabs,
            domains: msg.domains,
            paused_tab_ids: msg.pausedTabIds,
          },
          { notifyServer: true },
        );
        persistAccessPolicyLocal();
        sendTabsUpdate();
        sendResponse({ ok: true });
      } catch (error) {
        sendResponse({ ok: false, error: error?.message || String(error) });
      }
    })();
    return true;
  }

  if (msg.type === "toggle_pause_tab") {
    const tabId = Number.parseInt(String(msg.tabId), 10);
    if (!Number.isInteger(tabId)) {
      sendResponse({ ok: false });
      return true;
    }
    void (async () => {
      try {
        if (pausedTabIds.has(tabId)) {
          pausedTabIds.delete(tabId);
        } else {
          pausedTabIds.add(tabId);
          await detachDebugger(tabId);
        }
        persistAccessPolicyLocal();
        if (ws && ws.readyState === WebSocket.OPEN) {
          sendAccessPolicyUpdate();
        }
        sendTabsUpdate();
        sendResponse({ ok: true, paused: pausedTabIds.has(tabId) });
      } catch (error) {
        sendResponse({ ok: false, error: error?.message || String(error) });
      }
    })();
    return true;
  }

  if (msg.type === "get_access_policy") {
    sendResponse({
      authorizedDomains,
      allowAllEligibleTabs,
      pausedTabIds: [...pausedTabIds],
    });
    return true;
  }

  if (msg.type === "glow_control") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) sendGlowToTab(tabs[0].id, msg.active);
    });
    return false;
  }
});
