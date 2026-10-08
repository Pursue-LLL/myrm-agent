/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/store/chat/archiveRestoreActions::resolveArchiveRestoreActionsForMessage (POS: Typed archive restore action utility layer. Keeps parsing, normalization and send-time matching outside the chat stream reducer and input hook.)
 * - @/hooks/message-input/useInputFileUpload::useInputFileUpload (POS: 聊天输入文件上传 Hook)
 * - @/hooks/message-input/useMessageQueue::useMessageQueue (POS: 排队消息的 React 视图层)
 * - @/hooks/message-input/useQueueDrain::useQueueDrain (POS: 排队消息发送循环)
 * - @/hooks/message-input/turnCapabilityTelemetry::useTurnCapabilityTelemetry (POS: 单轮能力覆写埋点编排)
 * - @/hooks/message-input/useMessageInputWikiEvidenceCore::recordChatWikiQueryAttempt (POS: Chat 输入链路的 Wiki 证据复问口径核心)
 * - @/hooks/message-input/useMessageInputWikiEvidenceCore::queuePendingChatWikiQuerySuccess (POS: steer success 延迟确认注册)
 *
 * [OUTPUT]
 * - useMessageInput: exposes chat input state, upload handling and submit handlers.
 *
 * [POS]
 * 聊天输入业务 Hook。封装输入框状态、附件上传、草稿、排队发送和提交编排。
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import useChatStore from '@/store/useChatStore';
import { buildExplicitSkillWireMessage } from '@/lib/utils/messageUtils';
import { useScopedArtifactStore } from '@/store/useScopedArtifactStore';
import { compactChat } from '@/services/chat';
import { toast } from '@/lib/utils/toast';
import { useQuotaGuard } from '@/hooks/billing/useQuotaGuard';
import { useDraftPersistence } from '@/hooks/shared/useDraftPersistence';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import { isArchiveRestoreActionInvalidError } from '@/lib/utils/networkResilience';
import { useMessageQueue } from './useMessageQueue';
import { useQueueDrain } from './useQueueDrain';
import { useInputFileUpload } from './useInputFileUpload';
import { resolveArchiveRestoreActionsForMessage } from '@/store/chat/archiveRestoreActions';
import { recordChatWikiQueryAttempt, queuePendingChatWikiQuerySuccess } from './useMessageInputWikiEvidenceCore';
import { addInputHistory } from './useInputHistory';
import { buildTurnAgentConfigOverride, type TurnCapabilitySelection } from './turnCapabilityOverrideCore';
import { resolveTerminalTelemetry, useTurnCapabilityTelemetry } from './turnCapabilityTelemetry';

function composeOutboundUserMessage(rawInput: string): string {
  let outbound = rawInput;
  const pending = useChatStore.getState().pendingExplicitSkillActivation;
  if (pending) {
    outbound = buildExplicitSkillWireMessage(pending, outbound);
  }

  // 注入局部工件编辑选区语义 (Scoped Artifact)
  const scopedTarget = useScopedArtifactStore.getState().target;
  if (scopedTarget) {
    const scopeHeader = `[针对工件 "${scopedTarget.artifactName}" 的局部范围 (${scopedTarget.scopeLabel}) 定向编辑]`;
    const snippetBody = scopedTarget.selectedSnippet ? `\n\`\`\`\n${scopedTarget.selectedSnippet}\n\`\`\`\n` : '';
    outbound = `${scopeHeader}${snippetBody}\n${outbound}`.trim();
    useScopedArtifactStore.getState().clearTarget();
  }

  return outbound;
}

function clearPendingExplicitSkillActivation(): void {
  if (useChatStore.getState().pendingExplicitSkillActivation) {
    useChatStore.getState().setPendingExplicitSkillActivation(null);
  }
}

