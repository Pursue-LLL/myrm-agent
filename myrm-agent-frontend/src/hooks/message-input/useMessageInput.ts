/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/store/chat/archiveRestoreActions::resolveArchiveRestoreActionsForMessage (POS: Typed archive restore action utility layer. Keeps parsing, normalization and send-time matching outside the chat stream reducer and input hook.)
 * - @/hooks/message-input/useInputFileUpload::useInputFileUpload (POS: 聊天输入文件上传 Hook)
 * - @/hooks/message-input/useMessageQueue::useMessageQueue (POS: 消息排队状态机)
 * - @/hooks/message-input/useMessageInputWikiEvidenceCore::recordChatWikiQueryAttempt (POS: Chat 输入链路的 Wiki 证据复问口径核心)
 * - @/hooks/message-input/useMessageInputWikiEvidenceCore::queuePendingChatWikiQuerySuccess (POS: steer success 延迟确认注册)
 * - @/services/turnCapabilityMetrics::recordTurnCapability* (POS: 单轮 Skill/MCP 能力覆写可观测埋点)
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
import { compactChat } from '@/services/chat';
import { toast } from '@/lib/utils/toast';
import { useQuotaGuard } from '@/hooks/billing/useQuotaGuard';
import { useDraftPersistence } from '@/hooks/shared/useDraftPersistence';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import { FatalNetworkError, isArchiveRestoreActionInvalidError } from '@/lib/utils/networkResilience';
import { useMessageQueue } from './useMessageQueue';
import { useInputFileUpload } from './useInputFileUpload';
import { resolveArchiveRestoreActionsForMessage } from '@/store/chat/archiveRestoreActions';
import { recordChatWikiQueryAttempt, queuePendingChatWikiQuerySuccess } from './useMessageInputWikiEvidenceCore';
import { addInputHistory } from './useInputHistory';
import {
  buildTurnAgentConfigOverride,
  type TurnCapabilitySelection,
} from './turnCapabilityOverrideCore';
import {
  recordTurnCapabilityBusyRequeued,
  recordTurnCapabilityOverrideApplied,
  recordTurnCapabilityOverrideNoop,
  recordTurnCapabilityQueueEnqueued,
  recordTurnCapabilitySelectionSubmitted,
  recordTurnCapabilitySendCompleted,
  recordTurnCapabilitySendFailed,
  type TurnCapabilityFailureReason,
  type TurnCapabilityMetricSource,
} from '@/services/turnCapabilityMetrics';
const MAX_DRAIN_RETRIES = 4;

function getOptionalSelectionCount(values: readonly string[] | null): number | undefined {
  return values === null ? undefined : values.length;
}

