/**
 * Side Panel tool-approval rules (pure; testable without DOM or chrome.* APIs).
 *
 * [INPUT]
 * - SSE `tool_approval_request` / `approval_required` events from POST /api/v1/agents/agent-stream
 *
 * [OUTPUT]
 * - describeApproval: what the panel shows for the request and whether it may approve
 * - resolveApprovalCopy / clockTimeFormatter: localized overlay text for a described approval
 * - buildResumeValue / buildStreamBody: the request that settles an interrupt (same endpoint as a new message)
 * - isResumeConflict: the interrupt was already settled elsewhere
 *
 * [POS] Decision logic of the Side Panel approval flow; sidepanel.js owns the network, approval_overlay.js the DOM.
 */

/**
 * Review-config keys the Side Panel can honor. Any other key set on an action (spend digest, dual confirmation,
 * irreversible-action warning, impact summary, ...) means the Web UI shows or asks for more than one click, so the
 * Side Panel never approves such a request (it can still reject it). New keys therefore fail closed.
 */
const PLAIN_REVIEW_KEYS = new Set(["allowedDecisions", "hideAllowAlways", "domainApproval"]);

/** Denial reason handed to the agent, the same text the Web UI sends. */
const REJECT_FEEDBACK = "User rejected this action.";

/**
 * What the panel cannot show in full it does not approve: the dangerous part may sit anywhere in a command or an
 * argument value, so a cut view is marked with `…` and can only be rejected here. A shell command gets a larger room
 * than any other argument value.
 */
const MAX_COMMAND_CHARS = 2000;
const MAX_VALUE_CHARS = 300;

/** Argument names that carry the command text of a shell tool, in the harness' lookup order (`extract_shell_command_text`). */
const SHELL_COMMAND_KEYS = ["command", "code", "script", "cmd"];

/**
 * @typedef {{ summary: string, body: string, reason: string }} ApprovalAction
 * `summary`: what a shell command does in plain words (empty when the harness has no explanation: an internal tool
 * name is never shown); `body`: the command or arguments being approved; `reason`: why the policy asks.
 * @typedef {"elevated" | "too_long" | "no_details"} ApprovalBlocker
 * @typedef {{
 *   kind: "tool" | "external",
 *   actions: ApprovalAction[],
 *   canApprove: boolean,
 *   blocker?: ApprovalBlocker,
 *   interruptId?: string,
 *   deadline?: { atMs: number, behavior: "deny" | "allow" },
 * }} ApprovalView
 * `tool`: answerable here (one decision covers every listed action), `interruptId` naming the interrupt it settles.
 * `external`: only the Web UI can answer it.
 */

/** What the card and the notice that replaces it say when the server settles an unanswered request. */
const DEADLINE_KEYS = {
  deny: { pending: "approvalDeadlineDeny", expired: "approvalExpiredDeny" },
  allow: { pending: "approvalDeadlineAllow", expired: "approvalExpiredAllow" },
};

/**
 * @param {unknown} value
 * @param {number} limit
 * @returns {string}
 */
