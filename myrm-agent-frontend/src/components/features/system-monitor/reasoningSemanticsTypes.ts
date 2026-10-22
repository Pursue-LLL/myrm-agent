/**
 * [INPUT]: Raw LLM provider tokens, normalization policies, and invariant verification results.
 * [OUTPUT]: Strong TypeScript definitions for reasoning token semantics, zero-double-counting assertions, and honest HUD displays.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/reasoningSemanticsTypes.ts
 */

export type ReasoningInclusionPolicy =
  | 'INCLUDED_IN_COMPLETION'
  | 'STANDALONE_OUTPUT'
  | 'INDEPENDENT_BILLING';

export interface NormalizedTokenUsageSnapshot {
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  visible_content_tokens: number;
  total_tokens: number;
  cost_usd: number;
  is_zero_double_counted: boolean;
  raw_provider: string;
  policy_applied: ReasoningInclusionPolicy;
  normalized_at: string;
}

export interface InvariantCheckResult {
  is_valid: boolean;
  violation_type?: string | null;
  diagnostic_warning?: string | null;
  corrected_snapshot?: NormalizedTokenUsageSnapshot | null;
}

export interface ProviderPolicyItem {
  provider_keyword: string;
  policy: string;
  description: string;
}
