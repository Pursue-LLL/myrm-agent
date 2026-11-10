/**
 * [INPUT]
 * - useChatStore (POS: 消息发送、截图附件与流式状态)
 * - useFlowPadStore (POS: Inline 结果与生成态)
 * - formatAppshotMessage (POS: 截图上下文转消息)
 *
 * [OUTPUT]
 * - useFlowPadSend: 提交/快捷动作发送、Inline 请求级流式结果桥接与提交态。
 *
 * [POS]
 * FlowPad 发送层。Inline 模式下只认本次请求 ID 的助手消息并回写 inlineResult；
 * 被聊天拒绝的发送会结束生成态并撤回截图附件，输入保留以便重试。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import useChatStore from '@/store/useChatStore';
import { useFlowPadStore, type FlowPadCapture, type FlowPadMode } from '@/store/useFlowPadStore';
import { formatAppshotMessage } from './FlowPadModalParts';
import type { InlineRouteSelection } from './useFlowPadInlineRoute';

export type FlowPadQuickActionKey = 'replyPrompt' | 'summarizePrompt' | 'translatePrompt' | 'explainPrompt';

interface UseFlowPadSendOptions {
  isOpen: boolean;
  mode: FlowPadMode;
  captures: FlowPadCapture[];
  text: string;
  close: () => void;
  currentAgentLabel: string;
  inlineRouteSelection: InlineRouteSelection | null;
  inlineRouteSwitching: boolean;
  /** Credits the first message sent to a summoned expert. */
  reportSummonFirstMessage: () => void;
}

