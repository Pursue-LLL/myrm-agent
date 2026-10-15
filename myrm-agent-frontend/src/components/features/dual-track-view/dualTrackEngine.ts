/**
 * dualTrackEngine.ts
 * 业务极简模式 vs 深度工程模式消息过滤与底层工程追踪统计纯函数引擎
 */

import type {
  DualTrackViewMode,
  EngineeringTraceDetails,
  EngineeringTraceSummary,
  TurnMessageItem,
  TurnMessageKind,
} from './dualTrackTypes';

export function isEngineeringMessage(kind: TurnMessageKind): boolean {
  return (
    kind === 'tool_call' ||
    kind === 'terminal_output' ||
    kind === 'code_diff'
  );
}

export function filterMessagesByViewMode(
  messages: TurnMessageItem[],
  mode: DualTrackViewMode
): TurnMessageItem[] {
  if (mode === 'engineering') {
    return messages;
  }

  // 业务极简模式：过滤纯工程底层技术细节，保留用户沟通、澄清、计划与业务结论
  return messages.filter((msg) => {
    return !isEngineeringMessage(msg.kind);
  });
}

export function summarizeEngineeringTrace(
  trace: EngineeringTraceDetails | undefined
): EngineeringTraceSummary {
  if (trace === undefined) {
    return {
      toolCount: 0,
      diffCount: 0,
      logLineCount: 0,
      totalAdditions: 0,
      totalDeletions: 0,
      allTestsPassed: true,
    };
  }

  const toolCount = trace.toolCalls.length;
  const diffCount = trace.codeDiffs.length;
  const logLineCount = trace.terminalLogs.length;

  let totalAdditions = 0;
  let totalDeletions = 0;
  for (const diff of trace.codeDiffs) {
    totalAdditions += diff.additions;
    totalDeletions += diff.deletions;
  }

  let allTestsPassed = true;
  for (const assertion of trace.testAssertions) {
    if (!assertion.passed) {
      allTestsPassed = false;
      break;
    }
  }

  return {
    toolCount,
    diffCount,
    logLineCount,
    totalAdditions,
    totalDeletions,
    allTestsPassed,
  };
}

export function formatTraceSummaryBadge(
  summary: EngineeringTraceSummary
): string {
  const parts: string[] = [];

  if (summary.toolCount > 0) {
    parts.push(`${summary.toolCount} 工具调用`);
  }

  if (summary.diffCount > 0) {
    parts.push(
      `${summary.diffCount} 文件变更 (+${summary.totalAdditions}/-${summary.totalDeletions})`
    );
  }

  if (summary.logLineCount > 0) {
    parts.push(`${summary.logLineCount} 行日志`);
  }

  if (parts.length === 0) {
    return '无底层工程痕迹';
  }

  const testStatus = summary.allTestsPassed ? '断言全绿' : '存在测试告警';
  return `${parts.join(' · ')} · ${testStatus}`;
}
