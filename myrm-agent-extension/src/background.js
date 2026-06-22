/**
 * Myrm Agent Extension — Background Service Worker (MV3)
 *
 * Maintains a persistent WebSocket connection to the Myrm Agent Server,
 * handles CDP proxy requests, manages tab lifecycle, context menus,
 * keyboard shortcuts, and Side Panel ↔ content script communication.
 *
 * Architecture:
 * - WebSocket: Extension ↔ server for CDP proxy and tab management
 * - Side Panel: Communicates directly with server via HTTP+SSE (not through this worker)
 * - Context Menu: "Ask Myrm Agent" right-click opens Side Panel with selected text
 * - Glow: Forwards glow state from Side Panel to content script on active tab
 * - Heartbeat: chrome.alarms ensures Service Worker stays alive
 */

const ALARM_NAME = "myrm-keepalive";
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_DELAY_MS = 30000;

let ws = null;
let serverUrl = "";
let authToken = "";
let reconnectDelay = RECONNECT_DELAY_MS;
let isConnecting = false;
let lastError = "";
let authorizedDomains = [];
let attachedTabs = new Map(); // tabId -> debugger target
let backgroundWindowId = null; // Isolated background window for non-disruptive automation

// --- Lifecycle ---

function restoreState() {
  chrome.storage.local.get(["serverUrl", "authToken", "authorizedDomains", "backgroundWindowId"], (data) => {
    serverUrl = data.serverUrl || "";
    authToken = data.authToken || "";
    authorizedDomains = data.authorizedDomains || [];
    backgroundWindowId = data.backgroundWindowId || null;
    if (serverUrl) connect();
  });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: 0.4 });
  setupContextMenu();
  restoreState();
});

chrome.runtime.onStartup.addListener(restoreState);

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    if (!ws && serverUrl && !isConnecting) {
      connect();
    }
  }
});

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
    lastError = "Invalid WebSocket URL";
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
    }));

    sendTabsUpdate();
    sendDomainsUpdate();
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
    if (!lastError) lastError = event.reason || "Connection closed";
    updateBadge("disconnected");
    detachAllDebuggers();
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws = null;
    isConnecting = false;
    lastError = "Connection refused — server not running?";
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
    chrome.storage.local.set({ authorizedDomains });
    send({ type: "domains_update", domains: authorizedDomains });
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

async function executeAction(action, payload) {
  switch (action) {
    case "list_tabs":
      return await getAuthorizedTabs();

    case "attach_debugger": {
      const { domain, tabId, background = true } = payload;

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

    case "detach_debugger": {
      const { tabId } = payload;
      await detachDebugger(tabId);
      return { success: true };
    }

    case "send_cdp": {
      const { tabId, method, params } = payload;
      return await sendCdpCommand(tabId, method, params);
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

async function findTabForDomain(domain) {
  const tabs = await chrome.tabs.query({});
  const authorized = tabs.filter((tab) => isTabAuthorized(tab));

  if (domain) {
    const matching = authorized.filter((tab) => extractDomain(tab.url || "") === domain);
    return matching.find((tab) => tab.active) || matching[0] || null;
  }

  return authorized.find((tab) => tab.active) || authorized[0] || null;
}

function isTabAuthorized(tab) {
  if (!tab.url) return false;
  const domain = extractDomain(tab.url);
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
  getAuthorizedTabs().then((tabs) => {
    send({ type: "tabs_update", tabs });
  });
}

function sendDomainsUpdate() {
  send({ type: "domains_update", domains: authorizedDomains });
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

  if (attachedTabs.has(tabId)) {
    return { cdp_ws_url: buildCdpProxyUrl(tabId) };
  }

  await chrome.debugger.attach(target, "1.3");
  attachedTabs.set(tabId, target);

  return { cdp_ws_url: buildCdpProxyUrl(tabId) };
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

async function sendCdpCommand(tabId, method, params) {
  if (!attachedTabs.has(tabId)) {
    throw new Error(`Debugger not attached to tab ${tabId}`);
  }
  return await chrome.debugger.sendCommand({ tabId }, method, params || {});
}

function buildCdpProxyUrl(tabId) {
  // The CDP proxy URL points back to the server's extension bridge endpoint
  // which will route CDP commands through the WebSocket to this extension
  const base = serverUrl.replace(/^ws/, "http").replace(/\/ws\/extension$/, "");
  return `${base}/api/extension/cdp/${tabId}`;
}

// --- Chrome Debugger Events ---

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

// --- Context Menu + Keyboard Shortcut + Glow ---

function setupContextMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "ask-myrm-agent", title: "Ask Myrm Agent", contexts: ["selection"] });
    chrome.contextMenus.create({ id: "ask-myrm-agent-page", title: "Ask Myrm Agent about this page", contexts: ["page"] });
  });
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
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
      serverUrl,
      authorizedDomains,
      attachedTabs: Array.from(attachedTabs.keys()),
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
    authorizedDomains = msg.domains || [];
    chrome.storage.local.set({ authorizedDomains });
    if (ws && ws.readyState === WebSocket.OPEN) {
      send({ type: "domains_update", domains: authorizedDomains });
    }
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "glow_control") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) sendGlowToTab(tabs[0].id, msg.active);
    });
    return false;
  }
});
