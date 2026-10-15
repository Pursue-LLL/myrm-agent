/**
 * [INPUT]
 * ../streamContext::StreamCtx (POS: per-SSE-event reducer context)
 * @/services/i18nToastService (POS: localized toasts outside React)
 *
 * [OUTPUT]
 * riskEvents: RISK_BLOCKED SSE handler. The server names the rules that held the message; the sentence is worded here,
 * in the user's language, with the rule names the settings page shows and where to turn the rule off.
 *
 * [POS]
 * Chat SSE event handler slice for the server-side input risk gate.
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import { AgentEventType } from '../../types/agentStream/part1';
import { showI18nToast, translateI18nKeyIfPresent } from '@/services/i18nToastService';

interface RiskBlockedPayload {
  rules?: Array<{ rule_id: string; display_name: string; severity: string }>;
}

const RISK_RULES_KEY = 'settings.securityPolicy.riskRules';
const MAX_NAMED_RULES = 3;
const TOAST_DURATION_MS = 10_000;

/** Built-in rules are named in the user's language like on the settings page; a custom rule keeps its own name. */
function ruleLabel(rule: { rule_id: string; display_name: string }): string {
  return translateI18nKeyIfPresent(`${RISK_RULES_KEY}.rules.${rule.rule_id}.name`, rule.display_name);
}

export async function riskEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;

  if (data.type === AgentEventType.RISK_BLOCKED) {
    const payload = data.data as RiskBlockedPayload | undefined;
    const names = [...new Set((payload?.rules ?? []).map(ruleLabel))].slice(0, MAX_NAMED_RULES).join(' / ');

    showI18nToast(`${RISK_RULES_KEY}.blockedTitle`, undefined, {
      type: 'error',
      duration: TOAST_DURATION_MS,
      descriptionKey: `${RISK_RULES_KEY}.blockedDescription`,
      descriptionValues: { rules: names },
    });

    actions.setLoading(false);
    return done(ctx);
  }

  return null;
}
