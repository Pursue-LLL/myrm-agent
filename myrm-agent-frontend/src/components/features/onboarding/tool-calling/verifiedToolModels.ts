/**
 * Curated list of verified models for tool-calling capabilities.
 *
 * Provides benchmark model recommendations and validation utilities
 * to prevent silent tool-calling failures when users configure custom models.
 */

export interface VerifiedToolModel {
  id: string;
  name: string;
  provider: string;
  descriptionKey: string;
  recommended: boolean;
}

export const VERIFIED_TOOL_MODELS: readonly VerifiedToolModel[] = [
  {
    id: 'claude-3-5-sonnet-latest',
    name: 'Claude 3.5 Sonnet',
    provider: 'Anthropic',
    descriptionKey: 'benchmarkAnthropic',
    recommended: true,
  },
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    provider: 'OpenAI',
    descriptionKey: 'benchmarkOpenAI',
    recommended: true,
  },
  {
    id: 'deepseek-chat',
    name: 'DeepSeek-V3',
    provider: 'DeepSeek',
    descriptionKey: 'benchmarkDeepSeek',
    recommended: true,
  },
  {
    id: 'qwen-2.5-coder-32b-instruct',
    name: 'Qwen 2.5 Coder 32B',
    provider: 'Qwen / Ollama',
    descriptionKey: 'benchmarkQwen',
    recommended: true,
  },
] as const;

/**
 * Check whether a given model string or ID matches a known verified tool-calling model.
 */
export function isVerifiedToolCallingModel(modelName: string): boolean {
  if (!modelName || !modelName.trim()) {
    return false;
  }
  const normalized = modelName.trim().toLowerCase();

  // 1. Direct or partial ID matching
  for (const item of VERIFIED_TOOL_MODELS) {
    if (normalized === item.id.toLowerCase() || normalized.includes(item.id.toLowerCase())) {
      return true;
    }
  }

  // 2. Common tool-calling certified families
  const certifiedPatterns = [
    /claude-3-5-sonnet/i,
    /claude-3-7-sonnet/i,
    /gpt-4o/i,
    /gpt-4-turbo/i,
    /o1/i,
    /o3-mini/i,
    /deepseek-chat/i,
    /deepseek-v3/i,
    /qwen2\.5-coder/i,
    /qwen-2\.5-coder/i,
  ];

  return certifiedPatterns.some((pattern) => pattern.test(normalized));
}
