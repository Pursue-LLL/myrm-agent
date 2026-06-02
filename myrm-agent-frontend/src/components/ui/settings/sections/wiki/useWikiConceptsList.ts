'use client';

/**
 * [INPUT] services/wikiService (POS: Wiki REST 客户端)
 * [OUTPUT] useWikiConceptsList: 词条树 CRUD 状态与 handlers
 * [POS] Settings Wiki 词条管理业务逻辑 Hook
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import type { TreeApi } from 'react-arborist';
import { wikiService, Concept, TreeNode } from '@/services/wikiService';
import {
  countDescendantItems,
  filterFolderNodes,
  getWikiOperationErrorMessage,
  resolveCreateParentFolder,
} from './wikiTreeUtils';

export interface DeleteTarget {
  name: string;
  isDir: boolean;
  itemCount?: number;
}

export function useWikiConceptsList() {
  const t = useTranslations('settings.wiki.concepts');
  const [query, setQuery] = useState('');
  const [treeData, setTreeData] = useState<TreeNode[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const [selectedConcept, setSelectedConcept] = useState<Concept | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<'create' | 'rename'>('create');
  const [dialogInput, setDialogInput] = useState('');
  const [dialogTargetId, setDialogTargetId] = useState<string | null>(null);
  const [createParentFolder, setCreateParentFolder] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  const treeRef = useRef<TreeApi<TreeNode> | null>(null);

  const fetchTree = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await wikiService.getTree();
      setTreeData(res);
    } catch (error) {
      console.error('Failed to load wiki tree:', error);
      toast.error(t('loadFailed'));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchTree();
  }, [fetchTree]);

  const handleSelectConcept = async (id: string) => {
    try {
      const data = await wikiService.getConcept(id);
      setSelectedConcept(data);
      setIsEditing(false);
    } catch {
      toast.error(t('loadFailed'));
    }
  };

  const handleMove = async ({ dragIds, parentId }: { dragIds: string[]; parentId: string | null; index: number }) => {
    const sourceId = dragIds[0];
    if (!sourceId) return;

    const sourceName = sourceId.split('/').pop() || sourceId;
    const targetPath = parentId ? `${parentId}/${sourceName}` : sourceName;

    if (sourceId === targetPath) return;

    try {
      await wikiService.moveNode(sourceId, targetPath);
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

  const handleDeleteRequest = (target: Omit<DeleteTarget, 'itemCount'>) => {
    const itemCount = target.isDir ? countDescendantItems(treeData, target.name) : undefined;
    setDeleteTarget({ ...target, itemCount });
  };

  const submitDialog = async () => {
    if (!dialogInput.trim()) return;

    try {
      if (dialogMode === 'create') {
        const targetPath = createParentFolder ? `${createParentFolder}/${dialogInput}` : dialogInput;
        await wikiService.createFolder(targetPath);
        toast.success(t('createSuccess'));
      } else if (dialogMode === 'rename' && dialogTargetId) {
        const parentDir = dialogTargetId.split('/').slice(0, -1).join('/');
        const newPath = parentDir ? `${parentDir}/${dialogInput}` : dialogInput;

        if (dialogTargetId !== newPath) {
          await wikiService.moveNode(dialogTargetId, newPath);
          toast.success(t('renameSuccess'));
        }
      }
      await fetchTree();
      setDialogOpen(false);
    } catch (error) {
      toast.error(getWikiOperationErrorMessage(error, t('operationFailed')));
    }
  };

  const handleEdit = () => {
    if (selectedConcept) {
      setEditContent(selectedConcept.content);
      setIsEditing(true);
    }
  };

  const handleSave = async () => {
    if (!selectedConcept) return;
    setIsSaving(true);
    try {
      await wikiService.updateConcept(selectedConcept.name, editContent);
      setSelectedConcept({ ...selectedConcept, content: editContent });
      setIsEditing(false);
      toast.success(t('updateSuccess'));
    } catch (error) {
      toast.error(getWikiOperationErrorMessage(error, t('updateFailed')));
    } finally {
      setIsSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;

    const { name, isDir } = deleteTarget;
    setIsDeleting(name);
    try {
      if (isDir) {
        await wikiService.deleteFolder(name);
      } else {
        await wikiService.deleteConcept(name);
      }
      if (selectedConcept?.name === name || selectedConcept?.name.startsWith(`${name}/`)) {
        setSelectedConcept(null);
      }
      toast.success(t('deleteSuccess'));
      await fetchTree();
    } catch (error) {
      toast.error(getWikiOperationErrorMessage(error, t('deleteFailed')));
    } finally {
      setIsDeleting(null);
      setDeleteTarget(null);
    }
  };

  return {
    query,
    setQuery,
    treeData,
    folderTreeData: filterFolderNodes(treeData),
    isLoading,
    selectedConcept,
    isEditing,
    setIsEditing,
    editContent,
    setEditContent,
    isSaving,
    isDeleting,
    dialogOpen,
    setDialogOpen,
    dialogMode,
    dialogInput,
    setDialogInput,
    createParentFolder,
    setCreateParentFolder,
    deleteTarget,
    setDeleteTarget,
    treeRef,
    handleSelectConcept,
    handleMove,
    handleCreateFolder,
    handleRename,
    handleDeleteRequest,
    submitDialog,
    handleEdit,
    handleSave,
    confirmDelete,
  };
}
