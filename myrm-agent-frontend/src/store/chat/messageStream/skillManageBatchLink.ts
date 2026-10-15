/**
 * [INPUT]
 * @/store/chat/types::ProgressItem (POS: Task Steps entry of a message)
 *
 * [OUTPUT]
 * linkSkillManageBatch
 *
 * [POS]
 * The server announces the batch a skill_manage call committed on a tool_end event, because the stream only
 * carries the call's arguments and never its result. This links that batch to the step still waiting for one,
 * so Undo is offered while the turn is live. Mirrors app/services/skills/mutation_batch_stream.py
 * (`link_batch_to_step`), which does the same for the persisted message.
 */

import type { ProgressItem } from '@/store/chat/types';

const SKILL_MANAGE_TOOL_SUFFIX = 'skill_manage_tool';

/** Links `batchId` to the newest skill_manage step that neither failed nor owns a batch. Returns whether one was linked. */
export function linkSkillManageBatch(steps: ProgressItem[], batchId: string): boolean {
  const id = batchId.trim();
  if (!id) {
    return false;
  }
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    const step = steps[index];
    const awaitingBatch =
      (step.tool_name ?? '').endsWith(SKILL_MANAGE_TOOL_SUFFIX) &&
      !step.skill_mutation_batch_id &&
      step.status !== 'error' &&
      step.status !== 'cancelled';
    if (awaitingBatch) {
      step.skill_mutation_batch_id = id;
      return true;
    }
  }
  return false;
}
