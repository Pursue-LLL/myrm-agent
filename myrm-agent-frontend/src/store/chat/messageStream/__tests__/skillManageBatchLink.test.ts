import { describe, expect, it } from 'vitest';

import type { ProgressItem } from '@/store/chat/types';
import { linkSkillManageBatch } from '../skillManageBatchLink';

const FIRST = 'a1b2c3d4-e5f6-4789-a012-3456789abcde';
const SECOND = 'b1b2c3d4-e5f6-4789-b012-3456789abcde';

function step(overrides: Partial<ProgressItem> = {}): ProgressItem {
  return { step_key: 'skill_manage_tool_tool', tool_name: 'skill_manage_tool', ...overrides } as ProgressItem;
}

describe('linkSkillManageBatch', () => {
  it('links the batch to the newest skill_manage step without one', () => {
    const steps = [step({ tool_call_id: 'older' }), step({ tool_call_id: 'newer' })];

    expect(linkSkillManageBatch(steps, FIRST)).toBe(true);

    expect(steps[1].skill_mutation_batch_id).toBe(FIRST);
    expect(steps[0].skill_mutation_batch_id).toBeUndefined();
  });

  it('lets consecutive batches each claim their own step', () => {
    const steps = [step({ tool_call_id: 'first-call' })];
    linkSkillManageBatch(steps, FIRST);
    steps.push(step({ tool_call_id: 'second-call' }));

    linkSkillManageBatch(steps, SECOND);

    expect(steps.map((s) => s.skill_mutation_batch_id)).toEqual([FIRST, SECOND]);
  });

  it('matches a namespaced skill_manage tool name', () => {
    const steps = [step({ tool_name: 'agent_x__skill_manage_tool' })];

    expect(linkSkillManageBatch(steps, FIRST)).toBe(true);
  });

  it('skips failed steps and steps of other tools', () => {
    const steps = [
      step({ tool_name: 'bash_code_execute_tool' }),
      step({ status: 'error' }),
      step({ status: 'cancelled' }),
    ];

    expect(linkSkillManageBatch(steps, FIRST)).toBe(false);

    expect(steps.every((s) => s.skill_mutation_batch_id === undefined)).toBe(true);
  });

  it('links nothing when there is no step to claim the batch or the id is blank', () => {
    expect(linkSkillManageBatch([], FIRST)).toBe(false);
    expect(linkSkillManageBatch([step()], '   ')).toBe(false);
  });
});
