/**
 * Resolve skill_manage batch_id from progress step (structured field preferred).
 */

import type { ProgressItem } from '@/store/chat/types';
import type { TreeNode } from './treeUtils';

const SKILL_MANAGE_TOOL_SUFFIX = 'skill_manage_tool';

export function isSkillManageToolStep(step: ProgressItem): boolean {
  const name = step.tool_name?.trim() ?? '';
  return name === SKILL_MANAGE_TOOL_SUFFIX || name.endsWith(SKILL_MANAGE_TOOL_SUFFIX);
}

export function extractSkillManageBatchId(step: ProgressItem): string | null {
  if (!isSkillManageToolStep(step)) {
    return null;
  }
  if (step.status === 'error' || step.status === 'cancelled' || step.error) {
    return null;
  }
  const structured = step.skill_mutation_batch_id?.trim();
  if (structured) {
    return structured;
  }
  return null;
}

export function messageHasSkillManageUndo(steps: ProgressItem[]): boolean {
  return steps.some((step) => extractSkillManageBatchId(step) !== null);
}

/** Whether the step or any step nested under it carries an undo control. */
export function nodeHasSkillManageUndo(node: TreeNode): boolean {
  return extractSkillManageBatchId(node.step) !== null || node.children.some(nodeHasSkillManageUndo);
}
