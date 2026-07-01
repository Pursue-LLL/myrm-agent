/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/store/chat/archiveRestoreActions::resolveArchiveRestoreActionsForMessage (POS: Typed archive restore action utility layer. Keeps parsing, normalization and send-time matching outside the chat stream reducer and input hook.)
 * - @/hooks/useInputFileUpload::useInputFileUpload (POS: 聊天输入文件上传 Hook)
 * - @/hooks/useMessageQueue::useMessageQueue (POS: 消息排队状态机)
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
import { useQuotaGuard } from '@/hooks/useQuotaGuard';
import { useSessionWuBurnTracker } from '@/hooks/useSessionWuBurnTracker';
import { useDraftPersistence } from '@/hooks/useDraftPersistence';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import { isArchiveRestoreActionInvalidError } from '@/lib/utils/networkResilience';

import { useMessageQueue } from '@/hooks/useMessageQueue';
import { useInputFileUpload } from '@/hooks/useInputFileUpload';
import { resolveArchiveRestoreActionsForMessage } from '@/store/chat/archiveRestoreActions';
import { addInputHistory } from '@/hooks/useInputHistory';

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
  } = useChatStore(
    useShallow((state) => ({
      chatId: state.chatId,
      sendMessage: state.sendMessage,
      steerMessage: state.steerMessage,
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
    })),
  );

  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const { validateMessageQuota } = useQuotaGuard();
  const { markBalanceBeforeSend, reportBurnAfterTask } = useSessionWuBurnTracker();
  const { isUploadingPaste, handlePaste, handleDroppedFiles } = useInputFileUpload({
    actionMode,
    files,
    setFiles,
    setHideAttachList,
  });

  // ─── 草稿持久化 ───
  const { initialDraft, clearDraft } = useDraftPersistence(chatId, inputMessage);

  // ─── 消息排队 ───
  const { queue, enqueue, dequeue, editMessage, removeMessage, clearQueue } = useMessageQueue(chatId);

  const prevLoadingRef = useRef(loading);

  useEffect(() => {
    if (prevLoadingRef.current && !loading) {
      reportBurnAfterTask();
    }
    prevLoadingRef.current = loading;
  }, [loading, reportBurnAfterTask]);

  // 监听 loading 状态变化，当 loading 变为 false 时，自动发送队列中的下一条消息
  useEffect(() => {
    if (!loading && queue.length > 0) {
      const nextMessage = dequeue();
      if (nextMessage) {
        // 延迟一点点发送，确保状态完全重置
        setTimeout(() => {
          sendMessage(nextMessage.text, undefined, undefined, undefined, nextMessage.archiveRestoreActions).catch(
            (error) => {
              if (error && error.name === 'AgentBusyError') {
                // 如果还是 busy，退回队列头部
                enqueue(nextMessage.text, nextMessage.files, nextMessage.archiveRestoreActions);
                return;
              }
              if (isArchiveRestoreActionInvalidError(error)) {
                setInputMessage(nextMessage.text);
                setFiles(nextMessage.files);
                setPendingArchiveRestoreActions(nextMessage.archiveRestoreActions ?? []);
              }
            },
          );
        }, 300);
      }
    }
  }, [
    loading,
    queue.length,
    dequeue,
    sendMessage,
    enqueue,
    setInputMessage,
    setFiles,
    setPendingArchiveRestoreActions,
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
    if (quota.remainingWu !== undefined) {
      markBalanceBeforeSend(quota.remainingWu);
    }

    return true;
  }, [inputMessage, files, actionMode, validateMessageQuota, markBalanceBeforeSend]);

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

  /**
   * Steer 模式提交：中断当前任务的后续工具调用，立即转向新指令
   */
  const handleSteerSubmit = useCallback(async () => {
    if (!(await _validateAndPrepare())) return;
    clearDraft();

    const steerText = inputMessage.trim();
    const injectedText = _injectDirtyArtifacts(steerText);

    setInputMessage('');
    const success = await steerMessage(injectedText);
    if (!success) {
      sendMessage(injectedText, undefined).catch(() => {});
    }
  }, [
    _validateAndPrepare,
    clearDraft,
    inputMessage,
    setInputMessage,
    steerMessage,
    sendMessage,
    _injectDirtyArtifacts,
  ]);

  /**
   * Queue 模式提交：不干扰当前任务，等完成后自动发送
   */
  const handleQueueSubmit = useCallback(async () => {
    if (!(await _validateAndPrepare())) return;
    clearDraft();

    const queueText = inputMessage.trim();
    const injectedText = _injectDirtyArtifacts(queueText);
    const archiveRestoreActions = resolveArchiveRestoreActionsForMessage(injectedText, pendingArchiveRestoreActions);

    setInputMessage('');
    setPendingArchiveRestoreActions([]);
    enqueue(injectedText, files, archiveRestoreActions);
    toast.info(t('queue.added'));
  }, [
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
  ]);

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
      await handleQueueSubmit();
      return;
    }

    clearDraft();
    addInputHistory(inputMessage, useChatStore.getState().agentConfig?.id);
    setHideAttachList(true);

    const finalMessage = _injectDirtyArtifacts(inputMessage);
    const archiveRestoreActions = resolveArchiveRestoreActionsForMessage(finalMessage, pendingArchiveRestoreActions);
    setPendingArchiveRestoreActions([]);

    sendMessage(finalMessage, undefined, undefined, undefined, archiveRestoreActions).catch((error) => {
      if (error && error.name === 'AgentBusyError') {
        enqueue(finalMessage, files, archiveRestoreActions);
        toast.info(t('queue.added'));
        return;
      }
      if (isArchiveRestoreActionInvalidError(error)) {
        setInputMessage(finalMessage);
        setFiles(files);
        setPendingArchiveRestoreActions(archiveRestoreActions ?? []);
      }
    });
  }, [
    inputMessage,
    executeCompact,
    setInputMessage,
    _validateAndPrepare,
    handleQueueSubmit,
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

    // Handlers
    handlePaste,
    handleDroppedFiles,
    handleSubmit,
    handleSteerSubmit,
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
