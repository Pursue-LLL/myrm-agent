import type { ProgressItem } from '@/store/chat/types';

export interface TreeNode {
  step: ProgressItem;
  originalIndex: number;
  children: TreeNode[];
}

export function buildTree(steps: ProgressItem[]): TreeNode[] {
  const nodeMap = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];

  // 辅助函数：获取节点的唯一标识符（优先使用 tool_call_id 解决并发工具覆盖问题）
  const getUniqueKey = (step: ProgressItem) => step.tool_call_id || step.step_key;

  // First pass: create nodes
  steps.forEach((step, index) => {
    const node: TreeNode = {
      step,
      originalIndex: index,
      children: [],
    };
    const uniqueKey = getUniqueKey(step);
    if (uniqueKey) {
      nodeMap.set(uniqueKey, node);
    }
  });

  // Second pass: build tree
  steps.forEach((step) => {
    const uniqueKey = getUniqueKey(step);
    const node = uniqueKey ? nodeMap.get(uniqueKey) : undefined;
    if (!node) return;

    if (step.parent_step_key && nodeMap.has(step.parent_step_key)) {
      const parent = nodeMap.get(step.parent_step_key)!;
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  });

  return roots;
}
