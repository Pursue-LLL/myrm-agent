/**
 * Client-side Pareto agent profile diversity linting and root vendor extraction.
 * Mirrors myrm_agent_harness.backends.profiles.diversity_lint for instant UI validation.
 */

const PROVIDER_ROOT_VENDOR_MAP: Record<string, string> = {
  'azure-openai': 'openai',
  azure_openai: 'openai',
  azure: 'openai',
  openai: 'openai',
  'openai-codex': 'openai',
  anthropic: 'anthropic',
  claude: 'anthropic',
  deepseek: 'deepseek',
  google: 'google',
  gemini: 'google',
  meta: 'meta',
  'meta-llama': 'meta',
  mistral: 'mistral',
  mistralai: 'mistral',
  qwen: 'qwen',
  alibaba: 'qwen',
  xai: 'xai',
  grok: 'xai',
  groq: 'groq',
  together: 'together',
  togetherai: 'together',
  siliconflow: 'siliconflow',
  openrouter: 'openrouter',
  ollama: 'local',
  lmstudio: 'local',
  vllm: 'local',
};

export interface ModelSlotInput {
  providerId?: string;
  provider?: string;
  model?: string;
  slotName?: string;
  reasoningEffort?: string;
}

export interface ClientDiversityResult {
  isValid: boolean;
  distinctVendorCount: number;
  distinctVendors: string[];
  slotsEvaluated: number;
  reason?: string;
}

export function extractClientRootVendor(providerId?: string, model?: string): string {
  const normProvider = (providerId || '').toLowerCase().trim();
  const normModel = (model || '').toLowerCase().trim();

  // 1. OpenRouter model prefix extraction: e.g. "meta-llama/..." -> "meta"
  if (normProvider === 'openrouter' && normModel.includes('/')) {
    const prefix = normModel.split('/')[0];
    if (prefix.includes('llama') || prefix.includes('meta')) return 'meta';
    if (prefix.includes('qwen') || prefix.includes('alibaba')) return 'qwen';
    if (prefix.includes('claude') || prefix.includes('anthropic')) return 'anthropic';
    if (prefix.includes('deepseek')) return 'deepseek';
    if (prefix.includes('openai') || prefix.includes('gpt')) return 'openai';
    if (prefix.includes('gemini') || prefix.includes('google')) return 'google';
    if (prefix.includes('mistral')) return 'mistral';
    return prefix;
  }

  // 2. Direct provider lookup
  if (normProvider && PROVIDER_ROOT_VENDOR_MAP[normProvider]) {
    return PROVIDER_ROOT_VENDOR_MAP[normProvider];
  }

  // 3. Fallback to model heuristics
  if (normModel.includes('gpt') || normModel.includes('o1') || normModel.includes('o3') || normModel.includes('openai')) {
    return 'openai';
  }
  if (normModel.includes('claude') || normModel.includes('anthropic') || normModel.includes('sonnet') || normModel.includes('haiku')) {
    return 'anthropic';
  }
  if (normModel.includes('deepseek')) {
    return 'deepseek';
  }
  if (normModel.includes('gemini') || normModel.includes('google')) {
    return 'google';
  }
  if (normModel.includes('llama')) {
    return 'meta';
  }
  if (normModel.includes('qwen')) {
    return 'qwen';
  }
  if (normModel.includes('grok')) {
    return 'xai';
  }

  return normProvider || 'unknown';
}

export function validateClientProviderDiversity(
  slots: ModelSlotInput[],
  options: { minDistinctVendors?: number } = {},
): ClientDiversityResult {
  const minDistinct = options.minDistinctVendors ?? 2;
  const vendors = new Set<string>();
  let evaluatedCount = 0;

  for (const slot of slots) {
    const provider = slot.providerId || slot.provider || '';
    const model = slot.model || '';
    if (!provider && !model) continue;

    evaluatedCount++;
    const rootVendor = extractClientRootVendor(provider, model);
    if (rootVendor && rootVendor !== 'unknown') {
      vendors.add(rootVendor);
    }
  }

  const distinctVendors = Array.from(vendors);
  const isValid = distinctVendors.length >= minDistinct;

  return {
    isValid,
    distinctVendorCount: distinctVendors.length,
    distinctVendors,
    slotsEvaluated: evaluatedCount,
    reason: isValid
      ? undefined
      : `Insufficient provider diversity: ${distinctVendors.length} found, minimum ${minDistinct} required.`,
  };
}
