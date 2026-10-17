/**
 * Side Panel message list: the user's messages and the assistant turns streamed into it.
 *
 * [INPUT]
 * - The scrollable message list and its empty-state placeholder
 *
 * [OUTPUT]
 * - createChatView: message creation (`addMessage`, `createTurn`), turn updates (`appendText`, `toolContainer`,
 *   `appendNotice`, `showError`) and `reset` / `scrollToBottom`
 *
 * [POS] DOM rendering of the conversation for sidepanel.js; all content is written as text, never as HTML.
 */

/**
 * One assistant message and what has been streamed into it; a resumed approval continues the same turn.
 * @typedef {{ messageId: string, el: HTMLElement, bubble: HTMLElement, toolEl: HTMLElement | null, text: string }} Turn
 */

/**
 * @param {{ messages: HTMLElement, emptyState: HTMLElement }} elements
 */
export function createChatView({ messages, emptyState }) {
  function scrollToBottom() {
    requestAnimationFrame(() => {
      messages.scrollTop = messages.scrollHeight;
    });
  }

  /**
   * @param {"user" | "assistant"} role
   * @param {string} content
   * @returns {HTMLElement}
   */
  function addMessage(role, content) {
    emptyState.style.display = "none";
    const message = document.createElement("div");
    message.className = `message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = content;
    message.appendChild(bubble);
    messages.appendChild(message);
    scrollToBottom();
    return message;
  }

  return {
    scrollToBottom,
    addMessage,

    /**
     * @param {string} messageId
     * @returns {Turn}
     */
    createTurn(messageId) {
      const el = addMessage("assistant", "");
      return { messageId, el, bubble: el.querySelector(".message-bubble"), toolEl: null, text: "" };
    },

    /** @param {Turn} turn @param {string} text */
    appendText(turn, text) {
      turn.text += text;
      turn.bubble.textContent = turn.text;
      scrollToBottom();
    },

    /** @param {Turn} turn @returns {HTMLElement} the tool-progress block of the turn, created on first use */
    toolContainer(turn) {
      if (!turn.toolEl) {
        turn.toolEl = document.createElement("div");
        turn.toolEl.className = "tool-progress";
        turn.el.appendChild(turn.toolEl);
      }
      return turn.toolEl;
    },

    /** @param {Turn} turn @param {string} text */
    appendNotice(turn, text) {
      const notice = document.createElement("div");
      notice.className = "turn-notice";
      notice.textContent = text;
      turn.el.appendChild(notice);
    },

    /** Ends the turn's message with an error line, keeping what was already streamed. @param {Turn} turn @param {string} text */
    showError(turn, text) {
      turn.bubble.textContent = `${turn.text}${turn.text ? "\n\n" : ""}${text}`;
      turn.bubble.classList.add("error");
    },

    reset() {
      messages.innerHTML = "";
      emptyState.style.display = "";
      messages.appendChild(emptyState);
    },
  };
}
