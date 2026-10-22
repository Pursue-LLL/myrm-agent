/**
 * Side Panel tool-progress rows (one row per tool call of an assistant message).
 *
 * [INPUT]
 * - A container element and the tool name/status reported by the agent SSE stream
 *
 * [OUTPUT]
 * - addToolStep: append a row for a tool call
 * - updateLastToolStep: set the status of the most recent row
 *
 * [POS] DOM rendering of tool progress for sidepanel.js; the tool name is only ever written as text.
 */

const TOOL_ICONS = { running: "◎", done: "✓", error: "✗" };

/**
 * @param {HTMLElement} container
 * @param {string} name
 * @param {"running" | "done" | "error"} status
 */
export function addToolStep(container, name, status) {
  const icon = document.createElement("span");
  icon.className = "icon";
  icon.textContent = TOOL_ICONS[status] || TOOL_ICONS.running;
  const label = document.createElement("span");
  label.className = "name";
  label.textContent = name;

  const step = document.createElement("div");
  step.className = `tool-step ${status}`;
  step.dataset.tool = name;
  step.append(icon, label);
  container.appendChild(step);
}

/**
 * @param {HTMLElement} container
 * @param {string} name
 * @param {"running" | "done" | "error"} status
 */
export function updateLastToolStep(container, name, status) {
  const last = container.querySelector(".tool-step:last-child");
  if (!last) return;
  last.className = `tool-step ${status}`;
  last.querySelector(".icon").textContent = TOOL_ICONS[status] || TOOL_ICONS.running;
  if (name) last.querySelector(".name").textContent = name;
}
