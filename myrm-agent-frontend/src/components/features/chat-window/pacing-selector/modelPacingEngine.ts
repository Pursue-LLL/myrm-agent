/**
 * [INPUT]
 * - @/components/features/chat-window/pacing-selector/modelPacingTypes
 *
 * [OUTPUT]
 * - resolvePacingSpec, mapOptimizationModeToPacingTier,
 *   mapPacingTierToOptimizationMode, suggestPacingTierForPrompt
 *
 * [POS]
 * Pure computation engine for Item 191: TriTierModelExecutionPacingSelectorAndP1LatencyPresetSuite.
 * Maps abstract execution pacing tiers (fast/balanced/smart) to concrete execution specs,
 * latency budgets, and provides smart heuristics for prompt analysis.
 */

import type {
  ModelPacingTier,
  ModelPacingSpec,
  PacingSuggestion,
} from './modelPacingTypes';

export function resolvePacingSpec(tier: ModelPacingTier): ModelPacingSpec {
  switch (tier) {
    case 'fast': {
      return {
        tier: 'fast',
        displayName: '极速日常',
        subtitle: '低时延即时交付',
        description: '针对日常速记与快速改动优化，零多余推理时延，秒级极速响应',
        recommendedUseCases: ['代码改错', '文本速记', '日常问答', '文档润色'],
        typicalLatencySec: '< 5s',
        badgeColor: 'sky',
        temperatureHint: 0.3,
        thinkingBudgetTokens: 0,
      };
    }
    case 'balanced': {
      return {
        tier: 'balanced',
        displayName: '平衡推荐',
        subtitle: '品质与速度均衡',
        description: '日常主力开发推荐档位，稳健兼顾多工具调用、代码生成与响应速度',
        recommendedUseCases: ['业务功能开发', '代码重构', 'API 集成', '单测生成'],
        typicalLatencySec: '10-25s',
        badgeColor: 'emerald',
        temperatureHint: 0.5,
        thinkingBudgetTokens: 2048,
      };
    }
    case 'smart': {
      return {
        tier: 'smart',
        displayName: '深度推理',
        subtitle: '严谨推导与审计',
        description: '自动分配深度思考预算与严密思维链校验，适用于复杂架构与疑难排查',
        recommendedUseCases: ['系统架构设计', '严密数学推导', '疑难 Bug 攻坚', '全量安全审计'],
        typicalLatencySec: '30-90s',
        badgeColor: 'purple',
        temperatureHint: 0.2,
        thinkingBudgetTokens: 8192,
      };
    }
  }
}

export function mapOptimizationModeToPacingTier(optMode?: string | null): ModelPacingTier {
  if (optMode === 'speed') {
    return 'fast';
  }
  if (optMode === 'quality' || optMode === 'deep') {
    return 'smart';
  }
  return 'balanced';
}

export function mapPacingTierToOptimizationMode(
  tier: ModelPacingTier,
): 'speed' | 'balanced' | 'quality' {
  switch (tier) {
    case 'fast': {
      return 'speed';
    }
    case 'smart': {
      return 'quality';
    }
    case 'balanced': {
      return 'balanced';
    }
  }
}

const SMART_PROMPT_PATTERN =
  /(架构设计|严密证明|深度分析|数理推导|并发死锁|复杂重构|安全审计|深入思考|deep\s+reasoning|rigorous|formal\s+proof)/i;

const FAST_PROMPT_PATTERN =
  /(改错字|翻译|快速总结|速记|简单问答|润色|quick\s+summary|typo|translate)/i;

export function suggestPacingTierForPrompt(promptText: string): PacingSuggestion | null {
  const trimmed = promptText.trim();
  if (!trimmed) {
    return null;
  }

  const smartMatch = SMART_PROMPT_PATTERN.exec(trimmed);
  if (smartMatch) {
    return {
      suggestedTier: 'smart',
      matchedKeyword: smartMatch[0],
      reason: '检测到深度系统架构或严密推导需求，建议开启深度推理档',
    };
  }

  const fastMatch = FAST_PROMPT_PATTERN.exec(trimmed);
  if (fastMatch) {
    return {
      suggestedTier: 'fast',
      matchedKeyword: fastMatch[0],
      reason: '检测到日常轻量文本或速记任务，建议使用极速档以极低时延交付',
    };
  }

  return null;
}
