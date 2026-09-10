import { describe, it, expect } from 'vitest';
import type { ExecutionTrace } from '@/services/statistics';
import {
  generateEvidencePackFromTrace,
  exportEvidencePackToMarkdown,
  exportEvidencePackToJson,
} from '../evidencePackGenerator';

describe('evidencePackGenerator', () => {
  const mockTrace: ExecutionTrace = {
    session_id: 'sess-abc-123',
    metadata: { agent_id: 'agent-1' },
    outcome: 'success',
    start_time: 1000,
    end_time: 1050,
    duration_ms: 50000,
    task_input: '重构数据同步模块并验证单元测试覆盖',
    output: '重构已完成并通过全部测试',
    tool_calls: [
      {
        sequence: 1,
        tool_name: 'task_planning',
        start_time: 1001,
        end_time: 1002,
        duration_ms: 1000,
        success: true,
        error: null,
        output_summary: '拆解为3个核心任务',
      },
      {
        sequence: 2,
        tool_name: 'file_write_tool',
        start_time: 1005,
        end_time: 1008,
        duration_ms: 3000,
        success: true,
        error: null,
        input_data: { path: 'src/sync.ts' },
      },
      {
        sequence: 3,
        tool_name: 'bash_code_execute_tool',
        start_time: 1010,
        end_time: 1015,
        duration_ms: 5000,
        success: false,
        error: 'SyntaxError: Unexpected token',
      },
      {
        sequence: 4,
        tool_name: 'pytest_runner',
        start_time: 1020,
        end_time: 1030,
        duration_ms: 10000,
        success: true,
        error: null,
      },
    ],
    llm_calls: [],
    errors: [
      {
        sequence: 1,
        timestamp: 1015,
        error_type: 'SyntaxError',
        message: 'SyntaxError: Unexpected token in sync.ts',
        recoverable: true,
      },
    ],
    human_feedback: [],
    total_events: 10,
    total_tokens: 15400,
  };

  it('correctly parses execution trace into 6 distinct steps', () => {
    const pack = generateEvidencePackFromTrace(mockTrace);
    expect(pack.sessionId).toBe('sess-abc-123');
    expect(pack.steps).toHaveLength(6);

    // Step 1: Requirements
    expect(pack.steps[0].id).toBe('requirements');
    expect(pack.steps[0].details[0]).toContain('重构数据同步模块');

    // Step 2: Architecture
    expect(pack.steps[1].id).toBe('architecture');
    expect(pack.steps[1].details[0]).toContain('架构与规划');

    // Step 3: Initial Impl
    expect(pack.steps[2].id).toBe('initial_impl');
    expect(pack.steps[2].details[0]).toContain('file_write_tool');
    expect(pack.steps[2].details[1]).toContain('src/sync.ts');

    // Step 4: Execution & Correction
    expect(pack.steps[3].id).toBe('execution_correction');
    expect(pack.steps[3].metrics?.['总调用']).toBe(4);
    expect(pack.steps[3].metrics?.['异常数']).toBe(1);

    // Step 5: Verification
    expect(pack.steps[4].id).toBe('verification');
    expect(pack.steps[4].details[0]).toContain('验证/测试动作');

    // Step 6: Takeaways
    expect(pack.steps[5].id).toBe('takeaways');
    expect(pack.steps[5].details[0]).toContain('任务完整闭环');
  });

  it('exports formatted Markdown containing all 6 steps', () => {
    const pack = generateEvidencePackFromTrace(mockTrace);
    const md = exportEvidencePackToMarkdown(pack);
    expect(md).toContain('# 📋 项目实战六步经验证据包');
    expect(md).toContain('## Step 1:');
    expect(md).toContain('## Step 2:');
    expect(md).toContain('## Step 3:');
    expect(md).toContain('## Step 4:');
    expect(md).toContain('## Step 5:');
    expect(md).toContain('## Step 6:');
  });

  it('exports valid JSON representation', () => {
    const pack = generateEvidencePackFromTrace(mockTrace);
    const jsonStr = exportEvidencePackToJson(pack);
    const parsed = JSON.parse(jsonStr) as typeof pack;
    expect(parsed.sessionId).toBe(mockTrace.session_id);
    expect(parsed.steps).toHaveLength(6);
  });
});