/** Registers the deferred wiki-evidence success for an instruction the running turn accepted (steer or redirect). */
function confirmInstructionLanded(): void {
  const chatState = useChatStore.getState();
  const currentSessionMessageId =
    typeof chatState.getCurrentSessionMessageId === 'function' ? chatState.getCurrentSessionMessageId() : undefined;
  queuePendingChatWikiQuerySuccess(chatState.messages, chatState.chatId, currentSessionMessageId);
}

export const useMessageInput = () => {
  const t = useTranslations('chat');
  const [showLinkDialog, setShowLinkDialog] = useState(false);
  const [detectedLink, setDetectedLink] = useState<{ text: string; position: number } | null>(null);
  const [dontRemindAgain, setDontRemindAgain] = useState(false);
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('dontRemindLinkDialog');
      if (saved === 'true') {
        setDontRemindAgain(true);
      }
    }
  }, []);
  const [showCompactConfirm, setShowCompactConfirm] = useState(false);
  const [dontRemindCompact, setDontRemindCompact] = useState(false);
  const pendingCompactTopicRef = useRef<string | undefined>(undefined);
  const {
    chatId,
    sendMessage,
    steerMessage,
    redirectMessage,
    actionMode,
    setActionMode,
    files,
    setFiles,
    hideAttachList,
    setHideAttachList,
    stopMessage,
    clearCurrentSessionMessageId,
    inputMessage,
    setInputMessage,
    pendingArchiveRestoreActions,
    setPendingArchiveRestoreActions,
    loadMessages,
    loading,
    agentConfig,
    incognitoMode,
  } = useChatStore(
    useShallow((state) => ({
      chatId: state.chatId,
      sendMessage: state.sendMessage,
      steerMessage: state.steerMessage,
      redirectMessage: state.redirectMessage,
      actionMode: state.actionMode,
      setActionMode: state.setActionMode,
      files: state.files,
      setFiles: state.setFiles,
      hideAttachList: state.hideAttachList,
      setHideAttachList: state.setHideAttachList,
      stopMessage: state.stopMessage,
      clearCurrentSessionMessageId: state.clearCurrentSessionMessageId,
      inputMessage: state.inputMessage,
      setInputMessage: state.setInputMessage,
      pendingArchiveRestoreActions: state.pendingArchiveRestoreActions,
      setPendingArchiveRestoreActions: state.setPendingArchiveRestoreActions,
      loadMessages: state.loadMessages,
      loading: state.loading,
      agentConfig: state.agentConfig,
      incognitoMode: state.incognitoMode,
    })),
  );

  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const { validateMessageQuota } = useQuotaGuard();
  const { isUploadingPaste, handlePaste, handleDroppedFiles } = useInputFileUpload({
    actionMode,
    files,
    setFiles,
    setHideAttachList,
  });

  // ─── 草稿持久化（无痕会话不落盘）───
  const { initialDraft, clearDraft } = useDraftPersistence(incognitoMode ? null : chatId, inputMessage);

  // ─── 消息排队 ───
  const {
    queue,
    pausedReason,
    editingId,
    enqueue,
    editMessage,
    removeMessage,
    clearQueue,
    reorder,
    setEditingId,
    resume,
  } = useMessageQueue(chatId);
  useQueueDrain(chatId);
  const telemetry = useTurnCapabilityTelemetry(chatId);
  const [turnCapabilitySelection, setTurnCapabilitySelection] = useState<TurnCapabilitySelection | null>(null);
  const agentSkillSignature = (agentConfig?.selectedSkillIds ?? []).join('\u0001');
  const agentMcpSignature = (agentConfig?.selectedMcpNames ?? []).join('\u0001');

  const consumeTurnCapabilitySelection = useCallback(() => {
    if (!turnCapabilitySelection) {
      return null;
    }
    const consumed = turnCapabilitySelection;
    setTurnCapabilitySelection(null);
    return consumed;
  }, [turnCapabilitySelection]);

  useEffect(() => {
    setTurnCapabilitySelection(null);
  }, [chatId, agentConfig?.agentId, agentSkillSignature, agentMcpSignature]);

  // 仅在草稿变化且当前输入框为空时恢复草稿；读取最新 store 值而非渲染闭包，避免用户输入触发重复恢复
  useEffect(() => {
    if (initialDraft && !useChatStore.getState().inputMessage) {
      setInputMessage(initialDraft);
    }
  }, [initialDraft, setInputMessage]);

  /**
   * 执行压缩操作
   */
  const executeCompact = useCallback(
    async (focusTopic?: string) => {
      if (!chatId) {
        toast.warning(t('compact.noChatId'));
        return;
      }

      if (dontRemindCompact) {
        localStorage.setItem('dontRemindCompact', 'true');
      }

      const toastId = toast.loading(t('compact.compacting'));
      try {
        const result = await compactChat(chatId, focusTopic);
        if (result.compacted) {
          const topicHint = focusTopic ? ` (${focusTopic})` : '';
          toast.success(
            t('compact.success', { count: result.message_count, tokens: result.tokens_saved }) + topicHint,
            {
              id: toastId,
            },
          );
          await loadMessages(chatId);
        } else {
          toast.info(t('compact.skipped', { reason: result.reason ?? '' }), { id: toastId });
        }
      } catch {
        toast.error(t('compact.failed'), { id: toastId });
      }
    },
    [chatId, dontRemindCompact, loadMessages, t],
  );

  const _validateAndPrepare = useCallback(async (): Promise<boolean> => {
    if (inputMessage.trim().length === 0 && files.length === 0) {
      if (!useChatStore.getState().pendingExplicitSkillActivation) {
        return false;
      }
    }

    // 提交排队安全门禁：等待处于 uploading 状态的媒体就绪 (最长等待 30 秒)
    const currentStoreFiles = useChatStore.getState().files;
    const pendingUploads = currentStoreFiles.filter((f) => f.status === 'uploading');
    if (pendingUploads.length > 0) {
      const start = Date.now();
      while (Date.now() - start < 30000) {
        const checkFiles = useChatStore.getState().files;
        const stillUploading = checkFiles.some((f) => f.status === 'uploading');
        if (!stillUploading) {
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      const finalFiles = useChatStore.getState().files;
      const failed = finalFiles.some((f) => f.status === 'error');
      if (failed) {
        toast.error(t('uploadFailed') || 'Upload failed');
        return false;
      }
    }

    const { actionMode } = useChatStore.getState();

    const quota = await validateMessageQuota(inputMessage.trim().length, files.length > 0, actionMode);
    if (!quota.allowed) {
      return false;
    }
    return true;
  }, [inputMessage, files, actionMode, validateMessageQuota, t]);

  // 获取并清理脏状态的 Artifacts，用于注入到消息中
  const _injectDirtyArtifacts = useCallback((message: string): string => {
    const dirtyArtifacts = useArtifactPortalStore.getState().getDirtyArtifacts();
    const artifactIds = Object.keys(dirtyArtifacts);

    if (artifactIds.length === 0) {
      return message;
    }

    let injectedMessage = message;

    // 将所有脏状态的 Artifacts 注入到消息末尾
    for (const id of artifactIds) {
      const content = dirtyArtifacts[id];
      injectedMessage += `\n\n<edited_artifact id="${id}">\n${content}\n</edited_artifact>`;
      // 注入后清除脏状态
      useArtifactPortalStore.getState().clearDirtyState(id);
    }

    return injectedMessage;
  }, []);

  const recordChatQueryMetric = useCallback(() => {
    const chatState = useChatStore.getState();
    recordChatWikiQueryAttempt(chatState.messages, chatState.chatId);
  }, []);

  // Steer only reaches a registered, running turn. When the server cannot take the instruction mid-turn (the turn is
  // still starting or has just ended, or the request failed) it is queued instead of lost: it stays behind earlier
  // queued messages, Stop holds it like any other, and the drain sends it at once if the agent is already idle.
  const steerOrQueue = useCallback(
    async (instruction: string): Promise<void> => {
      if (await steerMessage(instruction)) {
        confirmInstructionLanded();
        return;
      }
      const position = enqueue(instruction, [], undefined, null);
      if (useChatStore.getState().loading) {
        toast.info(t('queue.added_with_position', { position }));
      }
    },
    [steerMessage, enqueue, t],
  );

  /**
   * Steer 模式提交：中断当前任务的后续工具调用，立即转向新指令
   */
  const handleSteerSubmit = useCallback(async () => {
    if (!(await _validateAndPrepare())) {
      return;
    }
    clearDraft();
    recordChatQueryMetric();
    const steerText = composeOutboundUserMessage(inputMessage.trim());
    const injectedText = _injectDirtyArtifacts(steerText);

    setInputMessage('');
    clearPendingExplicitSkillActivation();
    await steerOrQueue(injectedText);
  }, [
    _validateAndPrepare,
    clearDraft,
    inputMessage,
    setInputMessage,
    steerOrQueue,
    _injectDirtyArtifacts,
    recordChatQueryMetric,
  ]);

  /**
   * Redirect 模式提交：立即中断模型生成，保留 partial 输出，注入纠偏指令
   */
  const handleRedirectSubmit = useCallback(async () => {
    if (!(await _validateAndPrepare())) {
      return;
    }
    clearDraft();
    recordChatQueryMetric();
    const redirectText = composeOutboundUserMessage(inputMessage.trim());
    const injectedText = _injectDirtyArtifacts(redirectText);

    setInputMessage('');
    clearPendingExplicitSkillActivation();
    if (await redirectMessage(injectedText)) {
      confirmInstructionLanded();
    } else {
      await steerOrQueue(injectedText);
    }
  }, [
    _validateAndPrepare,
    clearDraft,
    inputMessage,
    setInputMessage,
    redirectMessage,
    steerOrQueue,
    _injectDirtyArtifacts,
    recordChatQueryMetric,
  ]);

  /**
   * Queue 模式提交：不干扰当前任务，等完成后自动发送
   */
  const handleQueueSubmit = useCallback(
    async (queuedTurnSelection?: TurnCapabilitySelection | null, skipValidation: boolean = false) => {
      if (!skipValidation && !(await _validateAndPrepare())) {
        return;
      }
      clearDraft();
      recordChatQueryMetric();
      const queueText = composeOutboundUserMessage(inputMessage.trim());
      const injectedText = _injectDirtyArtifacts(queueText);
      const archiveRestoreActions = resolveArchiveRestoreActionsForMessage(injectedText, pendingArchiveRestoreActions);

      setInputMessage('');
      clearPendingExplicitSkillActivation();
      setPendingArchiveRestoreActions([]);
      const effectiveTurnSelection =
        queuedTurnSelection === undefined ? consumeTurnCapabilitySelection() : queuedTurnSelection;
      if (effectiveTurnSelection) {
        telemetry.recordSelectionSubmitted('queue_submit', effectiveTurnSelection);
        telemetry.recordQueueEnqueued('queue_submit', effectiveTurnSelection);
      }
      // The queued message owns the staged attachments; leaving them in the composer would attach them to the next message too.
      enqueue(injectedText, useChatStore.getState().files, archiveRestoreActions, effectiveTurnSelection);
      setFiles([]);
      toast.info(t('queue.added'));
    },
    [
      _validateAndPrepare,
      clearDraft,
      inputMessage,
      setInputMessage,
      setPendingArchiveRestoreActions,
      setFiles,
      enqueue,
      t,
      _injectDirtyArtifacts,
      pendingArchiveRestoreActions,
      recordChatQueryMetric,
      consumeTurnCapabilitySelection,
      telemetry,
    ],
  );

  const handleSubmit = useCallback(async () => {
    if (inputMessage.trim().length === 0 && files.length === 0) {
      if (!useChatStore.getState().pendingExplicitSkillActivation) {
        return;
      }
    }

    const trimmedLower = inputMessage.trim().toLowerCase();
    if (trimmedLower === '/compact' || trimmedLower.startsWith('/compact ')) {
      const focusTopic = inputMessage.trim().slice('/compact'.length).trim() || undefined;
      setInputMessage('');
      const skipWarning = localStorage.getItem('dontRemindCompact') === 'true';
      if (skipWarning) {
        await executeCompact(focusTopic);
      } else {
        pendingCompactTopicRef.current = focusTopic;
        setShowCompactConfirm(true);
      }
      return;
    }

    if (trimmedLower === '/pet' || trimmedLower.startsWith('/pet ')) {
      const { executePetSlashCommand } = await import('@/services/companion/petSlashCommand');
      const result = await executePetSlashCommand(inputMessage.trim());
      if (result.newInputValue !== undefined) {
        setInputMessage(result.newInputValue);
      }
      return;
    }

    const validateResult = await _validateAndPrepare();
    if (!validateResult) {
      return;
    }

    if (loading) {
      // Redirect and steer carry text only, so a message with attachments waits in the queue instead of dropping them.
      const mode = useChatStore.getState().files.length > 0 ? 'queue' : (agentConfig?.busyInputMode ?? 'redirect');
      switch (mode) {
        case 'redirect':
          await handleRedirectSubmit();
          break;
        case 'steer':
          await handleSteerSubmit();
          break;
        case 'queue':
          await handleQueueSubmit(undefined, true);
          break;
      }
      return;
    }

    clearDraft();
    if (!incognitoMode) {
      addInputHistory(inputMessage, useChatStore.getState().agentConfig?.agentId);
    }
    setHideAttachList(true);
    recordChatQueryMetric();

    setInputMessage('');
    const finalMessage = _injectDirtyArtifacts(composeOutboundUserMessage(inputMessage));
    const archiveRestoreActions = resolveArchiveRestoreActionsForMessage(finalMessage, pendingArchiveRestoreActions);
    setPendingArchiveRestoreActions([]);
    clearPendingExplicitSkillActivation();
    const currentTurnSelection = consumeTurnCapabilitySelection();
    const turnAgentConfigOverride = buildTurnAgentConfigOverride(agentConfig, currentTurnSelection) ?? undefined;
    if (currentTurnSelection) {
      telemetry.recordSelectionSubmitted('direct', currentTurnSelection);
    }
    // The store clears the composer attachments once the request settles; the busy fallback and the
    // archive-restore recovery below work from this snapshot instead of the already emptied composer.
    const sentFiles = useChatStore.getState().files;

    sendMessage(
      finalMessage,
      undefined,
      undefined,
      undefined,
      archiveRestoreActions,
      turnAgentConfigOverride,
      true,
      resolveTerminalTelemetry('direct', currentTurnSelection, turnAgentConfigOverride),
    )
      .then((dispatched) => {
        if (dispatched) {
          telemetry.recordSettled('direct', currentTurnSelection, turnAgentConfigOverride);
        }
      })
      .catch((error) => {
        if (error instanceof Error && error.name === 'AgentBusyError') {
          const position = enqueue(finalMessage, sentFiles, archiveRestoreActions, currentTurnSelection);
          if (currentTurnSelection) {
            telemetry.recordBusyRequeued('direct');
            telemetry.recordQueueEnqueued('busy_requeue', currentTurnSelection);
          }
          toast.info(t('queue.added_with_position', { position }));
          return;
        }
        telemetry.recordFailed('direct', currentTurnSelection, turnAgentConfigOverride, error);
        if (isArchiveRestoreActionInvalidError(error)) {
          setInputMessage(finalMessage);
          setFiles(sentFiles);
          setPendingArchiveRestoreActions(archiveRestoreActions ?? []);
          if (currentTurnSelection) {
            setTurnCapabilitySelection(currentTurnSelection);
          }
        }
      });
  }, [
    inputMessage,
    executeCompact,
    setInputMessage,
    _validateAndPrepare,
    handleQueueSubmit,
    handleSteerSubmit,
    handleRedirectSubmit,
    agentConfig,
    sendMessage,
    pendingArchiveRestoreActions,
    setPendingArchiveRestoreActions,
    setHideAttachList,
    t,
    clearDraft,
    loading,
    enqueue,
    files,
    _injectDirtyArtifacts,
    recordChatQueryMetric,
    consumeTurnCapabilitySelection,
    setTurnCapabilitySelection,
    setFiles,
    incognitoMode,
    telemetry,
  ]);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value;

      const httpMatch = newValue.match(/(^|[^@])(https?:\/\/[^\s]+)/);

      if (httpMatch && !dontRemindAgain) {
        const matchIndex = (httpMatch.index ?? 0) + (httpMatch[1] ? httpMatch[1].length : 0);
        setDetectedLink({
          text: httpMatch[2],
          position: matchIndex,
        });
        setShowLinkDialog(true);
      }

      setInputMessage(newValue);

      if (newValue.trim() === '' && files.length === 0) {
        clearCurrentSessionMessageId();
      }
    },
    [dontRemindAgain, files.length, setInputMessage, clearCurrentSessionMessageId],
  );

  /**
   * 添加@符号到链接前
   */
  const handleAddAtSymbol = useCallback(() => {
    if (detectedLink) {
      const { text, position } = detectedLink;
      const beforeMatch = inputMessage.substring(0, position);
      const afterMatch = inputMessage.substring(position);
      const processedValue = beforeMatch + '@' + afterMatch;

      setInputMessage(processedValue);

      setTimeout(() => {
        if (inputRef.current) {
          const newCursorPos = position + text.length + 1;
          inputRef.current.selectionStart = newCursorPos;
          inputRef.current.selectionEnd = newCursorPos;
          inputRef.current.focus();
        }
      }, 0);
    }

    if (dontRemindAgain) {
      localStorage.setItem('dontRemindLinkDialog', 'true');
    }

    setShowLinkDialog(false);
    setDetectedLink(null);
  }, [detectedLink, inputMessage, dontRemindAgain, setInputMessage]);

  /**
   * 跳过添加@符号
   */
  const handleSkipAtSymbol = useCallback(() => {
    if (dontRemindAgain) {
      localStorage.setItem('dontRemindLinkDialog', 'true');
    }
    setShowLinkDialog(false);
    setDetectedLink(null);
  }, [dontRemindAgain]);

  /**
   * 键盘快捷键监听
   */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeElement = document.activeElement;

      const isInputFocused =
        activeElement?.tagName === 'INPUT' ||
        activeElement?.tagName === 'TEXTAREA' ||
        activeElement?.hasAttribute('contenteditable');

      if (e.key === '/' && !isInputFocused) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  return {
    // State
    showLinkDialog,
    setShowLinkDialog,
    detectedLink,
    dontRemindAgain,
    setDontRemindAgain,
    isUploadingPaste,
    showCompactConfirm,
    setShowCompactConfirm,
    dontRemindCompact,
    setDontRemindCompact,
    turnCapabilitySelection,
    setTurnCapabilitySelection,

    // Refs
    inputRef,

    // Store state
    actionMode,
    setActionMode,
    files,
    setFiles,
    hideAttachList,
    setHideAttachList,
    stopMessage,
    clearCurrentSessionMessageId,
    inputMessage,
    setInputMessage,
    loading,

    // Queue state
    queue,
    queuePausedReason: pausedReason,
    queueEditingId: editingId,
    editMessage,
    removeMessage,
    clearQueue,
    reorder,
    setQueueEditingId: setEditingId,
    resumeQueue: resume,

    // Handlers
    handlePaste,
    handleDroppedFiles,
    handleSubmit,
    handleSteerSubmit,
    handleRedirectSubmit,
    handleQueueSubmit,
    handleInputChange,
    handleAddAtSymbol,
    handleSkipAtSymbol,
    executeCompact,
    confirmCompact: useCallback(() => {
      const topic = pendingCompactTopicRef.current;
      pendingCompactTopicRef.current = undefined;
      executeCompact(topic);
    }, [executeCompact]),
  };
};
