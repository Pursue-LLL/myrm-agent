/**
 * [INPUT]
 * @/services/i18nToastService (POS: localized toasts outside React)
 *
 * [OUTPUT]
 * - parseRiskRules: the rules in an SSE payload.
 * - showRiskHeldToast: the one notice for a held text, worded here in the user's language with the rule names the
 *   settings page shows and where to turn the rule off.
 * - showRiskHeldRefusal: shows that notice for a REST error body that is such a refusal, and says whether it was one.
 * - riskHeldErrorFromResponse: the same for a failed `fetch` that did not go through `apiRequest`; returns the error
 *   to throw once the notice is shown.
 * - isRiskHeldError: whether an error is such a refusal, so a caller whose notice is already shown adds no failure
 *   toast of its own.
 *
 * [POS]
 * Shared by the chat SSE `risk_blocked` event, the central API error toast and every direct-fetch call of a text the
 * server may hold, so a text held on any path gets the same notice once. The server sends rule ids and names only,
 * never a sentence or the held text.
 */

import { showI18nToast, translateI18nKeyIfPresent } from '@/services/i18nToastService';

/** The `detail.code` of a REST refusal of text a server risk rule holds. */
const RISK_HELD_CODE = 'risk_held';

interface RiskRule {
  rule_id: string;
  display_name: string;
}

const RISK_RULES_KEY = 'settings.securityPolicy.riskRules';
const MAX_NAMED_RULES = 3;
const TOAST_DURATION_MS = 10_000;

function isRiskHeldDetail(detail: unknown): detail is Record<string, unknown> {
  return typeof detail === 'object' && detail !== null && (detail as { code?: unknown }).code === RISK_HELD_CODE;
}

function isRiskRule(value: unknown): value is RiskRule {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const rule = value as Record<string, unknown>;
  return typeof rule.rule_id === 'string' && typeof rule.display_name === 'string';
}

export function parseRiskRules(value: unknown): RiskRule[] {
  return Array.isArray(value) ? value.filter(isRiskRule) : [];
}

/** Built-in rules are named in the user's language like on the settings page; a custom rule keeps its own name. */
function ruleLabel(rule: RiskRule): string {
  return translateI18nKeyIfPresent(`${RISK_RULES_KEY}.rules.${rule.rule_id}.name`, rule.display_name);
}

export function showRiskHeldToast(rules: readonly RiskRule[]): void {
  const names = [...new Set(rules.map(ruleLabel))].slice(0, MAX_NAMED_RULES).join(' / ');

  showI18nToast(`${RISK_RULES_KEY}.blockedTitle`, undefined, {
    type: 'error',
    duration: TOAST_DURATION_MS,
    descriptionKey: `${RISK_RULES_KEY}.blockedDescription`,
    descriptionValues: { rules: names },
  });
}

/** Whether `detail` (an HTTP 400 body's `detail`) is a risk-held refusal; if so the notice has been shown. */
export function showRiskHeldRefusal(detail: unknown): boolean {
  if (!isRiskHeldDetail(detail)) {
    return false;
  }
  showRiskHeldToast(parseRiskRules(detail.rules));
  return true;
}

/** A refusal whose notice has been shown; its message is the neutral title, never the server's English text. */
export class RiskHeldRefusalError extends Error {
  constructor(public readonly data: Record<string, unknown>) {
    super(translateI18nKeyIfPresent(`${RISK_RULES_KEY}.blockedTitle`, 'Content blocked by risk rules'));
    this.name = 'RiskHeldRefusalError';
  }
}

/** Whether `error` is a refusal the user has already been told about (`apiRequest`'s `ApiError` or a `RiskHeldRefusalError`). */
export function isRiskHeldError(error: unknown): boolean {
  return error instanceof Error && isRiskHeldDetail((error as { data?: unknown }).data);
}

/**
 * A failed `fetch` response that did not go through `apiRequest`: when its body is a risk-held refusal, shows the
 * notice and returns the error to throw; otherwise null, with the body still readable by the caller.
 */
export async function riskHeldErrorFromResponse(response: Response): Promise<RiskHeldRefusalError | null> {
  if (response.status !== 400) {
    return null;
  }
  const body: unknown = await response
    .clone()
    .json()
    .catch(() => null);
  const detail = typeof body === 'object' && body !== null ? (body as { detail?: unknown }).detail : undefined;
  if (!isRiskHeldDetail(detail)) {
    return null;
  }
  showRiskHeldToast(parseRiskRules(detail.rules));
  return new RiskHeldRefusalError(detail);
}
