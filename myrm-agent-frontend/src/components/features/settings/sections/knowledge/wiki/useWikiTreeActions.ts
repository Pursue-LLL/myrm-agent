'use client';

/**
 * [INPUT] services/wikiService (POS: Wiki REST 客户端)
 * [OUTPUT] useWikiTreeActions: 树节点拖拽移动、新建文件夹、重命名与弹窗处理
 * [POS] Settings Wiki 目录与节点结构调整 Hook
 */
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { wikiService } from '@/services/wikiService';
import { getWikiOperationErrorMessage, resolveCreateParentFolder } from './wikiTreeUtils';
import type { TreeApi } from 'react-arborist';
import type { TreeNode } from '@/services/wikiService';

export interface UseWikiTreeActionsProps {
  treeRef: React.RefObject<TreeApi<TreeNode> | null>;
  agentScopeId?: string;
  fetchTree: () => Promise<void>;
  createParentFolder: string | null;
  setCreateParentFolder: (folder: string | null) => void;
  setDialogMode: (mode: 'create' | 'rename') => void;
  setDialogInput: (input: string) => void;
  setDialogOpen: (open: boolean) => void;
  dialogTargetId: string | null;
  setDialogTargetId: (id: string | null) => void;
  dialogMode: 'create' | 'rename';
  dialogInput: string;
}

export function useWikiTreeActions({
  treeRef,
  agentScopeId,
  fetchTree,
  createParentFolder,
  setCreateParentFolder,
  setDialogMode,
  setDialogInput,
  setDialogOpen,
  dialogTargetId,
  setDialogTargetId,
  dialogMode,
  dialogInput,
}: UseWikiTreeActionsProps) {
  const t = useTranslations('settings.wiki.concepts');

  const handleMove = async ({ dragIds, parentId }: { dragIds: string[]; parentId: string | null; index: number }) => {
    const sourceId = dragIds[0];
    if (!sourceId) {
      return;
    }

    const sourceName = sourceId.split('/').pop() || sourceId;
    const targetPath = parentId ? `${parentId}/${sourceName}` : sourceName;

    if (sourceId === targetPath) {
      return;
    }

    try {
      await wikiService.moveNode(sourceId, targetPath, agentScopeId);
      toast.success(t('moveSuccess'));
      await fetchTree();
    } catch (error) {
      toast.error(getWikiOperationErrorMessage(error, t('moveFailed')));
    }
  };

  const handleCreateFolder = (e?: React.MouseEvent) => {
    e?.preventDefault();
    e?.stopPropagation();
    const focused = treeRef.current?.focusedNode;
    setCreateParentFolder(resolveCreateParentFolder(focused?.id, focused?.data?.is_dir));
    setDialogMode('create');
    setDialogInput('');
    setDialogOpen(true);
  };

  const handleRename = (id: string, currentName: string, e?: React.MouseEvent) => {
    e?.preventDefault();
    e?.stopPropagation();
    setDialogTargetId(id);
    setDialogMode('rename');
    setDialogInput(currentName);
    setDialogOpen(true);
  };

  const submitDialog = async () => {
    if (!dialogInput.trim()) {
      return;
    }

    try {
      if (dialogMode === 'create') {
        const targetPath = createParentFolder ? `${createParentFolder}/${dialogInput}` : dialogInput;
        await wikiService.createFolder(targetPath, agentScopeId);
        toast.success(t('createSuccess'));
      } else if (dialogMode === 'rename' && dialogTargetId) {
        const parentDir = dialogTargetId.split('/').slice(0, -1).join('/');
        const newPath = parentDir ? `${parentDir}/${dialogInput}` : dialogInput;

        if (dialogTargetId !== newPath) {
          await wikiService.moveNode(dialogTargetId, newPath, agentScopeId);
          toast.success(t('renameSuccess'));
        }
      }
      await fetchTree();
      setDialogOpen(false);
    } catch (error) {
      toast.error(getWikiOperationErrorMessage(error, t('operationFailed')));
    }
  };

  return {
    handleMove,
    handleCreateFolder,
    handleRename,
    submitDialog,
  };
}