function truncate(value, limit) {
  const text = String(value);
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

/**
 * @param {unknown} value
 * @returns {string}
 */
function trimmedText(value) {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * @param {unknown} explanation the harness' `{ en, zh }` plain-language explanation of a command
 * @param {string} language UI language tag
 * @returns {string}
 */
function pickExplanation(explanation, language) {
  if (!explanation || typeof explanation !== "object") return "";
  const preferred = language.toLowerCase().startsWith("zh") ? ["zh", "en"] : ["en", "zh"];
  return preferred.map((key) => trimmedText(explanation[key])).find(Boolean) ?? "";
}

/**
 * @param {unknown} args
 * @returns {string} the shell command text, or "" when the arguments carry none
 */
function shellCommandText(args) {
  if (!args || typeof args !== "object") return "";
  const key = SHELL_COMMAND_KEYS.find((name) => trimmedText(args[name]));
  return key ? args[key] : "";
}

/**
 * @param {unknown} value
 * @returns {string}
 */
function asText(value) {
  return typeof value === "string" ? value : (JSON.stringify(value) ?? String(value));
}

/**
 * @param {unknown} args
 * @returns {{ body: string, fullyShown: boolean }} one `name: value` line per argument, a value over the limit cut
 * with the cut marked
 */
function formatArguments(args) {
  if (args === null || args === undefined) return { body: "", fullyShown: true };
  const entries =
    typeof args === "object" && !Array.isArray(args)
      ? Object.entries(args).map(([name, value]) => [`${name}: `, asText(value)])
      : [["", asText(args)]];
  return {
    body: entries.map(([label, text]) => `${label}${truncate(text, MAX_VALUE_CHARS)}`).join("\n"),
    fullyShown: entries.every(([, text]) => text.length <= MAX_VALUE_CHARS),
  };
}

/**
 * @param {{ action?: unknown, description?: unknown, args?: unknown, command_spans?: unknown, plain_explanation?: unknown }} request
 * @param {string} language
 * @returns {ApprovalAction & { fullyShown: boolean }}
 */
function describeAction(request, language) {
  const reason = trimmedText(request?.description);
  // The harness derives command spans and the explanation only for shell tools, so their presence marks one.
  const command = Array.isArray(request?.command_spans) ? shellCommandText(request?.args) : "";
  if (command) {
    return {
      summary: pickExplanation(request.plain_explanation, language),
      body: truncate(command, MAX_COMMAND_CHARS),
      reason,
      fullyShown: command.length <= MAX_COMMAND_CHARS,
    };
  }
  return { summary: "", ...formatArguments(request?.args), reason };
}

/**
 * Why the Side Panel may not approve a request, if it may not. An action it has nothing to show for would be approved
 * blind.
 * @param {Array<ApprovalAction & { fullyShown: boolean }>} described
 * @param {boolean} elevated
 * @returns {ApprovalBlocker | undefined}
 */
function findBlocker(described, elevated) {
  if (elevated) return "elevated";
  if (!described.every((action) => action.fullyShown)) return "too_long";
  if (described.some(({ summary, body, reason }) => !summary && !body && !reason)) return "no_details";
  return undefined;
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
 * The moment the server settles an unanswered request by itself. Measured from the arrival of the event on the panel's
 * own clock, because the server's `expiresAt` is on a clock the browser may not share.
 * @param {unknown} timeout `extensions.timeout` of the event
 * @param {number} now
 * @returns {ApprovalView["deadline"]}
 */
function describeDeadline(timeout, now) {
  const seconds = timeout?.seconds;
  const behavior = timeout?.behavior;
  if (typeof seconds !== "number" || !(seconds > 0) || (behavior !== "deny" && behavior !== "allow")) return undefined;
  return { atMs: now + seconds * 1000, behavior };
}

/**
 * @param {{ type?: string, data?: Record<string, unknown>, interruptId?: unknown }} event SSE event; its payload is untrusted and checked field by field
 * @param {{ now?: number, language?: string }} [context] arrival time and UI language tag
 * @returns {ApprovalView}
 */
export function describeApproval(event, { now = Date.now(), language = "en" } = {}) {
  const payload = event?.data;
  const requests =
    event?.type === "tool_approval_request" && Array.isArray(payload?.actionRequests) ? payload.actionRequests : [];
  if (requests.length === 0) return { kind: "external", actions: [], canApprove: false };

  const reviewConfigs = Array.isArray(payload.reviewConfigs) ? payload.reviewConfigs : [];
  const described = requests.map((request) => describeAction(request, language));
  const elevated = payload.extensions?.displayMode === "handover" || !reviewConfigs.every(isPlainReviewConfig);
  const blocker = findBlocker(described, elevated);
  const interruptId = typeof event.interruptId === "string" && event.interruptId ? event.interruptId : undefined;
  return {
    kind: "tool",
    actions: described.map(({ summary, body, reason }) => ({ summary, body, reason })),
    canApprove: blocker === undefined,
    blocker,
    interruptId,
    deadline: describeDeadline(payload.extensions?.timeout, now),
  };
}

/**
 * @param {string} language UI language tag
 * @returns {(timestampMs: number) => string} formats a moment as the clock time (with seconds) of the user's locale
 */
export function clockTimeFormatter(language) {
  const format = new Intl.DateTimeFormat(language, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return (timestampMs) => format.format(timestampMs);
}

/**
 * @param {ApprovalView} view
 * @param {(key: string, substitution?: string | number) => string} translate
 * @param {(timestampMs: number) => string} formatTime clock time in the user's locale
 * @returns {{ title: string, hint: string, deadline: string, expired: string, rejectLabel: string }}
 * `deadline` is the sentence under the card, `expired` the notice for when the deadline has passed unanswered.
 */
export function resolveApprovalCopy(view, translate, formatTime) {
  if (view.kind === "external") {
    return {
      title: translate("approvalTitleExternal"),
      hint: translate("approvalHintExternal"),
      deadline: "",
      expired: "",
      rejectLabel: translate("approvalDismiss"),
    };
  }
  const hints = {
    elevated: "approvalHintElevated",
    too_long: "approvalHintTooLong",
    no_details: "approvalHintNoDetails",
  };
  const deadlineKeys = view.deadline && DEADLINE_KEYS[view.deadline.behavior];
  return {
    title:
      view.actions.length === 1
        ? translate("approvalTitleSingle")
        : translate("approvalTitleBatch", view.actions.length),
    hint: view.blocker ? translate(hints[view.blocker]) : "",
    deadline: deadlineKeys ? translate(deadlineKeys.pending, formatTime(view.deadline.atMs)) : "",
    expired: deadlineKeys ? translate(deadlineKeys.expired) : "",
    rejectLabel: translate("approvalReject"),
  };
}

/**
 * One decision for every action of the interrupt (the harness applies it to each of them). With several interrupts
 * pending, `interruptId` is what makes the answer settle this one and no other.
 * @param {boolean} approved
 * @param {string} [interruptId] the interrupt the approval event named
 * @returns {{ decision: "approve" | "reject", feedback?: string, interruptId?: string }}
 */
export function buildResumeValue(approved, interruptId) {
  const answer = approved ? { decision: "approve" } : { decision: "reject", feedback: REJECT_FEEDBACK };
  return interruptId ? { ...answer, interruptId } : answer;
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
