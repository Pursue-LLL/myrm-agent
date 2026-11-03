import { describe, it, expect } from 'vitest';
import type { ExecutionTrace } from '@/services/statistics';
import en from '../../../locales/en.json';
import zh from '../../../locales/zh.json';
import {
  generateEvidencePackFromTrace,
  exportEvidencePackToMarkdown,
  exportEvidencePackToJson,
  type EvidencePackTranslator,
} from '../evidencePackGenerator';

type MessageNode = string | { [key: string]: MessageNode };

/** Resolves keys against a real locale bundle and fails loudly on a missing key or unfilled placeholder. */
function createTranslator(messages: { evidencePack: MessageNode }): EvidencePackTranslator {
  return (key, values = {}) => {
    let node: MessageNode | undefined = messages.evidencePack;
    for (const part of key.split('.')) {
      node = typeof node === 'object' ? node[part] : undefined;
    }
    if (typeof node !== 'string') {
      throw new Error(`Missing evidencePack key: ${key}`);
    }
    return node.replace(/\{(\w+)\}/g, (_, name: string) => {
      if (!(name in values)) {
        throw new Error(`Missing value "${name}" for evidencePack key: ${key}`);
      }
      return String(values[name]);
    });
  };
}

const tEn = createTranslator(en);
const tZh = createTranslator(zh);

describe('evidencePackGenerator', () => {
  const mockTrace: ExecutionTrace = {
    session_id: 'sess-abc-123',
    metadata: { user_id: null, agent_id: 'agent-1', task_type: null, trace_id: null },
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
        timestamp: 1015,
        error_type: 'SyntaxError',
        error: 'SyntaxError: Unexpected token in sync.ts',
      },
    ],
    human_feedback: [],
    total_events: 10,
    total_tokens: 15400,
  };

  it('correctly parses execution trace into 6 distinct steps', () => {
    const pack = generateEvidencePackFromTrace(mockTrace, tEn);
    expect(pack.sessionId).toBe('sess-abc-123');
    expect(pack.steps).toHaveLength(6);

    // Step 1: Requirements
    expect(pack.steps[0].id).toBe('requirements');
    expect(pack.steps[0].details[0]).toContain('重构数据同步模块');

    // Step 2: Architecture
    expect(pack.steps[1].id).toBe('architecture');
    expect(pack.steps[1].details[0]).toBe('Detected 1 architecture and planning dispatch phases');

    // Step 3: Initial Impl
    expect(pack.steps[2].id).toBe('initial_impl');
    expect(pack.steps[2].details[0]).toContain('file_write_tool');
    expect(pack.steps[2].details[1]).toContain('src/sync.ts');

    // Step 4: Execution & Correction
    expect(pack.steps[3].id).toBe('execution_correction');
    expect(pack.steps[3].metrics?.['Total calls']).toBe(4);
    expect(pack.steps[3].metrics?.['Failures']).toBe(1);

    // Step 5: Verification
    expect(pack.steps[4].id).toBe('verification');
    expect(pack.steps[4].details[0]).toBe('Ran 2 verification/test actions with a 50% pass rate');

    // Step 6: Takeaways
    expect(pack.steps[5].id).toBe('takeaways');
    expect(pack.steps[5].details[0]).toContain('Task closed the loop');
  });

  it('exports formatted Markdown containing all 6 steps', () => {
    const pack = generateEvidencePackFromTrace(mockTrace, tEn);
    const md = exportEvidencePackToMarkdown(pack, tEn);
    expect(md).toContain('# Project experience evidence pack (six steps):');
    expect(md).toContain('## Step 1:');
    expect(md).toContain('## Step 2:');
    expect(md).toContain('## Step 3:');
    expect(md).toContain('## Step 4:');
    expect(md).toContain('## Step 5:');
    expect(md).toContain('## Step 6:');
  });

  it('exports valid JSON representation', () => {
    const pack = generateEvidencePackFromTrace(mockTrace, tEn);
    const jsonStr = exportEvidencePackToJson(pack);
    const parsed = JSON.parse(jsonStr) as typeof pack;
    expect(parsed.sessionId).toBe(mockTrace.session_id);
    expect(parsed.steps).toHaveLength(6);
  });

  it('labels every step with a short tab title and localizes all generated copy', () => {
    const pack = generateEvidencePackFromTrace(mockTrace, tEn);
    expect(pack.steps.map((step) => step.shortTitle)).toEqual([
      'Requirements',
      'Architecture',
      'v0 draft',
      'Execution',
      'Verification',
      'Lessons',
    ]);

    const asciiTrace: ExecutionTrace = {
      ...mockTrace,
      task_input: 'Refactor the sync module',
      tool_calls: mockTrace.tool_calls.map((call) => ({ ...call, output_summary: 'split into 3 tasks' })),
    };
    const generated = generateEvidencePackFromTrace(asciiTrace, tEn).steps.flatMap((step) => [
      step.title,
      step.shortTitle,
      step.summary,
      ...step.details,
    ]);
    expect(generated.join('\n')).not.toMatch(/[\u4e00-\u9fff]/);
    expect(generated.join('\n')).not.toMatch(/\p{Extended_Pictographic}/u);
  });

  it('renders the same pack in Chinese when given the zh translator', () => {
    const pack = generateEvidencePackFromTrace(mockTrace, tZh);
    expect(pack.steps[0].shortTitle).toBe('原始需求');
    expect(pack.steps[3].metrics).toEqual({ 总调用: 4, 异常数: 1 });
    expect(exportEvidencePackToMarkdown(pack, tZh)).toContain('## 步骤 1：');
  });

  it('falls back to localized placeholders when the trace has no input, plans or edits', () => {
    const pack = generateEvidencePackFromTrace(
      { ...mockTrace, task_input: '', tool_calls: [], errors: [], outcome: 'failure', first_irrecoverable_index: 2 },
      tEn,
    );
    expect(pack.taskTitle).toBe('Untitled project task');
    expect(pack.steps[0].details).toEqual(['No explicit text input']);
    expect(pack.steps[1].details).toEqual(['Followed an end-to-end direct execution and agile response mode']);
    expect(pack.steps[2].details).toEqual(['No static file changes detected, or this was a pure conversation task']);
    expect(pack.steps[4].details).toEqual([
      'Completed inferred verification based on semantic consistency and the task-end gate',
    ]);
    expect(pack.steps[5].details).toEqual([
      'Task status is failure; focus on the interruption or the first irrecoverable error',
      'First fatal error at step index #2',
    ]);
  });
});
