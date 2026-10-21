import { describe, it, expect } from 'vitest';
import {
  detectP0UrgencyIntent,
  inspectTranscriptForDeviation,
  createWatchdogLogEntry,
} from '../p0UrgencyWatchdogEngine';

describe('p0UrgencyWatchdogEngine', () => {
  it('自然语言正确识别 P0 紧急模式意图', () => {
    expect(detectP0UrgencyIntent('这是一个很急的任务，这是 P0！')).toBe(true);
    expect(detectP0UrgencyIntent('请立刻处理，这是p0')).toBe(true);
    expect(detectP0UrgencyIntent('生产环境故障，最高优先级上线')).toBe(true);
    expect(detectP0UrgencyIntent('urgent p0 fix needed now')).toBe(true);

    expect(detectP0UrgencyIntent('请帮我把这个函数重构成 TypeScript')).toBe(
      false
    );
    expect(detectP0UrgencyIntent('')).toBe(false);
  });

  it('审查轨迹在无偏离时返回 passed 状态', () => {
    const emptyTurns: string[] = [];
    expect(inspectTranscriptForDeviation(emptyTurns)).toEqual({
      hasDeviation: false,
      status: 'passed',
    });

    const normalTurns = [
      'user: 请帮我查阅配置',
      'assistant: 正在读取',
      'tool_call: view_file config.json',
      'assistant: 配置已读取完成',
      'tool_call: write_to_file app.ts',
    ];
    const normalResult = inspectTranscriptForDeviation(normalTurns);
    expect(normalResult.hasDeviation).toBe(false);
    expect(normalResult.status).toBe('passed');
  });

  it('检测到同一工具连续调用 3 次以上时触发 steered 状态并注入纠偏指令', () => {
    const loopingTurns = [
      'tool_call: view_file a.ts',
      'assistant: 查看结果不理想',
      'tool_call: view_file a.ts',
      'assistant: 再次核对',
      'tool_call: view_file a.ts',
    ];

    const result = inspectTranscriptForDeviation(loopingTurns);
    expect(result.hasDeviation).toBe(true);
    expect(result.status).toBe('steered');
    expect(result.reason).toContain('view_file');
    expect(result.reason).toContain('3 次');
    expect(result.steeringPrompt).toContain('【P0 看门狗即时纠偏】');
  });

  it('检测到多次连续报错时触发 warning 告警', () => {
    const errorTurns = [
      'tool_call: run_command npm test',
      'output: error: compilation failed in module x',
      'tool_call: run_command npm test',
      'output: failed: test runner exited with error',
    ];

    const result = inspectTranscriptForDeviation(errorTurns);
    expect(result.hasDeviation).toBe(true);
    expect(result.status).toBe('warning');
    expect(result.reason).toContain('连续报错');
    expect(result.steeringPrompt).toContain('【P0 看门狗警告】');
  });

  it('正确构造看门狗审计日志条目', () => {
    const analysis = inspectTranscriptForDeviation([
      'tool_call: view_file x.ts',
      'tool_call: view_file x.ts',
      'tool_call: view_file x.ts',
    ]);

    const log = createWatchdogLogEntry(1, analysis);
    expect(log.id).toContain('wd-log-');
    expect(log.inspectionRound).toBe(1);
    expect(log.status).toBe('steered');
    expect(log.injectedSteeringPrompt).toBeDefined();
  });
});
