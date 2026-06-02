import { ApiError } from '@/lib/api';
import type { TreeNode } from '@/services/wikiService';

export function filterFolderNodes(nodes: TreeNode[]): TreeNode[] {
  return nodes
    .filter((node) => node.is_dir)
    .map((node) => ({
      ...node,
      children: node.children ? filterFolderNodes(node.children) : undefined,
    }));
}

export function findTreeNodeById(nodes: TreeNode[], targetId: string): TreeNode | null {
  for (const node of nodes) {
    if (node.id === targetId) return node;
    if (node.children) {
      const found = findTreeNodeById(node.children, targetId);
      if (found) return found;
    }
  }
  return null;
}

/** Count files and subfolders inside a folder (excluding the folder itself). */
export function countDescendantItems(nodes: TreeNode[], folderId: string): number {
  const folder = findTreeNodeById(nodes, folderId);
  if (!folder?.children?.length) return 0;

  const walk = (items: TreeNode[]): number =>
    items.reduce((sum, item) => sum + 1 + (item.children ? walk(item.children) : 0), 0);

  return walk(folder.children);
}

export function resolveCreateParentFolder(
  focusedNodeId: string | undefined,
  isDir: boolean | undefined,
): string | null {
  if (!focusedNodeId) return null;
  if (isDir) return focusedNodeId;
  const parent = focusedNodeId.split('/').slice(0, -1).join('/');
  return parent || null;
}

export function isNotFoundApiError(error: unknown): boolean {
  return error instanceof ApiError && error.code === 404;
}

export function getWikiOperationErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message || fallback;
  }
  return fallback;
}
