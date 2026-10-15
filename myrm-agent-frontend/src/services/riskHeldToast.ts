/**
 * [INPUT]
 * @/services/i18nToastService (POS: localized toasts outside React)
 *
 * [OUTPUT]
 * - parseRiskRules: the rules in an SSE payload.
 * - showRiskHeldToast: the one notice for a held text, worded here in the user's language with the rule names the
 *   settings page shows and where to turn the rule off.
 * - showRiskHeldRefusal: shows that notice for a REST error body that is such a refusal, and says whether it was one.
 *
 * [POS]
 * Shared by the chat SSE `risk_blocked` event, the central API error toast and the direct-fetch steer call, so a text
 * held on any path gets the same notice. The server sends rule ids and names only, never a sentence or the held text.
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
  if (typeof detail !== 'object' || detail === null) {
    return false;
  }
  const { code, rules } = detail as { code?: unknown; rules?: unknown };
  if (code !== RISK_HELD_CODE) {
    return false;
  }
  showRiskHeldToast(parseRiskRules(rules));
  return true;
}
