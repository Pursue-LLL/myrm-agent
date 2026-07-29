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
  getWikiErrorCode,
  resolveCreateParentFolder,
} from './wikiTreeUtils';
import { splitTagsInput } from './wikiSectionUtils';

export type WikiEditTab = 'truth' | 'timeline' | 'metadata' | 'advanced';

export interface DeleteTarget {
  name: string;
  isDir: boolean;
  itemCount?: number;
}

export function useWikiConceptsList(options?: {
  treeSyncNonce?: number;
  agentScopeId?: string | null;
}) {
  const t = useTranslations('settings.wiki.concepts');
  const agentScopeId = options?.agentScopeId ?? null;
  const [query, setQuery] = useState('');
  const [treeData, setTreeData] = useState<TreeNode[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const [selectedConcept, setSelectedConcept] = useState<Concept | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editTab, setEditTab] = useState<WikiEditTab>('truth');
  const [editContent, setEditContent] = useState('');
  const [editCompiledTruth, setEditCompiledTruth] = useState('');
  const [editTimelineDisplay, setEditTimelineDisplay] = useState('');
  const [editTimelineAppend, setEditTimelineAppend] = useState('');
  const [editTags, setEditTags] = useState('');
  const [editAliases, setEditAliases] = useState('');
  const [editContentHash, setEditContentHash] = useState<string | undefined>(undefined);
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
      const res = await wikiService.getTree(agentScopeId);
      setTreeData(res);
    } catch (error) {
      console.error('Failed to load wiki tree:', error);
      toast.error(t('loadFailed'));
    } finally {
      setIsLoading(false);
    }
  }, [agentScopeId, t]);

  useEffect(() => {
    setSelectedConcept(null);
    setIsEditing(false);
    setEditContent('');
    setTreeData([]);
    void fetchTree();
  }, [fetchTree, options?.treeSyncNonce, agentScopeId]);

  const handleSelectConcept = async (id: string) => {
    try {
      const data = await wikiService.getConcept(id, agentScopeId);
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

  const handleDeleteRequest = (target: Omit<DeleteTarget, 'itemCount'>) => {
    const itemCount = target.isDir ? countDescendantItems(treeData, target.name) : undefined;
    setDeleteTarget({ ...target, itemCount });
  };

  const submitDialog = async () => {
    if (!dialogInput.trim()) return;

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

  const handleEdit = () => {
    if (selectedConcept) {
      const sections = selectedConcept.editor_sections;
      setEditContent(selectedConcept.content);
      setEditCompiledTruth(sections?.compiled_truth ?? '');
      setEditTimelineDisplay(sections?.timeline ?? '');
      setEditTimelineAppend('');
      setEditTags((sections?.tags ?? []).join(', '));
      setEditAliases((sections?.aliases ?? []).join(', '));
      setEditContentHash(selectedConcept.content_hash);
      setEditTab('truth');
      setIsEditing(true);
    }
  };

  const handleSave = async () => {
    if (!selectedConcept) return;
    setIsSaving(true);
    const lease = editContentHash ? { if_match: editContentHash } : {};
    try {
      if (editTab === 'advanced') {
        await wikiService.applyWiki(
          {
            op: 'replace_full_document',
            concept_name: selectedConcept.name,
            content: editContent,
            ...lease,
          },
          agentScopeId,
          'settings',
        );
      } else if (editTab === 'truth') {
        await wikiService.applyWiki(
          {
            op: 'patch_compiled_truth',
            concept_name: selectedConcept.name,
            compiled_truth: editCompiledTruth,
            ...lease,
          },
          agentScopeId,
          'settings',
        );
      } else if (editTab === 'timeline') {
        if (!editTimelineAppend.trim()) {
          toast.error(t('timelineEntryRequired'));
          return;
        }
        const appendResult = await wikiService.applyWiki(
          {
            op: 'append_timeline',
            concept_name: selectedConcept.name,
            timeline_entry: editTimelineAppend.trim(),
            ...lease,
          },
          agentScopeId,
          'settings',
        );
        if (appendResult.appended === false) {
          toast.message(t('timelineDuplicateSkipped'));
        }
      } else {
        await wikiService.applyWiki(
          {
            op: 'update_metadata',
            concept_name: selectedConcept.name,
            tags: splitTagsInput(editTags),
            aliases: splitTagsInput(editAliases),
            ...lease,
          },
          agentScopeId,
          'settings',
        );
      }

      const refreshed = await wikiService.getConcept(selectedConcept.name, agentScopeId);
      setSelectedConcept(refreshed);
      const sections = refreshed.editor_sections;
      if (sections) {
        setEditCompiledTruth(sections.compiled_truth);
        setEditTimelineDisplay(sections.timeline);
        setEditTags(sections.tags.join(', '));
        setEditAliases(sections.aliases.join(', '));
      }
      setEditContentHash(refreshed.content_hash);
      if (editTab === 'timeline') {
        setEditTimelineAppend('');
      }
      setIsEditing(false);
      toast.success(t('updateSuccess'));
    } catch (error) {
      const code = getWikiErrorCode(error);
      if (code === 'conflict') {
        toast.error(t('pageConflict'));
      } else {
        toast.error(getWikiOperationErrorMessage(error, t('updateFailed')));
      }
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
        await wikiService.deleteFolder(name, agentScopeId);
      } else {
        await wikiService.deleteConcept(name, agentScopeId);
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
    editTab,
    setEditTab,
    editContent,
    setEditContent,
    editCompiledTruth,
    setEditCompiledTruth,
    editTimelineDisplay,
    editTimelineAppend,
    setEditTimelineAppend,
    editTags,
    setEditTags,
    editAliases,
    setEditAliases,
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
