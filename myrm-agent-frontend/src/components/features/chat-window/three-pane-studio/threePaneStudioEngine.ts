/**
 * [INPUT]
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioTypes
 *
 * [OUTPUT]
 * - findNodeById, findNodeByPath, findAncestorNodeIds,
 *   updateNodeStatusAndHighlight, buildDefaultContextTree, dispatchStudioToolEvent
 *
 * [POS]
 * Pure computation engine for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite.
 * Operates on immutable context trees, maps Agent file/memory tool paths to tree nodes,
 * computes ancestor expansion chains for instant unfolding, and broadcasts desktop events.
 */

import type {
  ContextTreeNode,
  ContextNodeType,
  NodeStatus,
  ToolHighlightEvent,
} from './threePaneStudioTypes';

export function findNodeById(
  nodes: readonly ContextTreeNode[],
  targetId: string,
): ContextTreeNode | null {
  for (const node of nodes) {
    if (node.id === targetId) {
      return node;
    }
    if (node.children && node.children.length > 0) {
      const found = findNodeById(node.children, targetId);
      if (found) {
        return found;
      }
    }
  }
  return null;
}

export function findNodeByPath(
  nodes: readonly ContextTreeNode[],
  targetPath: string,
): ContextTreeNode | null {
  const normalizedTarget = targetPath.replace(/\\/g, '/').toLowerCase();

  for (const node of nodes) {
    const nodeNormalized = node.path.replace(/\\/g, '/').toLowerCase();
    if (nodeNormalized === normalizedTarget || nodeNormalized.endsWith(`/${normalizedTarget}`)) {
      return node;
    }
    if (node.children && node.children.length > 0) {
      const found = findNodeByPath(node.children, targetPath);
      if (found) {
        return found;
      }
    }
  }
  return null;
}

export function findAncestorNodeIds(
  nodes: readonly ContextTreeNode[],
  targetId: string,
  ancestors: readonly string[] = [],
): readonly string[] {
  for (const node of nodes) {
    if (node.id === targetId) {
      return ancestors;
    }
    if (node.children && node.children.length > 0) {
      const pathWithCurrent = [...ancestors, node.id];
      const foundAncestors = findAncestorNodeIds(node.children, targetId, pathWithCurrent);
      if (foundAncestors.length > 0 || (node.children.some((c) => c.id === targetId))) {
        return foundAncestors.length > 0 ? foundAncestors : pathWithCurrent;
      }
    }
  }
  return [];
}

export function updateNodeStatusAndHighlight(
  nodes: readonly ContextTreeNode[],
  targetId: string,
  status: NodeStatus,
  activeHighlight: boolean,
): readonly ContextTreeNode[] {
  return nodes.map((node) => {
    let nextNode = node;
    if (node.id === targetId) {
      nextNode = {
        ...node,
        status,
        activeHighlight,
      };
    } else if (node.activeHighlight) {
      // 其它节点解除高亮
      nextNode = {
        ...node,
        activeHighlight: false,
      };
    }

    if (nextNode.children && nextNode.children.length > 0) {
      return {
        ...nextNode,
        children: updateNodeStatusAndHighlight(
          nextNode.children,
          targetId,
          status,
          activeHighlight,
        ),
      };
    }

    return nextNode;
  });
}

export interface RawContextInput {
  readonly memories?: readonly {
    readonly id: string;
    readonly title: string;
    readonly content: string;
  }[];
  readonly resources?: readonly {
    readonly id: string;
    readonly name: string;
    readonly path: string;
    readonly content?: string;
  }[];
  readonly skills?: readonly {
    readonly id: string;
    readonly name: string;
    readonly description: string;
  }[];
}

export function buildDefaultContextTree(input: RawContextInput = {}): readonly ContextTreeNode[] {
  const memories = input.memories ?? [];
  const resources = input.resources ?? [];
  const skills = input.skills ?? [];

  const memoryChildren: ContextTreeNode[] = memories.map((m) => ({
    id: `mem-${m.id}`,
    label: m.title,
    type: 'user_memory' as ContextNodeType,
    path: `user://memory/${m.id}`,
    content: m.content,
    status: 'idle',
  }));

  const resourceChildren: ContextTreeNode[] = resources.map((r) => ({
    id: `res-${r.id}`,
    label: r.name,
    type: 'resource' as ContextNodeType,
    path: r.path,
    content: r.content,
    status: 'idle',
  }));

  const skillChildren: ContextTreeNode[] = skills.map((s) => ({
    id: `skill-${s.id}`,
    label: s.name,
    type: 'skill' as ContextNodeType,
    path: `skills://${s.id}`,
    content: s.description,
    status: 'idle',
  }));

  return [
    {
      id: 'root-user-memory',
      label: '用户个性化记忆 (User Memory)',
      type: 'user_memory',
      path: 'user://memory',
      children: memoryChildren,
    },
    {
      id: 'root-workspace-resources',
      label: '项目资产与文件 (Workspace Resources)',
      type: 'resource',
      path: '/workspace',
      children: resourceChildren,
    },
    {
      id: 'root-agent-skills',
      label: '智能体技能集 (Agent Skills)',
      type: 'skill',
      path: 'skills://',
      children: skillChildren,
    },
  ];
}

export function dispatchStudioToolEvent(event: ToolHighlightEvent): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    const customEvent = new CustomEvent('myrm:studio-tool-highlight', {
      detail: event,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(customEvent);
    return true;
  } catch {
    return false;
  }
}
