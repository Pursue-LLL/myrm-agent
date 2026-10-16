/**
 * Side Panel tool-approval rules (pure; testable without DOM or chrome.* APIs).
 *
 * [INPUT]
 * - SSE `tool_approval_request` / `approval_required` events from POST /api/v1/agents/agent-stream
 *
 * [OUTPUT]
 * - describeApproval: what the panel shows and whether it may approve
 * - resolveApprovalCopy: localized overlay text for a described approval
 * - buildResumeValue / buildStreamBody: the request that settles an interrupt (same endpoint as a new message)
 * - isResumeConflict: the interrupt was already settled elsewhere
 *
 * [POS] Decision logic of the Side Panel approval flow; sidepanel.js owns the DOM and the network.
 */

/**
 * Review-config keys the Side Panel can honor. Any other key set on an action (spend digest, dual confirmation,
 * irreversible-action warning, impact summary, ...) means the Web UI shows or asks for more than one click, so the
 * Side Panel never approves such a request (it can still reject it). New keys therefore fail closed.
 */
const PLAIN_REVIEW_KEYS = new Set(["allowedDecisions", "hideAllowAlways", "domainApproval"]);

/** Denial reason handed to the agent, the same text the Web UI sends. */
const REJECT_FEEDBACK = "User rejected this action.";

const MAX_DETAIL_CHARS = 300;

/**
 * @typedef {{ name: string, detail: string }} ApprovalAction
 * @typedef {{ kind: "tool" | "external", actions: ApprovalAction[], canApprove: boolean }} ApprovalView
 * `tool`: answerable here (one decision covers every listed action). `external`: only the Web UI can answer it.
 */

/**
 * @param {unknown} value
 * @returns {string}
 */
function truncate(value) {
  const text = String(value);
  return text.length > MAX_DETAIL_CHARS ? `${text.slice(0, MAX_DETAIL_CHARS - 1)}…` : text;
}

/**
 * @param {{ action?: unknown, description?: unknown, args?: unknown }} request
 * @returns {ApprovalAction}
 */
function describeAction(request) {
  const description = typeof request?.description === "string" ? request.description.trim() : "";
  return {
    name: truncate(request?.action || "tool"),
    detail: truncate(description || JSON.stringify(request?.args ?? {})),
  };
}

/**
 * @param {unknown} config one entry of `reviewConfigs`
 * @returns {boolean} whether the Side Panel may approve the action it belongs to
 */
function isPlainReviewConfig(config) {
  if (config === null || config === undefined) return true;
  if (typeof config !== "object") return false;
  if (Array.isArray(config.allowedDecisions) && !config.allowedDecisions.includes("approve")) return false;
  return Object.entries(config).every(
    ([key, value]) => PLAIN_REVIEW_KEYS.has(key) || value === null || value === undefined || value === false,
  );
}

/**
 * @param {{ type?: string, data?: Record<string, unknown> }} event SSE event; its payload is untrusted and checked field by field
 * @returns {ApprovalView}
 */
export function describeApproval(event) {
  const payload = event?.data;
  const requests =
    event?.type === "tool_approval_request" && Array.isArray(payload?.actionRequests) ? payload.actionRequests : [];
  if (requests.length === 0) return { kind: "external", actions: [], canApprove: false };

  const reviewConfigs = Array.isArray(payload.reviewConfigs) ? payload.reviewConfigs : [];
  const canApprove = payload.extensions?.displayMode !== "handover" && reviewConfigs.every(isPlainReviewConfig);
  return { kind: "tool", actions: requests.map(describeAction), canApprove };
}

/**
 * @param {ApprovalView} view
 * @param {(key: string, substitution?: string | number) => string} translate
 * @returns {{ title: string, detail: string, hint: string, rejectLabel: string }}
 */
export function resolveApprovalCopy(view, translate) {
  if (view.kind === "external") {
    return {
      title: translate("approvalTitleExternal"),
      detail: "",
      hint: translate("approvalHintExternal"),
      rejectLabel: translate("approvalDismiss"),
    };
  }
  const [first] = view.actions;
  return {
    title:
      view.actions.length === 1
        ? translate("approvalTitleSingle", first.name)
        : translate("approvalTitleBatch", view.actions.length),
    detail: view.actions.map((action) => `${action.name}: ${action.detail}`).join("\n"),
    hint: view.canApprove ? "" : translate("approvalHintElevated"),
    rejectLabel: translate("approvalReject"),
  };
}

/**
 * One decision for every action of the interrupt (the harness applies it to each of them).
 * @param {boolean} approved
 * @returns {{ decision: "approve" } | { decision: "reject", feedback: string }}
 */
export function buildResumeValue(approved) {
  return approved ? { decision: "approve" } : { decision: "reject", feedback: REJECT_FEEDBACK };
}

/**
 * Body of POST /api/v1/agents/agent-stream: a new message, or with `resumeValue` the answer to a pending interrupt.
 * @param {{ messageId: string, chatId: string, query: string, resumeValue?: object, timezone: string, timestamp: number }} fields
 */
export function buildStreamBody({ messageId, chatId, query, resumeValue, timezone, timestamp }) {
  return {
    message_id: messageId,
    chat_id: chatId,
    query,
    action_mode: "agent",
    multiplexed: false,
    timezone,
    timestamp,
    ...(resumeValue && { resume_value: resumeValue }),
  };
}

/**
 * The server answers 409 when the interrupt was already settled (timeout, or another window).
 * @param {number} status
 * @returns {boolean}
 */
export function isResumeConflict(status) {
  return status === 409;
}
