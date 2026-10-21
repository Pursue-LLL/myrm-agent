/**
 * P0 Urgency Watchdog & Steering Engine
 * P0 紧急高频纠偏看门狗、执行轨迹偏离检测与实时原地指令注入引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 纯函数设计，高可测性。
 */

import { P0WatchdogLogEntry } from './templateBotTypes';

export const P0_INTENT_KEYWORDS: readonly string[] = [
  '这是p0',
  '这是 p0',
  'p0紧急',
  '最高优先级',
  'urgent p0',
  'emergency p0',
  'p0 cruise',
];

/**
 * 自然语言检测用户消息是否包含 P0 紧急模式触发意图
 */
export function detectP0UrgencyIntent(userMessage: string): boolean {
  if (!userMessage || userMessage.trim() === '') {
    return false;
  }

  const normalized = userMessage.toLowerCase().trim();
  for (const keyword of P0_INTENT_KEYWORDS) {
    if (normalized.includes(keyword)) {
      return true;
    }
  }

  return false;
}

export interface DeviationAnalysisResult {
  hasDeviation: boolean;
  status: 'passed' | 'warning' | 'steered';
  reason?: string;
  steeringPrompt?: string;
}

/**
 * 审查近程执行轨迹，检测死循环空转或逻辑偏离
 */
export function inspectTranscriptForDeviation(
  recentTurns: readonly string[]
): DeviationAnalysisResult {
  if (recentTurns.length === 0) {
    return {
      hasDeviation: false,
      status: 'passed',
    };
  }

  // 1. 检测是否包含重复工具调用特征（如同一工具重复出现 3 次以上）
  const toolRepeatCounts: Record<string, number> = {};
  for (const turn of recentTurns) {
    const match = turn.match(/tool_call:\s*([a-zA-Z0-9_]+)/i);
    if (match && match[1]) {
      const toolName = match[1];
      toolRepeatCounts[toolName] = (toolRepeatCounts[toolName] || 0) + 1;
    }
  }

  for (const [toolName, count] of Object.entries(toolRepeatCounts)) {
    if (count >= 3) {
      return {
        hasDeviation: true,
        status: 'steered',
        reason: `检测到工具 [${toolName}] 出现 ${count} 次连续重复调用，陷入无效空转。`,
        steeringPrompt: `【P0 看门狗即时纠偏】系统检测到工具 [${toolName}] 已重复调用 ${count} 次。请立即停止轮询，直接综合当前已有信息输出最小可行的核心交付物！`,
      };
    }
  }

  // 2. 检测轨迹中是否频繁出现错误重试（如持续异常报错）
  let errorCount = 0;
  for (const turn of recentTurns) {
    if (turn.toLowerCase().includes('error:') || turn.toLowerCase().includes('failed:')) {
      errorCount += 1;
    }
  }

  if (errorCount >= 2) {
    return {
      hasDeviation: true,
      status: 'warning',
      reason: `近程轨迹捕获到 ${errorCount} 处连续报错，推进受阻。`,
      steeringPrompt: '【P0 看门狗警告】检测到多次执行报错，请优先进行根因分析并启用最小化替代路径，避免死磕单一错误分支！',
    };
  }

  return {
    hasDeviation: false,
    status: 'passed',
  };
}

/**
 * 构造看门狗巡检审计日志记录
 */
export function createWatchdogLogEntry(
  round: number,
  analysis: DeviationAnalysisResult
): P0WatchdogLogEntry {
  return {
    id: `wd-log-${Date.now()}-${round}`,
    timestamp: Date.now(),
    inspectionRound: round,
    status: analysis.status,
    detectedIssue: analysis.reason,
    injectedSteeringPrompt: analysis.steeringPrompt,
  };
}
