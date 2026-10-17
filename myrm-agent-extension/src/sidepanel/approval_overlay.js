/**
 * Side Panel approval overlay (DOM only; what it shows is decided by approval.js).
 *
 * [INPUT]
 * - The overlay's elements, and a described approval plus its localized copy from approval.js
 *
 * [OUTPUT]
 * - createApprovalOverlay: `show(view, copy)` fills and opens the overlay, `hide()` closes it, `focusSafeAnswer()`
 *   puts focus on its reject button
 *
 * [POS] DOM rendering of the Side Panel approval card; every string from the agent is written as text, never as HTML.
 */

/**
 * @param {HTMLElement} parent
 * @param {keyof HTMLElementTagNameMap} tag
 * @param {string} className
 * @param {string} text nothing is appended when it is empty
 */
function appendText(parent, tag, className, text) {
  if (!text) return;
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  parent.appendChild(element);
}

/**
 * @param {import("./approval.js").ApprovalAction} action
 * @returns {HTMLElement}
 */
function renderAction(action) {
  const item = document.createElement("div");
  item.className = "approval-action";
  appendText(item, "div", "approval-summary", action.summary);
  appendText(item, "pre", "approval-body", action.body);
  appendText(item, "div", "approval-reason", action.reason);
  return item;
}

/**
 * @param {{
 *   root: HTMLElement,
 *   title: HTMLElement,
 *   list: HTMLElement,
 *   hint: HTMLElement,
 *   deadline: HTMLElement,
 *   approve: HTMLButtonElement,
 *   reject: HTMLButtonElement,
 * }} elements
 */
export function createApprovalOverlay({ root, title, list, hint, deadline, approve, reject }) {
  return {
    /**
     * @param {import("./approval.js").ApprovalView} view
     * @param {{ title: string, hint: string, deadline: string, rejectLabel: string }} copy
     */
    show(view, copy) {
      title.textContent = copy.title;
      list.replaceChildren(...view.actions.map(renderAction));
      list.scrollTop = 0;
      list.hidden = view.actions.length === 0;
      hint.textContent = copy.hint;
      hint.hidden = !copy.hint;
      deadline.textContent = copy.deadline;
      deadline.hidden = !copy.deadline;
      approve.hidden = !view.canApprove;
      reject.textContent = copy.rejectLabel;
      root.classList.add("visible");
    },
    hide() {
      root.classList.remove("visible");
    },
    /**
     * The safe answer takes focus, but only while the user is already working in the panel: focus must not be pulled
     * from the page they are typing in. A button that is still disabled (the turn is streaming) cannot take it.
     */
    focusSafeAnswer() {
      if (document.hasFocus()) reject.focus({ preventScroll: true });
    },
  };
}
