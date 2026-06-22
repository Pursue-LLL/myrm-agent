/**
 * Myrm Agent Extension — Side Panel Chat UI
 *
 * Lightweight chat client that communicates with myrm-agent-server via HTTP+SSE.
 * Reuses existing server API endpoints — zero backend changes required.
 *
 * API contracts:
 * - POST /api/v1/agents/agent-stream → SSE streaming chat
 * - GET  /api/v1/chats/{chatId}/messages → message history
 * - POST /api/v1/agents/agent/{messageId}/cancel → cancel
 * - GET  /api/v1/agents/chat/{chatId}/attach → re-attach to active stream
 */

// --- State ---

const state = {
  serverBaseUrl: "",
  authToken: "",
  chatId: null,
  connected: false,
  streaming: false,
  abortController: null,
  activeTab: null,
  selectedText: null,
  contextDismissed: false,
  pendingApproval: null,
  currentMessageId: null,
};

// --- DOM refs ---

const $ = (id) => document.getElementById(id);

const dom = {
  connDot: $("conn-dot"),
  contextBar: $("context-bar"),
  contextValue: $("context-value"),
  contextDismiss: $("context-dismiss"),
  selectionCtx: $("selection-ctx"),
  selectionText: $("selection-text"),
  messagesEl: $("messages"),
  emptyState: $("empty-state"),
  streamingIndicator: $("streaming-indicator"),
  streamingLabel: $("streaming-label"),
  approvalOverlay: $("approval-overlay"),
  approvalTitle: $("approval-title"),
  approvalDetail: $("approval-detail"),
  btnApprove: $("btn-approve"),
  btnReject: $("btn-reject"),
  notConnected: $("not-connected"),
  inputArea: $("input-area"),
  chatInput: $("chat-input"),
  btnSend: $("btn-send"),
  btnCancel: $("btn-cancel"),
  btnNewChat: $("btn-new-chat"),
  btnSettings: $("btn-settings"),
  openPopupLink: $("open-popup-link"),
};

// --- Init ---

function init() {
  setupEventListeners();
  listenForBackgroundMessages();
  requestActiveTabContext();
  loadConfig();
}

function loadConfig() {
  chrome.storage.local.get(["serverUrl", "authToken"], (data) => {
    const wsUrl = data.serverUrl || "";
    state.authToken = data.authToken || "";
    state.serverBaseUrl = wsUrl
      .replace(/^ws:/, "http:")
      .replace(/^wss:/, "https:")
      .replace(/\/api\/v1\/ws\/extension\/?$/, "")
      .replace(/\/ws\/extension\/?$/, "")
      .replace(/\/$/, "");

    if (state.serverBaseUrl) {
      checkConnection();
    } else {
      setConnectionState("disconnected");
    }
  });
}

chrome.storage.onChanged.addListener((changes) => {
  if (changes.serverUrl || changes.authToken) loadConfig();
});

// --- Connection ---

async function checkConnection() {
  if (!state.serverBaseUrl) { setConnectionState("disconnected"); return; }
  setConnectionState("connecting");
  try {
    const resp = await apiFetch("/api/v1/health", { method: "GET" });
    setConnectionState(resp.ok ? "connected" : "error");
  } catch {
    setConnectionState("error");
  }
}

function setConnectionState(status) {
  state.connected = status === "connected";
  dom.connDot.className = `connection-dot ${status}`;
  dom.notConnected.classList.toggle("visible", !state.connected);
  dom.inputArea.style.display = state.connected ? "block" : "none";
  dom.btnSend.disabled = !state.connected;
}

// --- API helpers ---

function apiFetch(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(state.authToken ? { Authorization: `Bearer ${state.authToken}` } : {}),
    ...(options.headers || {}),
  };
  return fetch(`${state.serverBaseUrl}${path}`, { ...options, headers });
}

