/**
 * [INPUT]
 * - @/components/features/chat-window/context-hud/contextHudTypes
 *
 * [OUTPUT]
 * - computeContextHudMetrics, formatTokenMetric, formatPercentage,
 *   diagnoseCacheMiss, resolveWatermarkColor
 *
 * [POS]
 * Pure computation engine for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite.
 * Computes 6-metric HUD telemetry, evaluates watermark thresholds,
 * and performs heuristic root-cause attribution for prompt cache misses.
 */

import type {
  ContextWatermarkLevel,
  AutoCompactState,
  ContextHudMetrics,
  CacheAttributionReport,
} from './contextHudTypes';

export const DEFAULT_CONTEXT_LIMIT = 128000;

export function formatTokenMetric(tokens: number): string {
  if (tokens <= 0) {
    return '0';
  }
  if (tokens < 1000) {
    return tokens.toString();
  }
  if (tokens < 1000000) {
    const k = Math.round(tokens / 100) / 10;
    return `${k.toFixed(1)}k`;
  }
  const m = Math.round(tokens / 10000) / 100;
  return `${m.toFixed(2)}M`;
}

export function formatPercentage(pct: number): string {
  return `${Math.max(0, Math.min(100, Math.round(pct)))}%`;
}

export function computeContextHudMetrics(params: {
  inputTokens: number;
  outputTokens: number;
  cachedReadTokens: number;
  contextLimit?: number;
  autoCompactState?: AutoCompactState;
}): ContextHudMetrics {
  const inputTokens = Math.max(0, params.inputTokens);
  const outputTokens = Math.max(0, params.outputTokens);
  const cachedReadTokens = Math.max(0, Math.min(inputTokens, params.cachedReadTokens));
  const contextLimit = params.contextLimit && params.contextLimit > 0 ? params.contextLimit : DEFAULT_CONTEXT_LIMIT;
  const usedTokens = inputTokens + outputTokens;

  const cacheHitRate = inputTokens > 0 ? Math.min(100, Math.round((cachedReadTokens / inputTokens) * 100)) : 0;
  const watermarkPercentage = Math.min(100, Math.round((usedTokens / contextLimit) * 100));

  let watermarkLevel: ContextWatermarkLevel = 'healthy';
  if (watermarkPercentage > 85) {
    watermarkLevel = 'critical';
  } else if (watermarkPercentage >= 60) {
    watermarkLevel = 'warning';
  }

  return {
    inputTokens,
    outputTokens,
    cachedReadTokens,
    cacheHitRate,
    contextLimit,
    usedTokens,
    watermarkPercentage,
    watermarkLevel,
    autoCompactState: params.autoCompactState ?? 'ready',
  };
}

export function diagnoseCacheMiss(params: {
  inputTokens: number;
  cachedReadTokens: number;
  turnIndex: number;
  hasDynamicTime?: boolean;
  hasToolMutation?: boolean;
  hasSystemPromptChanged?: boolean;
}): CacheAttributionReport {
  const { inputTokens, cachedReadTokens, turnIndex } = params;

  // 1. 首轮冷启动判断
  if (turnIndex <= 1 && cachedReadTokens === 0) {
    return {
      reason: 'first_turn_cold',
      reasonTitle: '首轮冷启动构建中',
      description: '首轮请求正在向模型 Provider 写入初始前缀缓存切片，下轮起将稳定生效。',
      suggestion: '无需优化，保持对话前缀固定即可。',
      estimatedTokenSavings: 0,
      score: 95,
    };
  }

  // 2. 动态时间戳破坏前缀哈希
  if (params.hasDynamicTime) {
    return {
      reason: 'timestamp_jitter',
      reasonTitle: '动态时间戳导致前缀抖动',
      description: '检测到 System Prompt 中注入了秒级实时时间戳，导致前缀哈希每次变动全量失效。',
      suggestion: '将实时时间戳移出 System Prompt，或仅按自然日/小时粗粒度量化。',
      estimatedTokenSavings: Math.round(inputTokens * 0.7),
      score: 40,
    };
  }

  // 3. 系统提示词变更
  if (params.hasSystemPromptChanged) {
    return {
      reason: 'system_prompt_drift',
      reasonTitle: '系统提示词发生动态漂移',
      description: 'System Prompt 内容或引导规则发生改变，破坏了既有前缀哈希链。',
      suggestion: '固化静态 System Prompt 前缀，将可变会话参数下沉至末尾。',
      estimatedTokenSavings: Math.round(inputTokens * 0.8),
      score: 45,
    };
  }

  // 4. 工具 Schema 变更
  if (params.hasToolMutation) {
    return {
      reason: 'tool_schema_mutation',
      reasonTitle: '工具列表定义动态变动',
      description: '注入模型的 Tool Definitions 列表顺序或 Schema 结构发生变动。',
      suggestion: '对工具定义清单实施固定字典序排序后再序列化。',
      estimatedTokenSavings: Math.round(inputTokens * 0.5),
      score: 50,
    };
  }

  // 5. 最小切片未对齐 (如 < 1024 Tokens)
  if (inputTokens < 1024 && cachedReadTokens === 0) {
    return {
      reason: 'boundary_misalignment',
      reasonTitle: '未达到最小缓存门槛',
      description: '当前输入前缀不足 1024 Tokens，未达到 Provider 自动切片缓存起征线。',
      suggestion: '短任务无需干预，长任务累积后将自动切入缓存加速。',
      estimatedTokenSavings: 0,
      score: 85,
    };
  }

  // 6. 正常命中
  const hitRatio = inputTokens > 0 ? cachedReadTokens / inputTokens : 0;
  if (hitRatio >= 0.5) {
    return {
      reason: 'none',
      reasonTitle: '缓存链路工作极佳',
      description: `Prompt Cache 命中率达 ${Math.round(hitRatio * 100)}%，有效削减延迟与计费。`,
      suggestion: '继续保持当前前缀结构。',
      estimatedTokenSavings: cachedReadTokens,
      score: 100,
    };
  }

  return {
    reason: 'none',
    reasonTitle: '缓存平稳运行中',
    description: `已成功读取 ${cachedReadTokens} 缓存 Tokens。`,
    suggestion: '保持对话前缀连贯。',
    estimatedTokenSavings: cachedReadTokens,
    score: 80,
  };
}

export function resolveWatermarkColor(level: ContextWatermarkLevel): {
  textClass: string;
  badgeClass: string;
  progressClass: string;
} {
  switch (level) {
    case 'healthy': {
      return {
        textClass: 'text-emerald-500',
        badgeClass: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
        progressClass: '[&::-webkit-progress-value]:bg-emerald-500 [&::-moz-progress-bar]:bg-emerald-500',
      };
    }
    case 'warning': {
      return {
        textClass: 'text-amber-500',
        badgeClass: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
        progressClass: '[&::-webkit-progress-value]:bg-amber-500 [&::-moz-progress-bar]:bg-amber-500',
      };
    }
    case 'critical': {
      return {
        textClass: 'text-rose-500',
        badgeClass: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
        progressClass: '[&::-webkit-progress-value]:bg-rose-500 [&::-moz-progress-bar]:bg-rose-500',
      };
    }
  }
}
