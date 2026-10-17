/**
 * Myrm Agent Extension — Side Panel Chat UI
 *
 * [INPUT]
 * - server_client.js::createServerClient (POS: server location, credentials and health of the Side Panel)
 * - sse.js::readSSE (POS: transport parsing of the agent stream)
 * - approval.js::describeApproval (POS: decision logic of the approval flow: what to show, whether to approve)
 * - approval_overlay.js::createApprovalOverlay (POS: DOM rendering of the approval card)
 * - approval_notify.js::notifyApprovalPending (POS: system notification while an approval waits)
 * - chat_view.js::createChatView (POS: DOM rendering of the conversation)
 * - page_context.js::createPageContext (POS: active tab and selected text a message is asked about)
 * - tool_steps.js::addToolStep (POS: DOM rendering of tool progress)
 * - POST /api/v1/agents/agent-stream (SSE chat; with `resume_value` it answers a pending tool approval) and
 *   POST /api/v1/agents/agent/{messageId}/cancel
 *
 * [OUTPUT]
 * - None: the page's entry script; it wires the modules above to the Side Panel DOM.
 *
 * [POS] Controller of the Side Panel chat: turns user input and agent events into the stream, the approval flow and
 * the input lock.
 */

import { applyDocumentI18n, msg } from "../i18n.js";
import {
  buildResumeValue,
  buildStreamBody,
  clockTimeFormatter,
  describeApproval,
  isResumeConflict,
  resolveApprovalCopy,
} from "./approval.js";
import { clearApprovalNotification, notifyApprovalPending } from "./approval_notify.js";
import { createApprovalOverlay } from "./approval_overlay.js";
import { createChatView } from "./chat_view.js";
import { createPageContext } from "./page_context.js";
import { createServerClient } from "./server_client.js";
import { readSSE } from "./sse.js";
import { addToolStep, updateLastToolStep } from "./tool_steps.js";

// --- State ---

const state = {
  chatId: null,
  connected: false,
  streaming: false,
  abortController: null,
  /** The approval waiting for an answer: `{ view, turn }`, `turn` being the assistant message it belongs to. */
  pendingApproval: null,
  approvalExpiryTimer: null,
  currentMessageId: null,
};

// --- DOM refs ---

const $ = (id) => document.getElementById(id);

const uiLanguage = chrome.i18n.getUILanguage();
const formatClockTime = clockTimeFormatter(uiLanguage);