function classifyTurnCapabilityFailureReason(error: unknown): TurnCapabilityFailureReason {
  if (isArchiveRestoreActionInvalidError(error)) {
    return 'archive_restore_invalid';
  }
  if (error instanceof Error) {
    if (error.name === 'AbortError') {
      return 'abort';
    }
    if (error instanceof FatalNetworkError && typeof error.status === 'number' && error.status >= 500) {
      return 'server_error';
    }
    const combined = `${error.name} ${error.message}`.toLowerCase();
    if (
      combined.includes('network') ||
      combined.includes('timeout') ||
      combined.includes('fetch') ||
      combined.includes('connection')
    ) {
      return 'network_error';
    }
    if (combined.includes('server') || combined.includes('http') || combined.includes('status')) {
      return 'server_error';
    }
    return 'unknown_error';
  }
  if (error && typeof error === 'object') {
    const maybeMessage = (error as { message?: unknown }).message;
    if (typeof maybeMessage === 'string') {
      const lowerMessage = maybeMessage.toLowerCase();
      if (lowerMessage.includes('network') || lowerMessage.includes('timeout') || lowerMessage.includes('fetch')) {
        return 'network_error';
      }
      if (lowerMessage.includes('server') || lowerMessage.includes('http') || lowerMessage.includes('status')) {
        return 'server_error';
      }
    }
  }
  return 'unknown_error';
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

  // ─── 草稿持久化 ───
  const { initialDraft, clearDraft } = useDraftPersistence(chatId, inputMessage);

  // ─── 消息排队 ───
  const { queue, enqueue, dequeue, editMessage, removeMessage, clearQueue, requeue, reorder } = useMessageQueue(chatId);
  const [turnCapabilitySelection, setTurnCapabilitySelection] = useState<TurnCapabilitySelection | null>(null);
  const agentSkillSignature = (agentConfig?.selectedSkillIds ?? []).join('\u0001');
  const agentMcpSignature = (agentConfig?.selectedMcpNames ?? []).join('\u0001');
  const turnCapabilityContextKey = chatId ? `chat:${chatId}` : undefined;

  const recordTurnSelectionSubmitted = useCallback(
    (source: TurnCapabilityMetricSource, selection: TurnCapabilitySelection) => {
      recordTurnCapabilitySelectionSubmitted(
        source,
        getOptionalSelectionCount(selection.skillIds),
        getOptionalSelectionCount(selection.mcpNames),
        turnCapabilityContextKey,
      );
    },
    [turnCapabilityContextKey],
  );

  const recordTurnOverrideApplied = useCallback(
    (source: TurnCapabilityMetricSource, selection: TurnCapabilitySelection, effectiveSkillCount: number, effectiveMcpCount: number) => {
      recordTurnCapabilityOverrideApplied(
        source,
        getOptionalSelectionCount(selection.skillIds),
        getOptionalSelectionCount(selection.mcpNames),
        effectiveSkillCount,
        effectiveMcpCount,
        turnCapabilityContextKey,
      );
    },
    [turnCapabilityContextKey],
  );

  const recordTurnOverrideNoop = useCallback(
    (source: TurnCapabilityMetricSource, selection: TurnCapabilitySelection) => {
      recordTurnCapabilityOverrideNoop(
        source,
        getOptionalSelectionCount(selection.skillIds),
        getOptionalSelectionCount(selection.mcpNames),
        turnCapabilityContextKey,
      );
    },
    [turnCapabilityContextKey],
  );

  const recordTurnQueueEnqueued = useCallback(
    (source: TurnCapabilityMetricSource, selection: TurnCapabilitySelection) => {
      recordTurnCapabilityQueueEnqueued(
        source,
        getOptionalSelectionCount(selection.skillIds),
        getOptionalSelectionCount(selection.mcpNames),
        turnCapabilityContextKey,
      );
    },
    [turnCapabilityContextKey],
  );

  const consumeTurnCapabilitySelection = useCallback(() => {
    if (!turnCapabilitySelection) {
      return null;
    }
    const consumed = turnCapabilitySelection;
    setTurnCapabilitySelection(null);
    return consumed;
  }, [turnCapabilitySelection]);

  const drainFailCountRef = useRef(0);

  useEffect(() => {
    setTurnCapabilitySelection(null);
  }, [chatId, agentConfig?.agentId, agentSkillSignature, agentMcpSignature]);

  // busy→idle 时重置重试计数，允许后续 auto-drain 正常工作
  useEffect(() => {
    if (loading) {
      drainFailCountRef.current = 0;
    }
  }, [loading]);

  useEffect(() => {
    if (loading || queue.length === 0 || drainFailCountRef.current >= MAX_DRAIN_RETRIES) {
      return;
    }

    const nextMessage = dequeue();
    if (!nextMessage) return;

    setTimeout(() => {
      const queuedTurnSelection = nextMessage.turnCapabilitySelection ?? null;
      const queuedAgentConfigOverride =
        buildTurnAgentConfigOverride(useChatStore.getState().agentConfig, queuedTurnSelection) ?? undefined;
      sendMessage(
        nextMessage.text,
        undefined,
        undefined,
        undefined,
        nextMessage.archiveRestoreActions,
        queuedAgentConfigOverride,
        true,
      )
        .then(() => {
          if (queuedTurnSelection) {
            if (queuedAgentConfigOverride) {
              recordTurnOverrideApplied(
                'queue_drain',
                queuedTurnSelection,
                queuedAgentConfigOverride.selectedSkillIds.length,
                queuedAgentConfigOverride.selectedMcpNames.length,
              );
              recordTurnCapabilitySendCompleted(
                'queue_drain',
                queuedAgentConfigOverride.selectedSkillIds.length,
                queuedAgentConfigOverride.selectedMcpNames.length,
                turnCapabilityContextKey,
              );
            } else {
              recordTurnOverrideNoop('queue_drain', queuedTurnSelection);
            }
          }
        })
        .catch((error) => {
          if (error && error.name === 'AgentBusyError') {
            drainFailCountRef.current += 1;
            requeue(nextMessage);
            if (queuedTurnSelection) {
              recordTurnCapabilityBusyRequeued('queue_drain', turnCapabilityContextKey);
            }
            if (drainFailCountRef.current >= MAX_DRAIN_RETRIES) {
              toast.error(t('queue.stuck'));
            }
            return;
          }
          if (queuedTurnSelection) {
            if (queuedAgentConfigOverride) {
              recordTurnOverrideApplied(
                'queue_drain',
                queuedTurnSelection,
                queuedAgentConfigOverride.selectedSkillIds.length,
                queuedAgentConfigOverride.selectedMcpNames.length,
              );
              recordTurnCapabilitySendFailed(
                'queue_drain',
                classifyTurnCapabilityFailureReason(error),
                turnCapabilityContextKey,
              );
            } else {
              recordTurnOverrideNoop('queue_drain', queuedTurnSelection);
            }
          }
          if (isArchiveRestoreActionInvalidError(error)) {
            setInputMessage(nextMessage.text);
            setFiles(nextMessage.files);
            setPendingArchiveRestoreActions(nextMessage.archiveRestoreActions ?? []);
          }
        });
    }, 300);
  }, [
    loading,
    queue.length,
    dequeue,
    sendMessage,
    requeue,
    setInputMessage,
    setFiles,
    setPendingArchiveRestoreActions,
    turnCapabilityContextKey,
    recordTurnOverrideApplied,
    recordTurnOverrideNoop,
    t,
  ]);

  // 仅在组件挂载且有草稿，且当前输入框为空时恢复草稿
  useEffect(() => {
    if (initialDraft && !inputMessage) {
      setInputMessage(initialDraft);
    }
  }, [initialDraft, setInputMessage]); // 故意不将 inputMessage 放入依赖，只在 initialDraft 变化时触发

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
    if (inputMessage.trim().length === 0 && files.length === 0) return false;

    const { actionMode } = useChatStore.getState();

    const quota = await validateMessageQuota(inputMessage.trim().length, files.length > 0, actionMode);
    if (!quota.allowed) {
      return false;
    }
    return true;
  }, [inputMessage, files, actionMode, validateMessageQuota]);

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

  /**
   * Steer 模式提交：中断当前任务的后续工具调用，立即转向新指令
   */
  const handleSteerSubmit = useCallback(async () => {
    if (!(await _validateAndPrepare())) return;
    clearDraft();
    recordChatQueryMetric();
    const steerText = inputMessage.trim();
    const injectedText = _injectDirtyArtifacts(steerText);

    setInputMessage('');
    const success = await steerMessage(injectedText);
    if (success) {
      const chatState = useChatStore.getState();
      const currentSessionMessageId =
        typeof chatState.getCurrentSessionMessageId === 'function'
          ? chatState.getCurrentSessionMessageId()
          : undefined;
      queuePendingChatWikiQuerySuccess(chatState.messages, chatState.chatId, currentSessionMessageId);
    } else {
      sendMessage(injectedText, undefined, undefined, undefined, undefined, undefined, true).catch(() => {});
    }
  }, [
    _validateAndPrepare,
    clearDraft,
    inputMessage,
    setInputMessage,
    steerMessage,
    sendMessage,
    _injectDirtyArtifacts,
    recordChatQueryMetric,
    queuePendingChatWikiQuerySuccess,
  ]);

  /**
   * Redirect 模式提交：立即中断模型生成，保留 partial 输出，注入纠偏指令
   */
  const handleRedirectSubmit = useCallback(async () => {
    if (!(await _validateAndPrepare())) return;
    clearDraft();
    recordChatQueryMetric();
    const redirectText = inputMessage.trim();
    const injectedText = _injectDirtyArtifacts(redirectText);

    setInputMessage('');
    const success = await redirectMessage(injectedText);
    if (success) {
      const chatState = useChatStore.getState();
      const currentSessionMessageId =
        typeof chatState.getCurrentSessionMessageId === 'function'
          ? chatState.getCurrentSessionMessageId()
          : undefined;
      queuePendingChatWikiQuerySuccess(chatState.messages, chatState.chatId, currentSessionMessageId);
    } else {
      await handleSteerSubmit();
    }
  }, [
    _validateAndPrepare,
    clearDraft,
    inputMessage,
    setInputMessage,
    redirectMessage,
    handleSteerSubmit,
    _injectDirtyArtifacts,
    recordChatQueryMetric,
    queuePendingChatWikiQuerySuccess,
  ]);

  /**
   * Queue 模式提交：不干扰当前任务，等完成后自动发送
   */
  const handleQueueSubmit = useCallback(
    async (queuedTurnSelection?: TurnCapabilitySelection | null, skipValidation: boolean = false) => {
      if (!skipValidation && !(await _validateAndPrepare())) return;
      clearDraft();
      recordChatQueryMetric();
      const queueText = inputMessage.trim();
      const injectedText = _injectDirtyArtifacts(queueText);
      const archiveRestoreActions = resolveArchiveRestoreActionsForMessage(injectedText, pendingArchiveRestoreActions);

      setInputMessage('');
      setPendingArchiveRestoreActions([]);
      const effectiveTurnSelection =
        queuedTurnSelection === undefined ? consumeTurnCapabilitySelection() : queuedTurnSelection;
      if (effectiveTurnSelection) {
        recordTurnSelectionSubmitted('queue_submit', effectiveTurnSelection);
        recordTurnQueueEnqueued('queue_submit', effectiveTurnSelection);
      }
      enqueue(injectedText, files, archiveRestoreActions, effectiveTurnSelection);
      toast.info(t('queue.added'));
    },
    [
      _validateAndPrepare,
      clearDraft,
      inputMessage,
      setInputMessage,
      setPendingArchiveRestoreActions,
      enqueue,
      files,
      t,
      _injectDirtyArtifacts,
      pendingArchiveRestoreActions,
      recordChatQueryMetric,
      consumeTurnCapabilitySelection,
      recordTurnSelectionSubmitted,
      recordTurnQueueEnqueued,
    ],
  );

  const handleSubmit = useCallback(async () => {
    if (inputMessage.trim().length === 0 && files.length === 0) {
      return;
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

    const validateResult = await _validateAndPrepare();
    if (!validateResult) {
      return;
    }

    if (loading) {
      const mode = agentConfig?.busyInputMode ?? 'redirect';
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
    addInputHistory(inputMessage, useChatStore.getState().agentConfig?.id);
    setHideAttachList(true);
    recordChatQueryMetric();

    const finalMessage = _injectDirtyArtifacts(inputMessage);
    const archiveRestoreActions = resolveArchiveRestoreActionsForMessage(finalMessage, pendingArchiveRestoreActions);
    setPendingArchiveRestoreActions([]);
    const currentTurnSelection = consumeTurnCapabilitySelection();
    const turnAgentConfigOverride = buildTurnAgentConfigOverride(agentConfig, currentTurnSelection) ?? undefined;
    if (currentTurnSelection) {
      recordTurnSelectionSubmitted('direct', currentTurnSelection);
    }

    sendMessage(finalMessage, undefined, undefined, undefined, archiveRestoreActions, turnAgentConfigOverride, true)
      .then(() => {
        if (currentTurnSelection) {
          if (turnAgentConfigOverride) {
            recordTurnOverrideApplied(
              'direct',
              currentTurnSelection,
              turnAgentConfigOverride.selectedSkillIds.length,
              turnAgentConfigOverride.selectedMcpNames.length,
            );
            recordTurnCapabilitySendCompleted(
              'direct',
              turnAgentConfigOverride.selectedSkillIds.length,
              turnAgentConfigOverride.selectedMcpNames.length,
              turnCapabilityContextKey,
            );
          } else {
            recordTurnOverrideNoop('direct', currentTurnSelection);
          }
        }
      })
      .catch((error) => {
        if (error && error.name === 'AgentBusyError') {
          enqueue(finalMessage, files, archiveRestoreActions, currentTurnSelection);
          if (currentTurnSelection) {
            recordTurnCapabilityBusyRequeued('direct', turnCapabilityContextKey);
            recordTurnQueueEnqueued('busy_requeue', currentTurnSelection);
          }
          toast.info(t('queue.added_with_position', { position: queue.length + 1 }));
          return;
        }
        if (currentTurnSelection) {
          if (turnAgentConfigOverride) {
            recordTurnOverrideApplied(
              'direct',
              currentTurnSelection,
              turnAgentConfigOverride.selectedSkillIds.length,
              turnAgentConfigOverride.selectedMcpNames.length,
            );
            recordTurnCapabilitySendFailed(
              'direct',
              classifyTurnCapabilityFailureReason(error),
              turnCapabilityContextKey,
            );
          } else {
            recordTurnOverrideNoop('direct', currentTurnSelection);
          }
        }
        if (isArchiveRestoreActionInvalidError(error)) {
          setInputMessage(finalMessage);
          setFiles(files);
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
    recordTurnSelectionSubmitted,
    recordTurnOverrideApplied,
    recordTurnOverrideNoop,
    recordTurnQueueEnqueued,
    turnCapabilityContextKey,
  ]);
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value;

      const httpMatch = newValue.match(/(^|[^@])(https?:\/\/[^\s]+)/);

      if (httpMatch && !dontRemindAgain) {
        const matchIndex = httpMatch.index! + (httpMatch[1] ? httpMatch[1].length : 0);
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
    editMessage,
    removeMessage,
    clearQueue,
    reorder,

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