function generateId(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

// --- Chat ---

async function sendMessage() {
  const input = dom.chatInput.value.trim();
  if (!input || state.streaming) return;

  dom.chatInput.value = "";
  autoResizeInput();

  if (!state.chatId) state.chatId = generateId("spc");
  const messageId = generateId("sp");
  state.currentMessageId = messageId;

  let contextPrefix = "";
  if (!state.contextDismissed && state.activeTab) {
    contextPrefix = `[Current page: ${state.activeTab.title} — ${state.activeTab.url}]\n\n`;
  }
  if (state.selectedText) {
    contextPrefix += `[Selected text: "${state.selectedText}"]\n\n`;
  }

  addMessage("user", input);
  clearSelection();
  setStreaming(true);

  const assistantEl = addMessage("assistant", "");
  const contentEl = assistantEl.querySelector(".message-bubble");
  let toolProgressEl = null;
  state.abortController = new AbortController();

  try {
    const resp = await apiFetch("/api/v1/agents/agent-stream", {
      method: "POST",
      body: JSON.stringify({
        message_id: messageId,
        chat_id: state.chatId,
        query: contextPrefix + input,
        action_mode: "agent",
        multiplexed: false,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        timestamp: Date.now() / 1000,
      }),
      signal: state.abortController.signal,
      headers: { Accept: "text/event-stream" },
    });

    if (!resp.ok) {
      const errText = await resp.text().catch(() => resp.statusText);
      throw new Error(`Server error ${resp.status}: ${errText}`);
    }

    await consumeSSE(resp.body, contentEl, () => {
      if (!toolProgressEl) {
        toolProgressEl = document.createElement("div");
        toolProgressEl.className = "tool-progress";
        assistantEl.appendChild(toolProgressEl);
      }
      return toolProgressEl;
    });
  } catch (err) {
    if (err.name !== "AbortError") {
      contentEl.textContent = `Error: ${err.message}`;
      contentEl.style.color = "var(--error)";
    }
  } finally {
    setStreaming(false);
    state.abortController = null;
    state.currentMessageId = null;
    scrollToBottom();
  }
}

// --- SSE consumer ---

async function consumeSSE(body, contentEl, getToolEl) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullContent = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") return;
      try {
        const event = JSON.parse(data);
        handleSSEEvent(event, getToolEl, (text) => {
          fullContent += text;
          contentEl.textContent = fullContent;
          scrollToBottom();
        });
      } catch { /* skip malformed */ }
    }
  }
}

function handleSSEEvent(event, getToolEl, appendText) {
  switch (event.type) {
    case "message":
      if (event.data) appendText(typeof event.data === "string" ? event.data : "");
      break;
    case "message_end":
    case "agent_cancelled":
      notifyGlow(false);
      break;
    case "tool_start": {
      const name = event.tool_name || "tool";
      addToolStep(getToolEl(), name, "running");
      dom.streamingLabel.textContent = `Using ${name}\u2026`;
      notifyGlow(true);
      break;
    }
    case "tool_end": {
      const name = event.tool_name || "tool";
      updateLastToolStep(getToolEl(), name, "done");
      dom.streamingLabel.textContent = "Thinking\u2026";
      break;
    }
    case "tool_failure": {
      const name = event.tool_name || "tool";
      updateLastToolStep(getToolEl(), name, "error");
      break;
    }
    case "tool_approval_request":
    case "approval_required":
      showApproval(event);
      break;
    case "approval_processed":
      hideApproval();
      break;
    case "error":
      if (event.error || event.data) appendText(`\n\nError: ${event.error || event.data}`);
      break;
    case "tasks_steps":
    case "tool_heartbeat":
    case "sources":
    case "reasoning":
    case "token_usage":
    case "status":
      break;
    default: break;
  }
}

// --- Tool progress ---

const TOOL_ICONS = { running: "◎", done: "✓", error: "✗" };

function addToolStep(container, name, status) {
  if (!container) return;
  const step = document.createElement("div");
  step.className = `tool-step ${status}`;
  step.dataset.tool = name;
  step.innerHTML = `<span class="icon">${TOOL_ICONS[status] || "◎"}</span><span class="name">${escapeHtml(name)}</span>`;
  container.appendChild(step);
  scrollToBottom();
}

function updateLastToolStep(container, name, status) {
  if (!container) return;
  const last = container.querySelector(".tool-step:last-child");
  if (last) {
    last.className = `tool-step ${status}`;
    last.querySelector(".icon").textContent = TOOL_ICONS[status] || "◎";
    if (name) last.querySelector(".name").textContent = name;
  }
}

// --- Tool approval ---

function showApproval(event) {
  state.pendingApproval = event;
  if (event.type === "tool_approval_request" && event.data) {
    const action = event.data.actionRequests?.[0];
    const requestId = event.data.extensions?.approval?.requestId;
    state.pendingApproval._requestId = requestId;
    dom.approvalTitle.textContent = `Approve: ${action?.action || "action"}`;
    dom.approvalDetail.textContent = action?.description || JSON.stringify(action?.args || {}, null, 2);
  } else {
    const payload = event.data || {};
    dom.approvalTitle.textContent = `Approval required`;
    dom.approvalDetail.textContent = payload.message || JSON.stringify(payload, null, 2);
  }
  dom.approvalOverlay.classList.add("visible");
}

