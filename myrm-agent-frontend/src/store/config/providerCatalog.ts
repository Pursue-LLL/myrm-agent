/**
 * [INPUT]
 * (none)
 *
 * [OUTPUT]
 * BUILT_IN_PROVIDERS, BuiltInProviderId: ids of the providers the settings offer out of the box
 * ProviderInfo, AlternativeApiUrl: display name, default address, alternative addresses and console deep link
 * BUILT_IN_PROVIDER_INFO: the ProviderInfo of every built-in provider
 *
 * [POS]
 * Pure data catalog behind the provider list and the first-run provider rows. Routing and authentication rules live in
 * providerTypes.ts; the server's .env importer table is checked against this file by
 * test_importable_providers_catalog_parity.py.
 */

// 内置提供商 ID
export const BUILT_IN_PROVIDERS = [
  'openai',
  'anthropic',
  'gemini',
  'deepseek',
  'openrouter',
  'zai',
  'xai',
  'ollama',
  'moonshot',
  'lm_studio',
  'groq',
  'dashscope',
  'minimax',
  'mistral',
  'together_ai',
  'siliconflow',
  'volcengine',
  'fireworks_ai',
  'azure',
  'spark',
  'perplexity',
  'jina_ai',
  'bedrock',
  'xiaomi_mimo',
  'nvidia',
  'ai302',
  'opencode_go',
  'vercel_ai_gateway',
] as const;

export type BuiltInProviderId = (typeof BUILT_IN_PROVIDERS)[number];

// 备选 API URL 配置
export interface AlternativeApiUrl {
  url: string;
  label: string; // 显示名称，如 "Global (海外版)"
}

// 提供商信息
export interface ProviderInfo {
  id: string;
  name: string;
  icon?: string;
  isBuiltIn: boolean;
  defaultApiUrl?: string;
  alternativeApiUrls?: AlternativeApiUrl[]; // 可选的备选地址列表
  dashboardUrl?: string; // 官方控制台/仪表盘直达深链
}

