/**
 * Static provider data-usage hints for egress disclosure cards.
 *
 * [INPUT]
 * - (none — compile-time catalog)
 *
 * [OUTPUT]
 * - resolveProviderDataUsage, ProviderDataUsagePolicyKey
 *
 * [POS]
 * Settings DataFlow LLM egress 卡的训练/数据使用政策静态映射（honest doc 外链）。
 */

export type ProviderDataUsagePolicyKey =
  | 'api_not_used_for_training'
  | 'account_settings_apply'
  | 'self_hosted'
  | 'third_party_routing'
  | 'review_provider_policy';

export interface ProviderDataUsageEntry {
  policyKey: ProviderDataUsagePolicyKey;
  docUrl?: string;
}

const CATALOG: Record<string, ProviderDataUsageEntry> = {
  openai: {
    policyKey: 'api_not_used_for_training',
    docUrl: 'https://openai.com/policies/api-data-usage-policies',
  },
  anthropic: {
    policyKey: 'api_not_used_for_training',
    docUrl: 'https://docs.anthropic.com/en/docs/legal-center/data-usage-policy',
  },
  gemini: {
    policyKey: 'account_settings_apply',
    docUrl: 'https://ai.google.dev/gemini-api/terms',
  },
  deepseek: {
    policyKey: 'review_provider_policy',
    docUrl: 'https://platform.deepseek.com/terms',
  },
  openrouter: {
    policyKey: 'third_party_routing',
    docUrl: 'https://openrouter.ai/privacy',
  },
  xai: {
    policyKey: 'review_provider_policy',
    docUrl: 'https://x.ai/legal/privacy-policy',
  },
  moonshot: {
    policyKey: 'review_provider_policy',
    docUrl: 'https://platform.moonshot.cn/docs/agreement',
  },
  zai: {
    policyKey: 'review_provider_policy',
    docUrl: 'https://open.bigmodel.cn/dev/api/agreement',
  },
  groq: {
    policyKey: 'api_not_used_for_training',
    docUrl: 'https://groq.com/privacy-policy/',
  },
  ollama: { policyKey: 'self_hosted' },
  lm_studio: { policyKey: 'self_hosted' },
};

export function resolveProviderDataUsage(providerId: string, isLocalHost: boolean): ProviderDataUsageEntry {
  if (isLocalHost) {
    return { policyKey: 'self_hosted' };
  }
  return CATALOG[providerId] ?? { policyKey: 'review_provider_policy' };
}
