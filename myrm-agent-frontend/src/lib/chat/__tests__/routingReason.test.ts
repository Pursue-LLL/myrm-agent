import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { resolveRoutingReasonKey, type RoutingReasonKey, type RoutingTierValue } from '../routingReason';

/** Reasons emitted by harness `complexity_router.route_task` / `specialty_router.route_task_specialty`. */
const COMPLEXITY_REASONS = [
  'empty_query',
  'momentum_override',
  'content_dedup',
  'rule_based',
  'llm_judge_cached',
  'llm_judge_unavailable',
  'llm_judge',
  'default_standard',
  'min_tier_escalation(rule_based)',
  'min_tier_escalation(llm_judge)',
] as const;

const LOCALES = ['en', 'zh', 'zh-TW', 'ja', 'ko', 'de'] as const;

const ALL_KEYS: RoutingReasonKey[] = [
  'routingReasonSimpleIndicator',
  'routingReasonKeywordReasoning',
  'routingReasonKeywordStandard',
  'routingReasonSpecialtyCode',
  'routingReasonSpecialtyLongDoc',
  'routingReasonComplaintUp',
  'routingReasonMomentum',
  'routingReasonLlmJudge',
  'routingReasonJudgeUnavailable',
  'routingReasonDefaultStandard',
];

describe('resolveRoutingReasonKey', () => {
  it.each<[string, RoutingTierValue, RoutingReasonKey]>([
    ['rule_based', 'simple', 'routingReasonSimpleIndicator'],
    ['rule_based', 'reasoning', 'routingReasonKeywordReasoning'],
    ['rule_based', 'standard', 'routingReasonKeywordStandard'],
    ['content_dedup', 'simple', 'routingReasonSimpleIndicator'],
    ['content_dedup', 'standard', 'routingReasonKeywordStandard'],
  ])('maps %s with tier %s to %s', (reason, tier, key) => {
    expect(resolveRoutingReasonKey(reason, tier)).toBe(key);
  });

  it.each<[string, RoutingReasonKey]>([
    ['momentum_override', 'routingReasonMomentum'],
    ['llm_judge', 'routingReasonLlmJudge'],
    ['llm_judge_cached', 'routingReasonLlmJudge'],
    ['llm_judge_unavailable', 'routingReasonJudgeUnavailable'],
    ['default_standard', 'routingReasonDefaultStandard'],
    ['empty_query', 'routingReasonDefaultStandard'],
    ['min_tier_escalation(rule_based)', 'routingReasonComplaintUp'],
    ['min_tier_escalation(momentum_override)', 'routingReasonComplaintUp'],
  ])('maps %s to %s regardless of tier', (reason, key) => {
    expect(resolveRoutingReasonKey(reason, 'standard')).toBe(key);
  });

  it.each<[string, RoutingTierValue, RoutingReasonKey]>([
    ['specialty_slot_hit(code:code_fence_block)', 'code', 'routingReasonSpecialtyCode'],
    ['specialty_slot_hit(code:momentum_inherited(code))', 'code', 'routingReasonSpecialtyCode'],
    ['specialty_slot_hit(long_doc:char_length_exceeded(5000>=4000))', 'long_doc', 'routingReasonSpecialtyLongDoc'],
    ['specialty_slot_hit(reasoning:math_latex_notation)', 'reasoning', 'routingReasonKeywordReasoning'],
  ])('maps specialty hit %s to %s', (reason, tier, key) => {
    expect(resolveRoutingReasonKey(reason, tier)).toBe(key);
  });

  it('resolves every complexity-router reason the harness emits', () => {
    for (const reason of COMPLEXITY_REASONS) {
      expect(resolveRoutingReasonKey(reason, 'standard'), reason).not.toBeNull();
    }
  });

  it.each(['', 'rule:keyword(reasoning)', 'judge:simple', 'specialty_slot_hit(casual:x)', 'constructor', '__proto__'])(
    'returns null for unrecognized reason %j instead of leaking router internals',
    (reason) => {
      expect(resolveRoutingReasonKey(reason, 'standard')).toBeNull();
    },
  );
});

describe('routing reason locale coverage', () => {
  it.each(LOCALES)('%s defines every routing reason key', (locale) => {
    const messages = JSON.parse(readFileSync(resolve(__dirname, `../../../../locales/${locale}.json`), 'utf8')) as {
      chat: { tokenUsage: Record<string, string> };
    };
    for (const key of ALL_KEYS) {
      expect(messages.chat.tokenUsage[key], `${locale}:${key}`).toBeTruthy();
    }
  });
});
