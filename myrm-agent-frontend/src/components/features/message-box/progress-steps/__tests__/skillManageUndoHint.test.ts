import { describe, expect, it } from 'vitest';
import type { ProgressItem } from '@/store/chat/types';
import { messageHasSkillManageUndo } from '../skillManageBatch';

describe('messageHasSkillManageUndo', () => {
  it('returns true when a step carries skill_mutation_batch_id', () => {
    const steps: ProgressItem[] = [
      {
        step_key: 'tool_skill_manage_tool',
        tool_name: 'skill_manage_tool',
        status: 'success',
        skill_mutation_batch_id: 'a1b2c3d4-e5f6-4789-a012-3456789abcde',
      },
    ];
    expect(messageHasSkillManageUndo(steps)).toBe(true);
  });

  it('returns false when batch id is missing', () => {
    const steps: ProgressItem[] = [
      {
        step_key: 'tool_skill_manage_tool',
        tool_name: 'skill_manage_tool',
        status: 'success',
      },
    ];
    expect(messageHasSkillManageUndo(steps)).toBe(false);
  });
});
