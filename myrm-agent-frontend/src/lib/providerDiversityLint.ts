/**
 * Provider Diversity Linting & Root Vendor Extraction utility.
 *
 * [INPUT]
 * - Model selections / provider identifiers (e.g. { providerId: 'openai', model: 'gpt-4o' })
 *
 * [OUTPUT]
 * - extractRootVendor: maps proxy routers and wrappers to fundamental root vendor
 * - validateProviderDiversity: verifies >= minDistinctVendors unique root vendors
 *
 * [POS]
 * Frontend counterpart to harness `diversity_lint.py`.
 * Prevents mono-vendor bias and enforces Pareto multi-model heterogeneity.
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

const MODEL_PREFIX_VENDOR_MAP: Record<string, string> = {
  openai: 'openai',
  anthropic: 'anthropic',
  claude: 'anthropic',
  deepseek: 'deepseek',
  'deepseek-ai': 'deepseek',
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
  cohere: 'cohere',
  moonshot: 'moonshot',
  zhipu: 'zhipu',
  glm: 'zhipu',
  baichuan: 'baichuan',
  minimax: 'minimax',
};

export function extractRootVendor(providerId?: string | null, model?: string | null): string {
  const cleanProvider = (providerId ?? '').trim().toLowerCase();
  const cleanModel = (model ?? '').trim().toLowerCase();

  // 1. Handle multi-vendor proxy routers
  if (['openrouter', 'siliconflow', 'together', 'togetherai', 'groq'].includes(cleanProvider)) {
    if (cleanModel.includes('/')) {
      const prefix = cleanModel.split('/')[0].trim();
      if (prefix in MODEL_PREFIX_VENDOR_MAP) {
        return MODEL_PREFIX_VENDOR_MAP[prefix];
      }
    }
  }

  // 2. Check model string prefix
  if (cleanModel.includes('/')) {
    const prefix = cleanModel.split('/')[0].trim();
    if (prefix in MODEL_PREFIX_VENDOR_MAP) {
      return MODEL_PREFIX_VENDOR_MAP[prefix];
    }
  }

  // 3. Model family heuristics
  if (cleanModel.startsWith('gpt-') || cleanModel.startsWith('o1-') || cleanModel.startsWith('o3-')) {
    return 'openai';
  }
  if (cleanModel.startsWith('claude-') || cleanModel.startsWith('claude')) {
    return 'anthropic';
  }
  if (cleanModel.startsWith('deepseek-') || cleanModel.startsWith('deepseek')) {
    return 'deepseek';
  }
  if (cleanModel.startsWith('gemini-') || cleanModel.startsWith('gemma-')) {
    return 'google';
  }
  if (cleanModel.startsWith('qwen-') || cleanModel.startsWith('qwen2') || cleanModel.startsWith('qwq-')) {
    return 'qwen';
  }
  if (cleanModel.startsWith('llama-') || cleanModel.startsWith('llama3') || cleanModel.startsWith('llama2')) {
    return 'meta';
  }
  if (cleanModel.startsWith('mistral-') || cleanModel.startsWith('codestral-') || cleanModel.startsWith('mixtral-')) {
    return 'mistral';
  }
  if (cleanModel.startsWith('grok-') || cleanModel.startsWith('grok')) {
    return 'xai';
  }

  // 4. Provider lookup
  if (cleanProvider in PROVIDER_ROOT_VENDOR_MAP) {
    return PROVIDER_ROOT_VENDOR_MAP[cleanProvider];
  }

  return cleanProvider || cleanModel || 'unknown';
}

export interface ProviderDiversityValidationResult {
  isValid: boolean;
  distinctVendorCount: number;
  distinctVendors: string[];
  slotsEvaluated: number;
  reason: string;
}

export interface ModelSlotInput {
  providerId?: string;
  provider?: string;
  model?: string;
}

export function validateProviderDiversity(
  selections: ModelSlotInput[],
  minDistinctVendors: number = 2,
): ProviderDiversityValidationResult {
  if (!selections || selections.length === 0) {
    return {
      isValid: false,
      distinctVendorCount: 0,
      distinctVendors: [],
      slotsEvaluated: 0,
      reason: 'No model selections provided.',
    };
  }

  const vendors = new Set<string>();
  let slotsCount = 0;

  for (const item of selections) {
    slotsCount += 1;
    const provider = item.providerId ?? item.provider;
    const vendor = extractRootVendor(provider, item.model);
    if (vendor && vendor !== 'unknown') {
      vendors.add(vendor);
    }
  }

  const distinctVendors = Array.from(vendors).sort();
  const count = distinctVendors.length;

  if (count >= minDistinctVendors) {
    return {
      isValid: true,
      distinctVendorCount: count,
      distinctVendors,
      slotsEvaluated: slotsCount,
      reason: `Satisfies provider diversity: ${count} vendors (${distinctVendors.join(', ')}).`,
    };
  }

  return {
    isValid: false,
    distinctVendorCount: count,
    distinctVendors,
    slotsEvaluated: slotsCount,
    reason: `Insufficient provider diversity: ${count} vendor(s) (${distinctVendors.join(', ')}), minimum ${minDistinctVendors} required.`,
  };
}
