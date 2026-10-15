import { describe, expect, it } from 'vitest';
import {
  filterMessagesByViewMode,
  formatTraceSummaryBadge,
  isEngineeringMessage,
  summarizeEngineeringTrace,
} from '../dualTrackEngine';
import type {
  EngineeringTraceDetails,
  TurnMessageItem,
} from '../dualTrackTypes';

describe('dualTrackEngine', () => {
  it('正确判定是否为工程底层执行消息', () => {
    expect(isEngineeringMessage('tool_call')).toBe(true);
    expect(isEngineeringMessage('terminal_output')).toBe(true);
    expect(isEngineeringMessage('code_diff')).toBe(true);
    expect(isEngineeringMessage('user_prompt')).toBe(false);
    expect(isEngineeringMessage('business_plan')).toBe(false);
    expect(isEngineeringMessage('business_summary')).toBe(false);
  });

  it('在业务极简模式下过滤技术噪音，在工程模式下全量保留', () => {
    const messages: TurnMessageItem[] = [
      {
        id: 'm1',
        role: 'user',
        kind: 'user_prompt',
        content: '需要一套店长端经营图表',
        timestamp: 1000,
      },
      {
        id: 'm2',
        role: 'assistant',
        kind: 'tool_call',
        content: 'executing bash python script',
        timestamp: 1010,
      },
      {
        id: 'm3',
        role: 'assistant',
        kind: 'terminal_output',
        content: 'npm install --save lucide-react',
        timestamp: 1020,
      },
      {
        id: 'm4',
        role: 'assistant',
        kind: 'business_summary',
        content: '经营图表工件已构建完毕，可直接在右侧交互试玩。',
        timestamp: 1030,
      },
    ];

    // 业务模式过滤
    const businessFiltered = filterMessagesByViewMode(messages, 'business');
    expect(businessFiltered.length).toBe(2);
    expect(businessFiltered.map((m) => m.id)).toEqual(['m1', 'm4']);

    // 工程模式保留
    const engineeringFiltered = filterMessagesByViewMode(
      messages,
      'engineering'
    );
    expect(engineeringFiltered.length).toBe(4);
  });

  it('汇总工程底层追踪指标与代码变更统计', () => {
    const trace: EngineeringTraceDetails = {
      turnId: 'turn-100',
      toolCalls: [
        { id: 'c1', toolName: 'bash', inputSummary: 'ls -la', durationMs: 12 },
        { id: 'c2', toolName: 'edit_file', inputSummary: 'edit', durationMs: 45 },
      ],
      codeDiffs: [
        {
          filePath: 'src/app.tsx',
          diffText: '+const a = 1;\n-const b = 2;',
          additions: 15,
          deletions: 3,
        },
      ],
      terminalLogs: ['Starting build...', 'Build finished in 1.2s'],
      testAssertions: [
        { id: 't1', testName: 'render test', passed: true },
        { id: 't2', testName: 'event test', passed: true },
      ],
      timestamp: Date.now(),
    };

    const summary = summarizeEngineeringTrace(trace);
    expect(summary.toolCount).toBe(2);
    expect(summary.diffCount).toBe(1);
    expect(summary.totalAdditions).toBe(15);
    expect(summary.totalDeletions).toBe(3);
    expect(summary.logLineCount).toBe(2);
    expect(summary.allTestsPassed).toBe(true);

    const badge = formatTraceSummaryBadge(summary);
    expect(badge).toContain('2 工具调用');
    expect(badge).toContain('1 文件变更 (+15/-3)');
    expect(badge).toContain('2 行日志');
    expect(badge).toContain('断言全绿');
  });

  it('处理空追踪对象', () => {
    const emptySummary = summarizeEngineeringTrace(undefined);
    expect(emptySummary.toolCount).toBe(0);
    expect(emptySummary.allTestsPassed).toBe(true);
    expect(formatTraceSummaryBadge(emptySummary)).toBe('无底层工程痕迹');
  });
});
