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
import { useWikiConceptClaimActions } from './useWikiConceptClaimActions';
import { useWikiTreeActions } from './useWikiTreeActions';

function findConceptNodeId(nodes: TreeNode[], conceptPath: string): string | null {
  const normalized = conceptPath.replace(/\\/g, '/').replace(/^\//, '').replace(/\.md$/i, '');
  // Wiki concept paths are persisted in sanitized (lowercase) form, while
  // callers may reference the original mixed-case path (e.g. chat-compound
  // concept names). Compare case-insensitively so highlight/deep-link resolves.
  const normalizedLower = normalized.toLowerCase();
  for (const node of nodes) {
    const nodeId = node.id.replace(/\\/g, '/');
    if (
      !node.is_dir &&
      (nodeId.toLowerCase() === normalizedLower || nodeId.toLowerCase().endsWith(`/${normalizedLower}`))
    ) {
      return node.id;
    }
    if (node.children?.length) {
      const found = findConceptNodeId(node.children, normalized);
      if (found) {
        return found;
      }
    }
  }
  return null;
}

export type WikiEditTab = 'truth' | 'timeline' | 'metadata' | 'advanced';

type DiscardPending = 'select' | 'cancel';

interface EditBaseline {
  content: string;
  compiledTruth: string;
  timelineAppend: string;
  tags: string;
  aliases: string;
}

export interface DeleteTarget {
  name: string;
  isDir: boolean;
  itemCount?: number;
}

export function useWikiConceptsList(options?: {
  treeSyncNonce?: number;
  agentScopeId?: string | null;
  highlightConceptPath?: string | null;
  onVaultMutated?: () => void;
}) {
  const t = useTranslations('settings.wiki.concepts');
  const agentScopeId = options?.agentScopeId ?? null;
  const onVaultMutated = options?.onVaultMutated;
  const [query, setQuery] = useState('');
  const [treeData, setTreeData] = useState<TreeNode[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const [selectedConcept, setSelectedConceptState] = useState<Concept | null>(null);
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
  const [editBaseline, setEditBaseline] = useState<EditBaseline | null>(null);
  const [discardPending, setDiscardPending] = useState<DiscardPending | null>(null);
  const [pendingSelectId, setPendingSelectId] = useState<string | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<'create' | 'rename'>('create');
  const [dialogInput, setDialogInput] = useState('');
  const [dialogTargetId, setDialogTargetId] = useState<string | null>(null);
  const [createParentFolder, setCreateParentFolder] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  const treeRef = useRef<TreeApi<TreeNode> | null>(null);
  const lastHighlightedConceptRef = useRef<string | null>(null);
  // 词条选择只认最后一次发起的请求：快速连点或切换 Agent 范围时，较早发起的响应（含失败）一律丢弃
  const selectRequestRef = useRef(0);
  // 详情区正在展示的词条名：操作回调里的 selectedConcept 是发起时的快照，await 之后要以这里的最新值判断结果是否还属于当前详情
  const shownConceptNameRef = useRef<string | null>(null);
  const setSelectedConcept = useCallback((concept: Concept | null) => {
    shownConceptNameRef.current = concept?.name ?? null;
    setSelectedConceptState(concept);
  }, []);

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
    selectRequestRef.current += 1;
    setSelectedConcept(null);
    setIsEditing(false);
    setEditContent('');
    setEditBaseline(null);
    setDiscardPending(null);
    setPendingSelectId(null);
    setTreeData([]);
    lastHighlightedConceptRef.current = null;
    void fetchTree();
  }, [fetchTree, options?.treeSyncNonce, agentScopeId, setSelectedConcept]);

  const hasUnsavedEdits = Boolean(
    editBaseline &&
    (editContent !== editBaseline.content ||
      editCompiledTruth !== editBaseline.compiledTruth ||
      editTimelineAppend !== editBaseline.timelineAppend ||
      editTags !== editBaseline.tags ||
      editAliases !== editBaseline.aliases),
  );

  const handleSelectConcept = useCallback(
    async (id: string) => {
      const requestId = ++selectRequestRef.current;
      try {
        const data = await wikiService.getConcept(id, agentScopeId);
        if (requestId !== selectRequestRef.current) {
          return;
        }
        setSelectedConcept(data);
        setIsEditing(false);
        setEditBaseline(null);
      } catch {
        if (requestId === selectRequestRef.current) {
          toast.error(t('loadFailed'));
        }
      }
    },
    [agentScopeId, setSelectedConcept, t],
  );

  const requestSelectConcept = useCallback(
    async (id: string) => {
      if (isEditing && hasUnsavedEdits) {
        setPendingSelectId(id);
        setDiscardPending('select');
        return;
      }
      await handleSelectConcept(id);
    },
    [isEditing, hasUnsavedEdits, handleSelectConcept],
  );

  const requestCancelEdit = () => {
    if (hasUnsavedEdits) {
      setDiscardPending('cancel');
      return;
    }
    setIsEditing(false);
    setEditBaseline(null);
  };

  const confirmDiscard = () => {
    const pending = discardPending;
    const selectId = pendingSelectId;
    setDiscardPending(null);
    setPendingSelectId(null);
    setEditBaseline(null);
    if (pending === 'cancel') {
      setIsEditing(false);
      return;
    }
    if (pending === 'select' && selectId) {
      void handleSelectConcept(selectId);
    }
  };

  const cancelDiscard = () => {
    setDiscardPending(null);
    setPendingSelectId(null);
  };

  useEffect(() => {
    const highlight = options?.highlightConceptPath?.replace(/\\/g, '/').replace(/\.md$/i, '') ?? null;
    if (!highlight || isLoading || treeData.length === 0) {
      return;
    }
    if (lastHighlightedConceptRef.current === highlight) {
      return;
    }
    const nodeId = findConceptNodeId(treeData, highlight);
    if (!nodeId) {
      if (lastHighlightedConceptRef.current !== highlight) {
        lastHighlightedConceptRef.current = highlight;
        toast.message(t('highlightNotFound', { path: highlight }));
      }
      return;
    }
    lastHighlightedConceptRef.current = highlight;
    void requestSelectConcept(nodeId);
    // Deep-link navigation should also reveal the target in the tree. Expand
    // every ancestor directory (best-effort) so the highlighted leaf is
    // visibly selected after the detail panel loads.
    const segments = nodeId.split('/');
    for (let i = 1; i < segments.length; i++) {
      try {
        treeRef.current?.open(segments.slice(0, i).join('/'));
      } catch {
        // Tree may not have mounted at highlight time — selection still works.
      }
    }
  }, [options?.highlightConceptPath, isLoading, treeData, requestSelectConcept, t]);

  const { handleMove, handleCreateFolder, handleRename, submitDialog } = useWikiTreeActions({
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
  });

  const handleDeleteRequest = (target: Omit<DeleteTarget, 'itemCount'>) => {
    const itemCount = target.isDir ? countDescendantItems(treeData, target.name) : undefined;
    setDeleteTarget({ ...target, itemCount });
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
      setEditBaseline({
        content: selectedConcept.content,
        compiledTruth: sections?.compiled_truth ?? '',
        timelineAppend: '',
        tags: (sections?.tags ?? []).join(', '),
        aliases: (sections?.aliases ?? []).join(', '),
      });
      setEditTab('truth');
      setIsEditing(true);
    }
  };

  const handleSave = async () => {
    if (!selectedConcept) {
      return;
    }
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
      // 保存期间详情已换成别的词条：写入已成功，但这份刷新结果不属于当前详情，也不再属于任何编辑会话
      if (shownConceptNameRef.current === selectedConcept.name) {
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
        setEditBaseline(null);
      }
      toast.success(t('updateSuccess'));
      onVaultMutated?.();
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

  const { handleUpdateClaimStatus, handleHealClaims } = useWikiConceptClaimActions({
    selectedConcept,
    setSelectedConcept,
    shownConceptNameRef,
    agentScopeId,
    onVaultMutated,
  });

  const confirmDelete = async () => {
    if (!deleteTarget) {
      return;
    }

    const { name, isDir } = deleteTarget;
    setIsDeleting(name);
    try {
      if (isDir) {
        await wikiService.deleteFolder(name, agentScopeId);
      } else {
        await wikiService.deleteConcept(name, agentScopeId);
      }
      const shown = shownConceptNameRef.current;
      if (shown === name || shown?.startsWith(`${name}/`)) {
        setSelectedConcept(null);
      }
      toast.success(t('deleteSuccess'));
      await fetchTree();
      onVaultMutated?.();
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
    requestSelectConcept,
    requestCancelEdit,
    confirmDiscard,
    cancelDiscard,
    hasUnsavedEdits,
    discardDialogOpen: discardPending !== null,
    handleMove,
    handleCreateFolder,
    handleRename,
    handleDeleteRequest,
    submitDialog,
    handleEdit,
    handleSave,
    handleUpdateClaimStatus,
    handleHealClaims,
    confirmDelete,
  };
}
