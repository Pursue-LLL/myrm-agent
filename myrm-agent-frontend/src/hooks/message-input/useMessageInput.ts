/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/store/chat/archiveRestoreActions::resolveArchiveRestoreActionsForMessage (POS: Typed archive restore action utility layer. Keeps parsing, normalization and send-time matching outside the chat stream reducer and input hook.)
 * - @/hooks/message-input/useInputFileUpload::useInputFileUpload (POS: 聊天输入文件上传 Hook)
 * - @/hooks/message-input/useLinkAtPrompt::useLinkAtPrompt (POS: 输入里没加 @ 的链接的询问)
 * - @/hooks/message-input/useMessageQueue::useMessageQueue (POS: 排队消息的 React 视图层)
 * - @/hooks/message-input/useQueueDrain::useQueueDrain (POS: 排队消息发送循环)
 * - @/hooks/message-input/messageInputKeyRouter::resolveBusySubmitMode (POS: 聊天输入框双通道键盘交互路由核心)
 * - @/hooks/message-input/turnCapabilityTelemetry::useTurnCapabilityTelemetry (POS: 单轮能力覆写埋点编排)
 * - @/hooks/message-input/useTurnCapabilitySelection::useTurnCapabilitySelection (POS: 仅本轮能力覆写的暂存与消费)
 * - @/hooks/message-input/useCompactChat::useCompactChat (POS: /compact 的确认对话框与执行)
 * - @/hooks/message-input/useSubmitGate::useSubmitGate (POS: 提交门禁，判定这条提交能否发出)
 * - @/hooks/message-input/messageInputOutbound::composeOutboundUserMessage (POS: 提交前后对 store 的读写，四条提交路径共用)
 *
 * [OUTPUT]
 * - useMessageInput: exposes chat input state, upload handling and submit handlers.
 *
 * [POS]
 * 聊天输入业务 Hook。封装输入框状态、附件上传、草稿、排队发送和提交编排。
 */

