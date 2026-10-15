import { describe, expect, it } from 'vitest';
import type { ProgressItem } from '@/store/chat/types';
import { extractSkillManageBatchId } from '../skillManageBatch';

const BATCH_ID = 'a1b2c3d4-e5f6-4789-a012-3456789abcde';

const baseStep = (overrides: Partial<ProgressItem> = {}): ProgressItem => ({
  step_key: 'tool_skill_manage_tool',
  tool_name: 'skill_manage_tool',
  status: 'success',
  skill_mutation_batch_id: BATCH_ID,
  ...overrides,
});

describe('extractSkillManageBatchId', () => {
  it('returns structured skill_mutation_batch_id', () => {
    expect(extractSkillManageBatchId(baseStep())).toBe(BATCH_ID);
  });

  it('ignores failed steps', () => {
    expect(extractSkillManageBatchId(baseStep({ status: 'error' }))).toBeNull();
  });

  it('ignores other tools', () => {
    expect(extractSkillManageBatchId(baseStep({ tool_name: 'bash_code_execute_tool' }))).toBeNull();
  });

  it('returns null when structured id is missing', () => {
    expect(extractSkillManageBatchId(baseStep({ skill_mutation_batch_id: undefined }))).toBeNull();
  });
});
