/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态源，读取/清理挂载项)
 * - @/hooks/message-input/turnCapabilityOverrideCore::TurnCapabilitySelection (POS: 单轮能力收窄状态契约)
 * - @/lib/utils/messageUtils::formatSkillChipLabel (POS: 技能显示名格式化工具)
 *
 * [OUTPUT]
 * - useComposerContextChips: 统一提取并派发聊天输入区所有上下文挂载项 (技能/工作流/单轮能力/提及/附件)
 * - ContextChipItem / ContextChipCategory: 上下文胶囊项数据契约
 *
 * [POS]
 * 输入区上下文挂载项适配层。将分散在不同 Store 字段的挂载状态转换为统一的 Chip 列表与原子注销动作。
 */

import { useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import useChatStore, { File as FileType } from '@/store/useChatStore';
import type { TurnCapabilitySelection } from '@/hooks/message-input/turnCapabilityOverrideCore';
import { formatSkillChipLabel } from '@/lib/utils/messageUtils';
import { deleteSharedContextBindingByTarget } from '@/services/memory/sharedContexts';

export type ContextChipCategory = 'skill' | 'workflow' | 'capability' | 'mention' | 'attachment' | 'knowledge';

export interface ContextChipItem {
  id: string;
  category: ContextChipCategory;
  label: string;
  detail?: string | null;
  tooltip?: string | null;
  iconType: 'skill' | 'workflow' | 'capability' | 'mention' | 'file' | 'image' | 'knowledge';
  isRemovable: boolean;
  onRemove?: () => void;
  onAction?: () => void;
}

export interface UseComposerContextChipsParams {
  turnCapabilitySelection: TurnCapabilitySelection | null;
  setTurnCapabilitySelection: (selection: TurnCapabilitySelection | null) => void;
  files: FileType[];
  setFiles: (files: FileType[]) => void;
  clearCurrentSessionMessageId: () => void;
  mentionReferences: Array<{
    type: string;
    path?: string;
    fileId?: string;
    url?: string;
    label: string;
    startLine?: number;
    endLine?: number;
  }>;
  removeMentionReference: (key: string) => void;
  onOpenCapabilityEditor?: () => void;
  hideAttachList?: boolean;
}

export interface ComposerContextSummary {
  totalItems: number;
  totalSkills: number;
  totalMcp: number;
  totalFiles: number;
  isOverloaded: boolean;
}

const mentionReferenceKey = (reference: {
  type: string;
  path?: string;
  fileId?: string;
  url?: string;
  label: string;
  startLine?: number;
  endLine?: number;
}): string => {
  return `${reference.type}:${reference.path ?? reference.fileId ?? reference.url ?? reference.label}:${reference.startLine ?? ''}:${reference.endLine ?? ''}`;
};

export function useComposerContextChips({
  turnCapabilitySelection,
  setTurnCapabilitySelection,
  files,
  setFiles,
  clearCurrentSessionMessageId,
  mentionReferences,
  removeMentionReference,
  onOpenCapabilityEditor,
  hideAttachList = false,
}: UseComposerContextChipsParams) {
  const tChat = useTranslations('chat');
  const tTurn = useTranslations('chat.turnCapabilities');
  const tWorkflow = useTranslations('chat.workflowTemplateArmed');

  const pendingWorkflowTemplateId = useChatStore((s) => s.pendingWorkflowTemplateId);
  const pendingWorkflowTemplateDisplayName = useChatStore((s) => s.pendingWorkflowTemplateDisplayName);
  const pendingExplicitSkillActivation = useChatStore((s) => s.pendingExplicitSkillActivation);
  const clearPendingWorkflowTemplate = useChatStore((s) => s.clearPendingWorkflowTemplate);
  const setIsWorkflowMode = useChatStore((s) => s.setIsWorkflowMode);
  const setPendingExplicitSkillActivation = useChatStore((s) => s.setPendingExplicitSkillActivation);

  const activeKnowledgeBaseIds = useChatStore((s) => s.activeKnowledgeBaseIds);
  const activeKnowledgeBaseNames = useChatStore((s) => s.activeKnowledgeBaseNames);
  const removeActiveKnowledgeBase = useChatStore((s) => s.removeActiveKnowledgeBase);
  const chatId = useChatStore((s) => s.chatId);
  const incognitoMode = useChatStore((s) => s.incognitoMode);

  const handleDisarmWorkflow = useCallback(() => {
    clearPendingWorkflowTemplate();
    setIsWorkflowMode(false);
  }, [clearPendingWorkflowTemplate, setIsWorkflowMode]);

  const handleClearSkillActivation = useCallback(() => {
    setPendingExplicitSkillActivation(null);
  }, [setPendingExplicitSkillActivation]);

  const handleClearTurnCapability = useCallback(() => {
    setTurnCapabilitySelection(null);
  }, [setTurnCapabilitySelection]);

  const handleRemoveKnowledgeBase = useCallback(
    async (kbId: string) => {
      removeActiveKnowledgeBase(kbId);
      if (chatId && !incognitoMode) {
        try {
          await deleteSharedContextBindingByTarget(kbId, 'conversation', chatId);
        } catch {
          // 静默降级
        }
      }
    },
    [chatId, incognitoMode, removeActiveKnowledgeBase],
  );

  const handleRemoveFile = useCallback(
    (fileId: string) => {
      const next = files.filter((f) => f.id !== fileId);
      setFiles(next);
      if (next.length === 0) {
        clearCurrentSessionMessageId();
      }
    },
    [files, setFiles, clearCurrentSessionMessageId],
  );

  const chips: ContextChipItem[] = useMemo(() => {
    const list: ContextChipItem[] = [];

    // 1. 工作流模板 (Workflow Template)
    if (pendingWorkflowTemplateId) {
      const label = pendingWorkflowTemplateDisplayName?.trim() || pendingWorkflowTemplateId;
      list.push({
        id: `workflow-${pendingWorkflowTemplateId}`,
        category: 'workflow',
        label,
        detail: tWorkflow('label'),
        tooltip: pendingWorkflowTemplateId,
        iconType: 'workflow',
        isRemovable: true,
        onRemove: handleDisarmWorkflow,
      });
    }

    // 2. 显式临时技能激活 (Explicit Skill Activation)
    if (pendingExplicitSkillActivation && pendingExplicitSkillActivation.skillNames.length > 0) {
      pendingExplicitSkillActivation.skillNames.forEach((skillName) => {
        list.push({
          id: `skill-${skillName}`,
          category: 'skill',
          label: formatSkillChipLabel(skillName),
          detail: pendingExplicitSkillActivation.instruction || null,
          tooltip: skillName,
          iconType: 'skill',
          isRemovable: true,
          onRemove: handleClearSkillActivation,
        });
      });
    }

    // 3. 单轮能力覆写 (Turn Capability Selection)
    if (turnCapabilitySelection !== null) {
      const parts: string[] = [];
      if (turnCapabilitySelection.skillIds !== null) {
        parts.push(tTurn('overrideSkillsShort', { skills: turnCapabilitySelection.skillIds.length }));
      }
      if (turnCapabilitySelection.mcpNames !== null) {
        parts.push(tTurn('overrideMcpShort', { mcps: turnCapabilitySelection.mcpNames.length }));
      }
      list.push({
        id: 'turn-capability-override',
        category: 'capability',
        label: parts.join(' · ') || tTurn('activeSummary'),
        detail: null,
        tooltip: tTurn('activeSummary'),
        iconType: 'capability',
        isRemovable: true,
        onRemove: handleClearTurnCapability,
        onAction: onOpenCapabilityEditor,
      });
    }

    // 4. @ 提及引用 (Mention References)
    if (mentionReferences.length > 0) {
      mentionReferences.forEach((ref) => {
        const key = mentionReferenceKey(ref);
        list.push({
          id: `mention-${key}`,
          category: 'mention',
          label: ref.label,
          detail: ref.type,
          tooltip: ref.path ?? ref.fileId ?? ref.url ?? ref.label,
          iconType: 'mention',
          isRemovable: true,
          onRemove: () => removeMentionReference(key),
        });
      });
    }

    // 5. 会话级挂载知识库 (Mounted Knowledge Bases)
    if (activeKnowledgeBaseIds.length > 0) {
      activeKnowledgeBaseIds.forEach((kbId) => {
        const kbName = activeKnowledgeBaseNames[kbId] || kbId;
        list.push({
          id: `knowledge-${kbId}`,
          category: 'knowledge',
          label: kbName,
          detail: tChat('knowledgePicker.chipDetail'),
          tooltip: kbName,
          iconType: 'knowledge',
          isRemovable: true,
          onRemove: () => void handleRemoveKnowledgeBase(kbId),
        });
      });
    }

    // 6. 附加文件 (Attachments) - 仅在 AttachList 被折叠隐藏时作为紧凑胶囊呈现，避免双重卡片堆叠
    if (hideAttachList && files.length > 0) {
      files.forEach((file) => {
        const isImg = file.type?.startsWith('image/') || file.fileName?.match(/\.(png|jpe?g|webp|gif|svg)$/i);
        list.push({
          id: `file-${file.id}`,
          category: 'attachment',
          label: file.fileName,
          detail: file.status === 'uploading' ? tChat('uploading') : null,
          tooltip: file.fileName,
          iconType: isImg ? 'image' : 'file',
          isRemovable: true,
          onRemove: () => handleRemoveFile(file.id),
        });
      });
    }

    return list;
  }, [
    pendingWorkflowTemplateId,
    pendingWorkflowTemplateDisplayName,
    pendingExplicitSkillActivation,
    turnCapabilitySelection,
    activeKnowledgeBaseIds,
    activeKnowledgeBaseNames,
    mentionReferences,
    files,
    hideAttachList,
    tWorkflow,
    tTurn,
    tChat,
    handleDisarmWorkflow,
    handleClearSkillActivation,
    handleClearTurnCapability,
    handleRemoveKnowledgeBase,
    handleRemoveFile,
    removeMentionReference,
    onOpenCapabilityEditor,
  ]);

  const summary: ComposerContextSummary = useMemo(() => {
    let skillCount = 0;
    let mcpCount = 0;

    if (pendingExplicitSkillActivation) {
      skillCount += pendingExplicitSkillActivation.skillNames.length;
    }
    if (turnCapabilitySelection?.skillIds !== null && turnCapabilitySelection?.skillIds !== undefined) {
      skillCount += turnCapabilitySelection.skillIds.length;
    }
    if (turnCapabilitySelection?.mcpNames !== null && turnCapabilitySelection?.mcpNames !== undefined) {
      mcpCount += turnCapabilitySelection.mcpNames.length;
    }

    const totalFiles = files.length + mentionReferences.length;
    const totalItems = chips.length;

    // 超过 6 个活跃能力或超过 5 个文件判定为潜在过载负载
    const isOverloaded = skillCount + mcpCount >= 6 || totalFiles >= 5;

    return {
      totalItems,
      totalSkills: skillCount,
      totalMcp: mcpCount,
      totalFiles,
      isOverloaded,
    };
  }, [chips.length, pendingExplicitSkillActivation, turnCapabilitySelection, files.length, mentionReferences.length]);

  return {
    chips,
    summary,
    hasContext: chips.length > 0,
  };
}
