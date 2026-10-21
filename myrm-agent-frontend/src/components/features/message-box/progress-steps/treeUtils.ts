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
    if (!node) {
      return;
    }

    const parent = step.parent_step_key ? nodeMap.get(step.parent_step_key) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  });

  return roots;
}

// A turn with more than FOLD_THRESHOLD top-level steps shows its first FOLD_HEAD and last FOLD_TAIL steps;
// the stretch in between sits behind a "show more" bar.
const FOLD_THRESHOLD = 8;
const FOLD_HEAD = 2;
const FOLD_TAIL = 3;

export interface FoldedRoots {
  head: TreeNode[];
  folded: TreeNode[];
  tail: TreeNode[];
}

/** Splits the top-level steps into visible head, folded stretch and visible tail; null when the turn shows in full. */
export function foldRoots(roots: TreeNode[]): FoldedRoots | null {
  if (roots.length <= FOLD_THRESHOLD) {
    return null;
  }
  return {
    head: roots.slice(0, FOLD_HEAD),
    folded: roots.slice(FOLD_HEAD, roots.length - FOLD_TAIL),
    tail: roots.slice(roots.length - FOLD_TAIL),
  };
}
