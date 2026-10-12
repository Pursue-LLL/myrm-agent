/**
 * [INPUT]
 * - routingReason / routingTier persisted on assistant messages (emitted by the harness complexity and specialty routers)
 *
 * [OUTPUT]
 * - RoutingTierValue / RoutingReasonKey: tier and `chat.tokenUsage` locale-key unions.
 * - resolveRoutingReasonKey: maps a router verdict reason to a user-facing locale key.
 *
 * [POS]
 * Single translation point for smart-routing attribution copy. A reason the table does not know
 * resolves to null so the UI hides the row instead of exposing raw router internals.
 */

export type RoutingTierValue = 'simple' | 'standard' | 'reasoning' | 'complex' | 'code' | 'long_doc';

export type RoutingReasonKey =
  | 'routingReasonSimpleIndicator'
  | 'routingReasonKeywordReasoning'
  | 'routingReasonKeywordStandard'
  | 'routingReasonSpecialtyCode'
  | 'routingReasonSpecialtyLongDoc'
  | 'routingReasonComplaintUp'
  | 'routingReasonMomentum'
  | 'routingReasonLlmJudge'
  | 'routingReasonJudgeUnavailable'
  | 'routingReasonDefaultStandard';

/** Reasons whose meaning does not depend on the resulting tier. */
const STATIC_REASON_KEYS: ReadonlyMap<string, RoutingReasonKey> = new Map([
  ['momentum_override', 'routingReasonMomentum'],
  ['llm_judge', 'routingReasonLlmJudge'],
  ['llm_judge_cached', 'routingReasonLlmJudge'],
  ['llm_judge_unavailable', 'routingReasonJudgeUnavailable'],
  ['default_standard', 'routingReasonDefaultStandard'],
  ['empty_query', 'routingReasonDefaultStandard'],
]);

/** `specialty_slot_hit(<specialty>:<detail>)` — the specialty names the matched policy. */
const SPECIALTY_REASON_KEYS: ReadonlyMap<string, RoutingReasonKey> = new Map([
  ['code', 'routingReasonSpecialtyCode'],
  ['long_doc', 'routingReasonSpecialtyLongDoc'],
  ['reasoning', 'routingReasonKeywordReasoning'],
]);

/** `rule_based` / `content_dedup` carry no pattern name; the resulting tier tells which pattern family matched. */
const RULE_BASED_TIER_KEYS: ReadonlyMap<RoutingTierValue, RoutingReasonKey> = new Map([
  ['simple', 'routingReasonSimpleIndicator'],
  ['reasoning', 'routingReasonKeywordReasoning'],
]);

const SPECIALTY_HIT_PATTERN = /^specialty_slot_hit\(([a-z_]+):/;

export function resolveRoutingReasonKey(reason: string, tier: RoutingTierValue): RoutingReasonKey | null {
  if (reason.startsWith('min_tier_escalation(')) {
    return 'routingReasonComplaintUp';
  }
  const specialty = SPECIALTY_HIT_PATTERN.exec(reason)?.[1];
  if (specialty !== undefined) {
    return SPECIALTY_REASON_KEYS.get(specialty) ?? null;
  }
  if (reason === 'rule_based' || reason === 'content_dedup') {
    return RULE_BASED_TIER_KEYS.get(tier) ?? 'routingReasonKeywordStandard';
  }
  return STATIC_REASON_KEYS.get(reason) ?? null;
}
