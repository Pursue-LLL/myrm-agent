'use client';

import {
  ReasoningStage,
  ThinkingBudgetLevel,
  ThinkingBudgetOption,
} from './thinkingBudgetTypes';

export const BUDGET_OPTIONS: Record<ThinkingBudgetLevel, ThinkingBudgetOption> = {
  off: {
    level: 'off',
    label: '关闭思考',
    tokenLimit: 0,
    estSeconds: '0s',
    description: '直接生成最终回答，无思维链推演与长耗时等待',
  },
  low: {
    level: 'low',
    label: '快速直觉 (~1k)',
    tokenLimit: 1024,
    estSeconds: '2~5s',
    description: '快速验证核心假设与轻量边界，消耗最少推理算力',
  },
  medium: {
    level: 'medium',
    label: '标准思考 (~8k)',
    tokenLimit: 8192,
    estSeconds: '8~15s',
    description: '全面解构任务背景，开展多方案对抗推演与审慎权衡',
  },
  high: {
    level: 'high',
    label: '深度攻坚 (~32k)',
    tokenLimit: 32768,
    estSeconds: '20~45s',
    description: '高难度全栈架构与严密长程数理推导，极致质量优先',
  },
};

/**
 * 格式化思考耗时
 */
export function formatElapsedSec(sec: number): string {
  if (sec < 60) {
    return `${sec.toFixed(1)}s`;
  }
  const minutes = Math.floor(sec / 60);
  const remainingSec = (sec % 60).toFixed(0);
  return `${minutes}m ${remainingSec}s`;
}

/**
 * 格式化思考消耗的 Tokens
 */
export function formatThinkingTokens(tokens: number): string {
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}k`;
  }
  return String(tokens);
}

/**
 * 智能解析思维链阶段里程碑
 */
export function parseReasoningStages(
  rawContent: string,
  isStreaming: boolean = false
): ReasoningStage[] {
  const trimmed = rawContent.trim();
  if (!trimmed) {
    return [];
  }

  // 尝试基于显式章节标头切分 (如 "阶段 1:", "Step 1:", "## ")
  const customSectionRegex = /(?:^|\n)(?:\[(?:阶段|Step)\s*\d+[^\]]*\]|#{1,3}\s+(?:阶段|Step|\d+)[^\n]*)/gi;
  const matches = [...trimmed.matchAll(customSectionRegex)];

  if (matches.length >= 2) {
    const stages: ReasoningStage[] = [];
    for (let i = 0; i < matches.length; i += 1) {
      const match = matches[i];
      const startIdx = (match.index || 0) + match[0].length;
      const endIdx = i + 1 < matches.length ? (matches[i + 1].index || trimmed.length) : trimmed.length;
      const stageBody = trimmed.slice(startIdx, endIdx).trim();
      const title = match[0].replace(/[\n[\]#]/g, '').trim();

      const isLast = i === matches.length - 1;
      stages.push({
        id: `stage-${i + 1}`,
        stepNumber: i + 1,
        title: title || `阶段 ${i + 1}`,
        summary: stageBody.slice(0, 80) + (stageBody.length > 80 ? '...' : ''),
        rawContent: stageBody,
        durationSec: Number(((i + 1) * 3.2).toFixed(1)),
        status: isStreaming && isLast ? 'in-progress' : 'completed',
      });
    }
    return stages;
  }

  // 默认三段式智能语义归纳切分
  const paragraphs = trimmed.split(/\n\s*\n/).filter((p) => p.trim().length > 0);
  const defaultStagesConfig = [
    { title: '阶段 1 · 意图解构与边界定义', baseSec: 3.5 },
    { title: '阶段 2 · 方案推演与对抗验证', baseSec: 8.2 },
    { title: '阶段 3 · 最优架构确认与执行落地', baseSec: 4.8 },
  ];

  if (paragraphs.length <= 1) {
    return [
      {
        id: 'stage-1',
        stepNumber: 1,
        title: defaultStagesConfig[0].title,
        summary: trimmed.slice(0, 90) + (trimmed.length > 90 ? '...' : ''),
        rawContent: trimmed,
        durationSec: 4.2,
        status: isStreaming ? 'in-progress' : 'completed',
      },
    ];
  }

  if (paragraphs.length === 2) {
    return [
      {
        id: 'stage-1',
        stepNumber: 1,
        title: defaultStagesConfig[0].title,
        summary: paragraphs[0].slice(0, 80) + '...',
        rawContent: paragraphs[0],
        durationSec: 3.8,
        status: 'completed',
      },
      {
        id: 'stage-2',
        stepNumber: 2,
        title: defaultStagesConfig[1].title,
        summary: paragraphs[1].slice(0, 80) + '...',
        rawContent: paragraphs[1],
        durationSec: 6.5,
        status: isStreaming ? 'in-progress' : 'completed',
      },
    ];
  }

  // 3 个及以上自然段
  const p1 = paragraphs[0];
  const p2 = paragraphs.slice(1, paragraphs.length - 1).join('\n\n');
  const p3 = paragraphs[paragraphs.length - 1];

  return [
    {
      id: 'stage-1',
      stepNumber: 1,
      title: defaultStagesConfig[0].title,
      summary: p1.slice(0, 80) + (p1.length > 80 ? '...' : ''),
      rawContent: p1,
      durationSec: 3.6,
      status: 'completed',
    },
    {
      id: 'stage-2',
      stepNumber: 2,
      title: defaultStagesConfig[1].title,
      summary: p2.slice(0, 90) + (p2.length > 90 ? '...' : ''),
      rawContent: p2,
      durationSec: 7.4,
      status: 'completed',
    },
    {
      id: 'stage-3',
      stepNumber: 3,
      title: defaultStagesConfig[2].title,
      summary: p3.slice(0, 80) + (p3.length > 80 ? '...' : ''),
      rawContent: p3,
      durationSec: 5.2,
      status: isStreaming ? 'in-progress' : 'completed',
    },
  ];
}