import { useRef, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import useChatStore from '@/store/useChatStore';
import { toast } from '@/lib/utils/toast';
import { isTextEntry } from '@/lib/utils/textEntry';
import { useDraftPersistence } from '@/hooks/shared/useDraftPersistence';
import { isArchiveRestoreActionInvalidError } from '@/lib/utils/networkResilience';
import { useMessageQueue } from './useMessageQueue';
import { useQueueDrain } from './useQueueDrain';
import { resolveBusySubmitMode } from './messageInputKeyRouter';
import { useInputFileUpload } from './useInputFileUpload';
import { useLinkAtPrompt } from './useLinkAtPrompt';
import { resolveArchiveRestoreActionsForMessage } from '@/store/chat/archiveRestoreActions';
import { addInputHistory } from './useInputHistory';
import { useCompactChat } from './useCompactChat';
import {
  clearPendingExplicitSkillActivation,
  composeOutboundUserMessage,
  confirmInstructionLanded,
  injectDirtyArtifacts,
  recordChatQueryMetric,
} from './messageInputOutbound';
import { buildTurnAgentConfigOverride, type TurnCapabilitySelection } from './turnCapabilityOverrideCore';
import { resolveTerminalTelemetry, useTurnCapabilityTelemetry } from './turnCapabilityTelemetry';
import { useSubmitGate } from './useSubmitGate';
import { useTurnCapabilitySelection } from './useTurnCapabilitySelection';

export const useMessageInput = () => {
  const t = useTranslations('chat');
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
      loading: state.loading,
      agentConfig: state.agentConfig,
      incognitoMode: state.incognitoMode,
    })),
  );

  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const linkPrompt = useLinkAtPrompt({ inputMessage, setInputMessage, inputRef });

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
  const { turnCapabilitySelection, setTurnCapabilitySelection, consumeTurnCapabilitySelection } =
    useTurnCapabilitySelection(chatId, agentConfig);
  const {
    showCompactConfirm,
    setShowCompactConfirm,
    dontRemindCompact,
    setDontRemindCompact,
    executeCompact,
    requestCompact,
    confirmCompact,
  } = useCompactChat(chatId);

  // 仅在草稿变化且当前输入框为空时恢复草稿；读取最新 store 值而非渲染闭包，避免用户输入触发重复恢复
  useEffect(() => {
    if (initialDraft && !useChatStore.getState().inputMessage) {
      setInputMessage(initialDraft);
    }
  }, [initialDraft, setInputMessage]);

  const _validateAndPrepare = useSubmitGate(inputMessage, files);

  // Steer only reaches a registered, running turn. When the turn cannot take the instruction (it is still starting or
  // has just ended, or the request failed) `steerMessage` resolves false and the instruction joins the queue, so it is
  // never dropped: it waits behind earlier queued messages, Stop holds it like any other, and the drain sends it at
  // once if the agent is already idle.
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
    const injectedText = injectDirtyArtifacts(steerText);

    setInputMessage('');
    clearPendingExplicitSkillActivation();
    await steerOrQueue(injectedText);
  }, [_validateAndPrepare, clearDraft, inputMessage, setInputMessage, steerOrQueue]);

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
    const injectedText = injectDirtyArtifacts(redirectText);

    setInputMessage('');
    clearPendingExplicitSkillActivation();
    if (await redirectMessage(injectedText)) {
      confirmInstructionLanded();
    } else {
      await steerOrQueue(injectedText);
    }
  }, [_validateAndPrepare, clearDraft, inputMessage, setInputMessage, redirectMessage, steerOrQueue]);

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
      const injectedText = injectDirtyArtifacts(queueText);
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
      pendingArchiveRestoreActions,
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
      await requestCompact(focusTopic);
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
      switch (resolveBusySubmitMode(useChatStore.getState().files.length > 0, agentConfig?.busyInputMode)) {
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
    const finalMessage = injectDirtyArtifacts(composeOutboundUserMessage(inputMessage));
    const archiveRestoreActions = resolveArchiveRestoreActionsForMessage(finalMessage, pendingArchiveRestoreActions);
    setPendingArchiveRestoreActions([]);
    clearPendingExplicitSkillActivation();
    const currentTurnSelection = consumeTurnCapabilitySelection();
    const turnAgentConfigOverride = buildTurnAgentConfigOverride(agentConfig, currentTurnSelection) ?? undefined;
    if (currentTurnSelection) {
      telemetry.recordSelectionSubmitted('direct', currentTurnSelection);
    }
    // The store clears the composer attachments once the request settles; the busy fallback and the
    // restore of a refused send below work from this snapshot instead of the already emptied composer.
    const sentFiles = useChatStore.getState().files;
    const sentChatId = useChatStore.getState().chatId;
    // A send the agent never took must not eat the draft: put it back unless the user already moved on.
    const restoreUnsentDraft = () => {
      const live = useChatStore.getState();
      // Refusals that return before the request starts leave this very array in the store; anything else
      // non-empty means the user attached something new meanwhile.
      const filesUntouched = live.files.length === 0 || live.files === sentFiles;
      if (live.chatId !== sentChatId || live.inputMessage.trim() || !filesUntouched) {
        return;
      }
      setInputMessage(finalMessage);
      setFiles(sentFiles);
      setHideAttachList(false);
      setPendingArchiveRestoreActions(archiveRestoreActions ?? []);
      if (currentTurnSelection) {
        setTurnCapabilitySelection(currentTurnSelection);
      }
    };

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
        } else {
          restoreUnsentDraft();
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
          restoreUnsentDraft();
        }
      });
  }, [
    inputMessage,
    requestCompact,
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
    consumeTurnCapabilitySelection,
    setTurnCapabilitySelection,
    setFiles,
    incognitoMode,
    telemetry,
  ]);

  const { detectLink } = linkPrompt;
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value;

      detectLink(newValue);
      setInputMessage(newValue);

      if (newValue.trim() === '' && files.length === 0) {
        clearCurrentSessionMessageId();
      }
    },
    [detectLink, files.length, setInputMessage, clearCurrentSessionMessageId],
  );

  /**
   * 键盘快捷键监听
   */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && !isTextEntry(document.activeElement)) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  return {
    // State
    showLinkDialog: linkPrompt.showLinkDialog,
    dontRemindAgain: linkPrompt.dontRemindAgain,
    setDontRemindAgain: linkPrompt.setDontRemindAgain,
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
    handleAddAtSymbol: linkPrompt.handleAddAtSymbol,
    handleSkipAtSymbol: linkPrompt.handleSkipAtSymbol,
    executeCompact,
    confirmCompact,
  };
};