function hideApproval() {
  state.pendingApproval = null;
  dom.approvalOverlay.classList.remove("visible");
}

async function respondApproval(approved) {
  if (!state.pendingApproval) return;
  const approvalId = state.pendingApproval._requestId;
  hideApproval();
  if (!approvalId) return;
  try {
    await apiFetch(`/api/v1/approvals/${approvalId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ decision: approved ? "approve" : "deny" }),
    });
  } catch (err) {
    console.error("[SidePanel] Approval response failed:", err);
  }
}

// --- Messages UI ---

function addMessage(role, content) {
  dom.emptyState.style.display = "none";
  const div = document.createElement("div");
  div.className = `message ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = content;
  div.appendChild(bubble);
  dom.messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}

function scrollToBottom() {
  requestAnimationFrame(() => { dom.messagesEl.scrollTop = dom.messagesEl.scrollHeight; });
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

// --- Streaming state ---

function setStreaming(active) {
  state.streaming = active;
  dom.streamingIndicator.classList.toggle("visible", active);
  dom.btnSend.disabled = active || !state.connected;
  dom.chatInput.disabled = active;
  dom.streamingLabel.textContent = "Thinking…";
  if (!active) notifyGlow(false);
}

async function cancelStream() {
  if (state.abortController) state.abortController.abort();
  if (state.currentMessageId) {
    apiFetch(`/api/v1/agents/agent/${state.currentMessageId}/cancel`, { method: "POST" }).catch(() => {});
  }
  setStreaming(false);
}

// --- Tab context ---

function requestActiveTabContext() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0] && tabs[0].url && !tabs[0].url.startsWith("chrome://")) {
      state.activeTab = { id: tabs[0].id, title: tabs[0].title || "", url: tabs[0].url };
      showTabContext();
    }
  });
  chrome.tabs.onActivated.addListener((info) => {
    chrome.tabs.get(info.tabId, (tab) => {
      if (tab && tab.url && !tab.url.startsWith("chrome://")) {
        state.activeTab = { id: tab.id, title: tab.title || "", url: tab.url };
        state.contextDismissed = false;
        showTabContext();
      }
    });
  });
}

function showTabContext() {
  if (state.contextDismissed || !state.activeTab) return;
  const title = state.activeTab.title || new URL(state.activeTab.url).hostname;
  dom.contextValue.textContent = title.length > 50 ? title.slice(0, 47) + "…" : title;
  dom.contextBar.classList.add("visible");
}

function hideTabContext() {
  state.contextDismissed = true;
  dom.contextBar.classList.remove("visible");
}

// --- Selected text ---

function setSelection(text) {
  if (!text || !text.trim()) return;
  state.selectedText = text.trim().slice(0, 2000);
  dom.selectionText.textContent = state.selectedText;
  dom.selectionCtx.classList.add("visible");
}

function clearSelection() {
  state.selectedText = null;
  dom.selectionCtx.classList.remove("visible");
}

// --- Background message listener ---

function listenForBackgroundMessages() {
  chrome.runtime.onMessage.addListener((msg) => {
    switch (msg.type) {
      case "selected_text": setSelection(msg.text); break;
      case "context_menu_query":
        setSelection(msg.text);
        dom.chatInput.value = msg.prompt || "";
        dom.chatInput.focus();
        break;
      case "connection_changed":
        setConnectionState(msg.connected ? "connected" : "disconnected");
        break;
    }
  });
}

function notifyGlow(active) {
  chrome.runtime.sendMessage({ type: "glow_control", active }).catch(() => {});
}

// --- Event listeners ---

function setupEventListeners() {
  dom.btnSend.addEventListener("click", sendMessage);
  dom.chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  dom.chatInput.addEventListener("input", autoResizeInput);
  dom.contextDismiss.addEventListener("click", hideTabContext);
  dom.btnNewChat.addEventListener("click", () => {
    state.chatId = null;
    dom.messagesEl.innerHTML = "";
    dom.emptyState.style.display = "";
    dom.messagesEl.appendChild(dom.emptyState);
    if (state.abortController) state.abortController.abort();
    setStreaming(false);
    clearSelection();
  });
  dom.btnSettings.addEventListener("click", () => chrome.action.openPopup());
  dom.openPopupLink.addEventListener("click", (e) => { e.preventDefault(); chrome.action.openPopup(); });
  dom.btnCancel.addEventListener("click", cancelStream);
  dom.btnApprove.addEventListener("click", () => respondApproval(true));
  dom.btnReject.addEventListener("click", () => respondApproval(false));
}

function autoResizeInput() {
  const el = dom.chatInput;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

// --- Boot ---

init();