export function useFlowPadSend({
  isOpen,
  mode,
  captures,
  text,
  close,
  currentAgentLabel,
  inlineRouteSelection,
  inlineRouteSwitching,
  reportSummonFirstMessage,
}: UseFlowPadSendOptions) {
  const t = useTranslations('flowPad');
  const { sendMessage, setFiles, getCurrentSessionMessageId } = useChatStore();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inlineActiveRequestIdRef = useRef<string | null>(null);

  const resetInlineRequest = useCallback(() => {
    inlineActiveRequestIdRef.current = null;
  }, []);

  // Inline Mode: bridge streaming messages to inlineResult
  useEffect(() => {
    if (mode !== 'inline' || !isOpen) {
      return;
    }

    const unsub = useChatStore.subscribe((state, prev) => {
      if (!state.loading && !prev.loading) {
        return;
      }

      const inlineRequestId = inlineActiveRequestIdRef.current;
      if (!inlineRequestId) {
        if (prev.loading && !state.loading) {
          useFlowPadStore.setState({ inlineGenerating: false });
        }
        return;
      }

      const lastMsg = state.messages.findLast((m) => m.role === 'assistant' && m.messageId === inlineRequestId);
      if (lastMsg?.content) {
        useFlowPadStore.setState({ inlineResult: lastMsg.content, inlineGenerating: state.loading });
      }
      if (prev.loading && !state.loading) {
        inlineActiveRequestIdRef.current = null;
        useFlowPadStore.setState({ inlineGenerating: false });
      }
    });

    return () => unsub();
  }, [mode, isOpen]);

  /** Resolves false when the chat refused the message before the turn started (it has already told the user why). */
  const sendWithInlineRoute = useCallback(
    async (message: string): Promise<boolean> => {
      if (mode !== 'inline') {
        return sendMessage(message);
      }

      const inlineRequestId = getCurrentSessionMessageId();
      inlineActiveRequestIdRef.current = inlineRequestId;
      useFlowPadStore.setState({ inlineResult: '', inlineGenerating: true });

      let dispatched = false;
      try {
        if (inlineRouteSelection) {
          reportSummonFirstMessage();
          dispatched = await sendMessage(
            message,
            inlineRequestId,
            undefined,
            undefined,
            undefined,
            inlineRouteSelection.config,
          );
        } else {
          dispatched = await sendMessage(message, inlineRequestId);
        }
        return dispatched;
      } finally {
        // A turn that never started raises no loading transition, so nothing else would end the spinner.
        if (!dispatched) {
          inlineActiveRequestIdRef.current = null;
          useFlowPadStore.setState({ inlineGenerating: false });
        }
      }
    },
    [mode, inlineRouteSelection, sendMessage, getCurrentSessionMessageId, reportSummonFirstMessage],
  );

  /**
   * Sends the message with the captured screenshots attached to the composer. When the chat does not take the
   * message (refused or failed) the screenshots come back off, so a retry does not attach them twice.
   */
  const sendWithScreenshots = useCallback(
    async (message: string): Promise<boolean> => {
      const screenshotFiles = captures
        .filter((c) => c.screenshot)
        .map((c, idx) => ({
          fileName: `appshot_${idx + 1}.jpg`,
          fileExtension: 'jpg',
          fileUrl: `data:image/jpeg;base64,${c.screenshot}`,
          fileType: 'uploaded' as const,
        }));
      const composerFiles = useChatStore.getState().files;
      if (screenshotFiles.length > 0) {
        setFiles([...composerFiles, ...screenshotFiles]);
      }

      let dispatched = false;
      try {
        dispatched = await sendWithInlineRoute(message);
        return dispatched;
      } finally {
        if (!dispatched && screenshotFiles.length > 0) {
          setFiles(composerFiles);
        }
      }
    },
    [captures, setFiles, sendWithInlineRoute],
  );

  const announceSent = useCallback(() => {
    if (mode === 'inline') {
      toast.success(t('inlineSubmitted'), { duration: 2000 });
      return;
    }
    toast.success(t('submitted', { agent: currentAgentLabel }), { duration: 3000 });
    close();
  }, [mode, t, currentAgentLabel, close]);

  const handleSubmit = useCallback(async () => {
    const hasCaptures = captures.length > 0;
    const hasText = text.trim().length > 0;

    if (!hasCaptures && !hasText) {
      return;
    }
    if (isSubmitting) {
      return;
    }
    if (inlineRouteSwitching) {
      toast.warning(t('inlineRouteSwitchingBlocked'), { duration: 2000 });
      return;
    }

    setIsSubmitting(true);
    try {
      const parts: string[] = [];
      if (hasCaptures) {
        parts.push(formatAppshotMessage(captures));
      }
      if (hasText) {
        parts.push(text.trim());
      }

      const message = parts.join('\n\n');
      // A refusal has already been explained to the user: keep the pad and the typed text so they can adjust and retry.
      if (message && !(await sendWithScreenshots(message))) {
        return;
      }
      announceSent();
    } catch (err) {
      console.error('FlowPad submit failed:', err);
      toast.error(t('submitFailed'), { duration: 3000 });
    } finally {
      setIsSubmitting(false);
    }
  }, [captures, text, sendWithScreenshots, announceSent, t, isSubmitting, inlineRouteSwitching]);

  const handleQuickAction = useCallback(
    async (promptKey: FlowPadQuickActionKey) => {
      if (isSubmitting || captures.length === 0) {
        return;
      }
      if (inlineRouteSwitching) {
        toast.warning(t('inlineRouteSwitchingBlocked'), { duration: 2000 });
        return;
      }

      setIsSubmitting(true);
      try {
        const message = `${formatAppshotMessage(captures)}\n\n${t(promptKey)}`;
        if (!(await sendWithScreenshots(message))) {
          return;
        }
        announceSent();
      } catch (err) {
        console.error('FlowPad quick action failed:', err);
        toast.error(t('submitFailed'), { duration: 3000 });
      } finally {
        setIsSubmitting(false);
      }
    },
    [isSubmitting, captures, sendWithScreenshots, announceSent, t, inlineRouteSwitching],
  );

  return { isSubmitting, handleSubmit, handleQuickAction, resetInlineRequest };
}