// 内置提供商配置
export const BUILT_IN_PROVIDER_INFO: Record<BuiltInProviderId, ProviderInfo> = {
  openai: {
    id: 'openai',
    name: 'OpenAI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.openai.com/v1',
  },
  anthropic: {
    id: 'anthropic',
    name: 'Anthropic',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.anthropic.com',
  },
  gemini: {
    id: 'gemini',
    name: 'Google Gemini',
    isBuiltIn: true,
    defaultApiUrl: 'https://generativelanguage.googleapis.com/v1beta',
  },
  deepseek: {
    id: 'deepseek',
    name: 'DeepSeek',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.deepseek.com',
  },
  openrouter: {
    id: 'openrouter',
    name: 'OpenRouter',
    isBuiltIn: true,
    defaultApiUrl: 'https://openrouter.ai/api/v1',
  },
  zai: {
    id: 'zai',
    name: 'Z.AI (Zhipu AI)',
    isBuiltIn: true,
    defaultApiUrl: 'https://open.bigmodel.cn/api/paas/v4',
    alternativeApiUrls: [
      { url: 'https://open.bigmodel.cn/api/paas/v4', label: 'China (国内版)' },
      { url: 'https://api.z.ai/api/paas/v4', label: 'International (国际版)' },
      { url: 'https://api.z.ai/api/coding/paas/v4', label: 'Coding Plan' },
    ],
  },
  xai: {
    id: 'xai',
    name: 'xAI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.x.ai/v1',
  },
  ollama: {
    id: 'ollama',
    name: 'Ollama',
    isBuiltIn: true,
    defaultApiUrl: 'http://localhost:11434',
  },
  moonshot: {
    id: 'moonshot',
    name: 'Moonshot AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.moonshot.cn/v1',
    alternativeApiUrls: [
      { url: 'https://api.moonshot.cn/v1', label: 'China (国内版)' },
      { url: 'https://api.moonshot.ai/v1', label: 'International (国际版)' },
    ],
  },
  lm_studio: {
    id: 'lm_studio',
    name: 'LM Studio',
    isBuiltIn: true,
    defaultApiUrl: 'http://localhost:1234/v1',
  },
  groq: {
    id: 'groq',
    name: 'Groq',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.groq.com/openai/v1',
  },
  dashscope: {
    id: 'dashscope',
    name: 'Dashscope (Qwen)',
    isBuiltIn: true,
    defaultApiUrl: 'https://coding.dashscope.aliyuncs.com/v1',
    alternativeApiUrls: [
      { url: 'https://coding.dashscope.aliyuncs.com/v1', label: 'China (国内版)' },
      { url: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1', label: 'International (国际版)' },
    ],
  },
  minimax: {
    id: 'minimax',
    name: 'MiniMax',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.minimaxi.com/v1',
    alternativeApiUrls: [
      { url: 'https://api.minimaxi.com/v1', label: 'China (国内版)' },
      { url: 'https://api.minimax.io/v1', label: 'Global (海外版)' },
    ],
  },
  mistral: {
    id: 'mistral',
    name: 'Mistral AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.mistral.ai/v1',
  },
  together_ai: {
    id: 'together_ai',
    name: 'Together AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.together.xyz/v1',
  },
  siliconflow: {
    id: 'siliconflow',
    name: 'SiliconFlow',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.siliconflow.cn/v1',
    alternativeApiUrls: [
      { url: 'https://api.siliconflow.cn/v1', label: 'China (国内版)' },
      { url: 'https://api.siliconflow.com/v1', label: 'International (国际版)' },
    ],
  },
  volcengine: {
    id: 'volcengine',
    name: 'Doubao (Volcengine)',
    isBuiltIn: true,
    defaultApiUrl: 'https://ark.cn-beijing.volces.com/api/v3',
  },
  fireworks_ai: {
    id: 'fireworks_ai',
    name: 'Fireworks AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.fireworks.ai/inference/v1',
  },
  azure: {
    id: 'azure',
    name: 'Azure OpenAI',
    isBuiltIn: true,
    defaultApiUrl: 'https://{your-resource}.openai.azure.com',
  },
  spark: {
    id: 'spark',
    name: 'Spark (iFlytek)',
    isBuiltIn: true,
    defaultApiUrl: 'https://spark-api-open.xf-yun.com/v1',
  },
  perplexity: {
    id: 'perplexity',
    name: 'Perplexity AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.perplexity.ai',
  },
  jina_ai: {
    id: 'jina_ai',
    name: 'Jina AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.jina.ai',
  },
  bedrock: {
    id: 'bedrock',
    name: 'AWS Bedrock',
    isBuiltIn: true,
    defaultApiUrl: 'https://bedrock-runtime.{region}.amazonaws.com',
  },
  xiaomi_mimo: {
    id: 'xiaomi_mimo',
    name: 'Xiaomi MiMo',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.xiaomimimo.com/v1',
    alternativeApiUrls: [
      { url: 'https://api.xiaomimimo.com/v1', label: 'Standard (标准版)' },
      { url: 'https://token-plan-cn.xiaomimimo.com/v1', label: 'Token Plan (China 国内)' },
      { url: 'https://token-plan-ams.xiaomimimo.com/v1', label: 'Token Plan (Europe 欧洲)' },
      { url: 'https://token-plan-sgp.xiaomimimo.com/v1', label: 'Token Plan (Singapore 新加坡)' },
    ],
  },
  nvidia: {
    id: 'nvidia',
    name: 'Nvidia NIM',
    isBuiltIn: true,
    defaultApiUrl: 'https://integrate.api.nvidia.com/v1',
  },
  ai302: {
    id: 'ai302',
    name: '302.AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.302.ai/v1',
  },
  opencode_go: {
    id: 'opencode_go',
    name: 'OpenCode Go',
    isBuiltIn: true,
    defaultApiUrl: 'https://opencode.ai/zen/go/v1',
    dashboardUrl: 'https://opencode.ai',
    alternativeApiUrls: [
      { url: 'https://opencode.ai/zen/go/v1', label: 'Zen / Go (订阅/贡献者套餐)' },
      { url: 'https://opencode.ai/v1', label: 'Standard API (平台标准直连)' },
    ],
  },
  vercel_ai_gateway: {
    id: 'vercel_ai_gateway',
    name: 'Vercel AI Gateway',
    isBuiltIn: true,
    defaultApiUrl: 'https://ai-gateway.vercel.sh/v1',
    dashboardUrl: 'https://vercel.com/dashboard/ai-gateway',
  },
};
