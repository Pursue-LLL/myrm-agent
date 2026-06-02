/**
 * Reasoning 模型检测模块
 *
 * 基于模型名称正则匹配，判断模型是否支持 reasoning/thinking 能力。
 * 作为 customModelInfo.supports_reasoning 的 fallback 机制。
 *
 * 设计原则：
 * - 覆盖主流 reasoning 模型（Claude、GPT-o系列、Gemini、DeepSeek、Qwen 等）
 * - 保持简洁，不照搬竞品的 30+ 模型类型函数（过度设计）
 * - 易于维护和扩展
 */

/**
 * 已知支持 reasoning 的模型名称正则模式
 *
 * 匹配逻辑：模型 ID 转小写后匹配
 * 覆盖范围：
 * - Anthropic: Claude 3.7+, Claude 4.x
 * - OpenAI: o1, o3, o4-mini, GPT-5
 * - Google: Gemini 2.5+ (thinking)
 * - DeepSeek: DeepSeek-R1, DeepSeek-V3+
 * - Qwen: Qwen3, QwQ, QvQ
 * - 其他: Grok, Mistral (Magistral), Kimi, MiniMax, MiMo 等
 */
const REASONING_MODEL_PATTERNS: RegExp[] = [
  // Anthropic Claude (3.7+, 4.x)
  /claude-3[-.]7/,
  /claude-sonnet-4/,
  /claude-opus-4/,
  /claude-haiku-4/,

  // OpenAI o-series and GPT-5
  /\bo1\b/,
  /\bo3\b/,
  /\bo3-mini\b/,
  /\bo4-mini\b/,
  /gpt-5/,

  // Google Gemini (thinking models)
  /gemini-2\.5/,
  /gemini.*thinking/,

  // DeepSeek
  /deepseek-r1/,
  /deepseek-v3/,
  /deepseek-chat-v3/,

  // Qwen reasoning models
  /qwen3/,
  /qwq/,
  /qvq/,

  // Grok
  /grok-3/,
  /grok-4/,

  // Mistral (Magistral)
  /magistral/,

  // Kimi
  /kimi-k2-thinking/,
  /kimi-k[2-9]/,

  // MiniMax
  /minimax-m[1-3]/,

  // MiMo
  /mimo/,

  // Step
  /step-3/,
  /step-r1/,

  // Zhipu
  /glm-z1/,

  // Baichuan
  /baichuan-m[2-3]/,

  // Ling
  /ring-1t/,
  /ring-mini/,
  /ring-flash/,
];

/**
 * 检测模型是否支持 reasoning 能力（基于模型名称正则匹配）
 *
 * @param modelId - 模型 ID（如 "claude-sonnet-4-20250514"）
 * @returns true 如果模型支持 reasoning
 */
export function isReasoningModelByName(modelId: string): boolean {
  if (!modelId) return false;

  const lowerId = modelId.toLowerCase();

  return REASONING_MODEL_PATTERNS.some((pattern) => pattern.test(lowerId));
}

/**
 * 双层检测：判断模型是否支持 reasoning
 *
 * 优先级：
 * 1. API/用户配置的 supports_reasoning（如果明确设置了）
 * 2. 正则匹配 fallback（覆盖已知 reasoning 模型）
 *
 * @param modelId - 模型 ID
 * @param apiSupportsReasoning - API 或用户配置的 supports_reasoning 值（可能为 undefined）
 * @returns true 如果模型支持 reasoning
 */
export function detectReasoningSupport(modelId: string, apiSupportsReasoning: boolean | undefined): boolean {
  // 如果 API/用户明确配置了，使用配置值
  if (apiSupportsReasoning !== undefined) {
    return apiSupportsReasoning;
  }

  // Fallback：正则匹配
  return isReasoningModelByName(modelId);
}