const dom = {
  connDot: $("conn-dot"),
  streamingIndicator: $("streaming-indicator"),
  streamingLabel: $("streaming-label"),
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

const server = createServerClient(setConnectionState);

const chatView = createChatView({ messages: $("messages"), emptyState: $("empty-state") });

const approvalOverlay = createApprovalOverlay({
  root: $("approval-overlay"),
  title: $("approval-title"),
  list: $("approval-list"),
  hint: $("approval-hint"),
  deadline: $("approval-deadline"),
  approve: dom.btnApprove,
  reject: dom.btnReject,
});

const pageContext = createPageContext({
  bar: $("context-bar"),
  value: $("context-value"),
  dismiss: $("context-dismiss"),
  selectionBox: $("selection-ctx"),
  selectionText: $("selection-text"),
});

// --- Init ---

function init() {
  document.documentElement.lang = uiLanguage;
  applyDocumentI18n();
  setupEventListeners();
  listenForBackgroundMessages();
  pageContext.start();
  server.start();
}

// --- Connection ---

function setConnectionState(status) {
  state.connected = status === "connected";
  dom.connDot.className = `connection-dot ${status}`;
  dom.notConnected.classList.toggle("visible", !state.connected);
  dom.inputArea.style.display = state.connected ? "block" : "none";
  syncInputLock();
}

/** The input is closed while a turn streams and while an approval waits: a new message must not overtake the answer. */
function syncInputLock() {
  const locked = state.streaming || Boolean(state.pendingApproval);
  dom.chatInput.disabled = locked;
  dom.chatInput.placeholder = msg(state.pendingApproval ? "panelInputPaused" : "panelInputPlaceholder");
  dom.btnSend.disabled = locked || !state.connected;
}

function generateId(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

// --- Chat ---

async function sendMessage() {
  const input = dom.chatInput.value.trim();
  if (!input || state.streaming || state.pendingApproval) return;

  dom.chatInput.value = "";
  autoResizeInput();

  if (!state.chatId) state.chatId = generateId("spc");

  const query = pageContext.queryPrefix() + input;
  chatView.addMessage("user", input);
  pageContext.clearSelection();

  await streamTurn(chatView.createTurn(generateId("sp")), { query });
}

/**
 * Streams `turn` from the server: a new message (`query`), or the answer to its pending approval (`resumeValue`).
 * @returns {Promise<boolean>} true when an approval answer never reached the server, so it can be given again
 */
async function streamTurn(turn, { query = "", resumeValue } = {}) {
  state.currentMessageId = turn.messageId;
  setStreaming(true);
  state.abortController = new AbortController();
  let reachedServer = false;

  try {
    const resp = await server.apiFetch("/api/v1/agents/agent-stream", {
      method: "POST",
      body: JSON.stringify(
        buildStreamBody({
          messageId: turn.messageId,
          chatId: state.chatId,
          query,
          resumeValue,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          timestamp: Date.now() / 1000,
        }),
      ),
      signal: state.abortController.signal,
      headers: { Accept: "text/event-stream" },
    });

    if (resumeValue && isResumeConflict(resp.status)) {
      chatView.appendNotice(turn, msg("approvalHandledElsewhere"));
      return false;
    }
    if (!resp.ok) {
      const errText = await resp.text().catch(() => resp.statusText);
      throw new Error(`Server error ${resp.status}: ${errText}`);
    }

    reachedServer = true;
    await readSSE(resp.body, (event) => handleSSEEvent(event, turn));
  } catch (err) {
    if (err.name === "AbortError") return false;
    if (resumeValue && !reachedServer) {
      chatView.appendNotice(turn, msg("approvalSendFailed"));
      return true;
    }
    console.error("Agent stream failed", err);
    chatView.showError(turn, msg("panelStreamError"));
  } finally {
    setStreaming(false);
    state.abortController = null;
    state.currentMessageId = null;
    chatView.scrollToBottom();
  }
  return false;
}

// --- SSE events ---

/** Both fields the server uses to say a message was refused because the chat's previous run is still going. */
const AGENT_BUSY_ERROR_TYPE = "AgentBusyError";
const AGENT_BUSY_STATUS = 409;

/** @param {{ error_type?: unknown, status_code?: unknown }} event */
function isAgentBusy(event) {
  return event.error_type === AGENT_BUSY_ERROR_TYPE || event.status_code === AGENT_BUSY_STATUS;
}

function handleSSEEvent(event, turn) {
  switch (event.type) {
    case "message":
      if (event.data) chatView.appendText(turn, typeof event.data === "string" ? event.data : "");
      break;
    case "message_end":
    case "agent_cancelled":
      notifyGlow(false);
      break;
    case "tool_start": {
      const name = toolName(event);
      addToolStep(chatView.toolContainer(turn), name, "running");
      chatView.scrollToBottom();
      dom.streamingLabel.textContent = msg("panelUsingTool", name);
      notifyGlow(true);
      break;
    }
    case "tool_end":
      updateLastToolStep(chatView.toolContainer(turn), toolName(event), "done");
      dom.streamingLabel.textContent = msg("panelThinking");
      break;
    case "tool_failure":
      updateLastToolStep(chatView.toolContainer(turn), toolName(event), "error");
      break;
    case "tool_approval_request":
    case "approval_required":
      showApproval(event, turn);
      break;
    case "error":
      // The raw error text is for developers: the chat only says what the user can act on.
      if (event.error || event.data) {
        console.error("Agent reported an error", event.error || event.data);
        chatView.showError(turn, msg(isAgentBusy(event) ? "panelAgentBusy" : "panelStreamError"));
      }
      break;
  }
}

function toolName(event) {
  return event.tool_name || msg("panelToolFallback");
}

// --- Tool approval ---

/** `setTimeout` runs a delay above this at once, which would close the card the moment it opens. */
const MAX_TIMER_DELAY_MS = 2 ** 31 - 1;

function showApproval(event, turn) {
  renderApproval({ view: describeApproval(event, { language: uiLanguage }), turn });
}

function renderApproval(pending) {
  const { view } = pending;
  const copy = resolveApprovalCopy(view, msg, formatClockTime);
  state.pendingApproval = pending;
  approvalOverlay.show(view, copy);
  syncInputLock();
  approvalOverlay.focusSafeAnswer();
  notifyApprovalPending(copy.deadline);
  scheduleApprovalExpiry(pending, copy.expired);
}

/**
 * At its deadline the server settles an unanswered approval itself, so the card must not keep asking: it closes and
 * says so, which also reopens the input.
 */
function scheduleApprovalExpiry(pending, notice) {
  clearTimeout(state.approvalExpiryTimer);
  if (!pending.view.deadline) return;
  const delay = Math.max(0, pending.view.deadline.atMs - Date.now());
  if (delay > MAX_TIMER_DELAY_MS) return;
  const expire = () => {
    hideApproval();
    chatView.appendNotice(pending.turn, notice);
  };
  state.approvalExpiryTimer = setTimeout(expire, delay);
}

function hideApproval() {
  clearTimeout(state.approvalExpiryTimer);
  state.pendingApproval = null;
  approvalOverlay.hide();
  clearApprovalNotification();
  syncInputLock();
}

/**
 * Answers the pending approval by resuming its turn; a request only the Web UI can answer is just dismissed.
 * An answer that did not reach the server brings the approval back, unless a newer one has taken its place.
 */
async function respondApproval(approved) {
  const pending = state.pendingApproval;
  if (!pending || state.streaming || (approved && !pending.view.canApprove)) return;
  hideApproval();
  if (pending.view.kind !== "tool") return;
  const resumeValue = buildResumeValue(approved, pending.view.interruptId);
  const answerLost = await streamTurn(pending.turn, { resumeValue });
  if (answerLost && !state.pendingApproval) renderApproval(pending);
}

// --- Streaming state ---

function setStreaming(active) {
  state.streaming = active;
  dom.streamingIndicator.classList.toggle("visible", active);
  syncInputLock();
  dom.btnApprove.disabled = active;
  dom.btnReject.disabled = active;
  dom.streamingLabel.textContent = msg("panelThinking");
  if (active) return;
  notifyGlow(false);
  if (state.pendingApproval) approvalOverlay.focusSafeAnswer();
}

async function cancelStream() {
  if (state.abortController) state.abortController.abort();
  if (state.currentMessageId) {
    server.apiFetch(`/api/v1/agents/agent/${state.currentMessageId}/cancel`, { method: "POST" }).catch(() => {});
  }
  setStreaming(false);
}

// --- Background message listener ---

function listenForBackgroundMessages() {
  chrome.runtime.onMessage.addListener((message) => {
    switch (message.type) {
      case "selected_text":
        pageContext.setSelection(message.text);
        break;
      case "context_menu_query":
        pageContext.setSelection(message.text);
        dom.chatInput.value = message.prompt || "";
        dom.chatInput.focus();
        break;
      case "connection_changed":
        setConnectionState(message.connected ? "connected" : "disconnected");
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
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  dom.chatInput.addEventListener("input", autoResizeInput);
  dom.btnNewChat.addEventListener("click", () => {
    state.chatId = null;
    chatView.reset();
    if (state.abortController) state.abortController.abort();
    hideApproval();
    setStreaming(false);
    pageContext.clearSelection();
  });
  dom.btnSettings.addEventListener("click", () => chrome.action.openPopup());
  dom.openPopupLink.addEventListener("click", (e) => {
    e.preventDefault();
    chrome.action.openPopup();
  });
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
