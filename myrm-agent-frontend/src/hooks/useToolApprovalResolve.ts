'use client';

import { useCallback } from 'react';
import { toast } from 'sonner';
import { useTranslations } from 'next-intl';

import { fetchWithTimeout } from '@/lib/api';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import type { ToolApprovalRequest } from '@/store/chat/types';
import { AdaptiveScheduler } from '@/store/chat/adaptiveScheduler';
import type { StreamHandlerState, StreamMutableState } from '@/store/chat/messageStreamHandler';
import {
  getModelSelection,
  getLiteModelSelection,
  getFallbackModelSelection,
  getFallbackLiteModelSelection,
} from '@/store/chat/messageRequest';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';

type DecisionType = 'approve' | 'edit' | 'reject';

interface ApprovalDecision {
  type: DecisionType;
  args?: Record<string, unknown>;
  feedback?: string;
  extensions: {
    allowAlways: boolean;
    allowDomain?: boolean;
  };
}

export interface ToolApprovalResolveExtra {
  edited_args?: Record<string, unknown>;
  feedback?: string;
  allow_always?: boolean | { tool?: boolean; args?: boolean };
  allow_domain?: boolean;
}

export function useToolApprovalResolve() {
  const t = useTranslations('toolApproval');
  const queue = useToolApprovalStore((state) => state.queue);
  const isLoading = useToolApprovalStore((state) => state.isResolving);
  const batchDecisions = useToolApprovalStore((state) => state.batchDecisions);
  const removeRequest = useToolApprovalStore((state) => state.removeRequest);
  const clearAll = useToolApprovalStore((state) => state.clearAll);
  const setResolving = useToolApprovalStore((state) => state.setResolving);
  const clearBatchDecisions = useToolApprovalStore((state) => state.clearBatchDecisions);

  const resolveRequest = useCallback(
    async (requestId: string, decision: DecisionType, extra?: ToolApprovalResolveExtra) => {
      setResolving(true);
      try {
        let request = queue.find((r) => r.requestId === requestId);
        if (!request) return;

        let resumeValue: { decisions: ApprovalDecision[] };

        if (request.batchId) {
          const nextDecisions = new Map(batchDecisions);
          nextDecisions.set(requestId, { type: decision, extra });
          useToolApprovalStore.setState({ batchDecisions: nextDecisions });

          const batchRequests = queue.filter((r) => r.batchId === request.batchId);
          const allDecided = batchRequests.every((r) => nextDecisions.has(r.requestId));

          if (!allDecided) {
            toast.info(
              t('batchPending', {
                decided: nextDecisions.size,
                total: batchRequests.length,
              }),
            );
            setResolving(false);
            return;
          }

          const sortedRequests = batchRequests.sort((a, b) => (a.batchIndex ?? 0) - (b.batchIndex ?? 0));
          const decisions = sortedRequests.map((r) => {
            const dec = nextDecisions.get(r.requestId)!;
            return {
              type: dec.type,
              args: dec.extra?.edited_args,
              feedback: dec.extra?.feedback,
              extensions: {
                allowAlways: dec.extra?.allow_always ?? false,
                ...(dec.extra?.allow_domain && { allowDomain: true }),
              },
            };
          });

          resumeValue = { decisions };
          request = sortedRequests[0];
          clearBatchDecisions();

          for (const req of batchRequests) {
            removeRequest(req.requestId);
          }
        } else {
          resumeValue = {
            decisions: [
              {
                type: decision,
                args: extra?.edited_args,
                feedback: extra?.feedback,
                extensions: {
                  allowAlways: extra?.allow_always ?? false,
                  ...(extra?.allow_domain && { allowDomain: true }),
                },
              },
            ],
          };
        }

        const { default: useChatStore } = await import('@/store/useChatStore');
        const chatState = useChatStore.getState();

        const modelSelection = getModelSelection(request.actionMode, chatState.agentConfig);
        const liteModelSelection = getLiteModelSelection();
        const fallbackModelSelection = getFallbackModelSelection(request.actionMode, chatState.agentConfig);
        const fallbackLiteModelSelection = getFallbackLiteModelSelection();

        if (!modelSelection) {
          toast.error(t('resumeError'));
          return;
        }

        const { createAISearchStream } = await import('@/services/chat');
        const requestBody = {
          query: '',
          message_id: request.messageId,
          chat_id: request.chatId,
          action_mode: request.actionMode,
          resume_value: resumeValue,
          model_selection: modelSelection,
          timezone: getBrowserTimezone(),
          ...(liteModelSelection && { lite_model_selection: liteModelSelection }),
          ...(fallbackModelSelection && { fallback_model_selection: fallbackModelSelection }),
          ...(fallbackLiteModelSelection && {
            fallback_lite_model_selection: fallbackLiteModelSelection,
          }),
          ...(chatState.agentConfig && {
            agent_config: {
              skill_ids: chatState.agentConfig.selectedSkillIds,
              enabled_builtin_tools: chatState.agentConfig.enabledBuiltinTools ?? [],
            },
          }),
        };

        const response = await createAISearchStream(requestBody, chatState.abortController || undefined);
        const { handleMessageStream } = await import('@/store/chat/messageStreamHandler');
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) {
          console.error('[APPROVAL] No response body');
          return;
        }

        let added = false;
        let recievedMessage = '';
        const sources: import('@/store/chat/types').Source[] = [];
        const scheduler = new AdaptiveScheduler();
        const streamState: StreamHandlerState = {
          messages: chatState.messages,
          messageAppeared: chatState.messageAppeared,
          loading: chatState.loading,
          scheduler,
        };

        const setMessagesAdapter = (updater: (state: StreamMutableState) => void) => {
          useChatStore.setState((draft) => {
            updater(draft);
          });
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n').filter((line) => line.trim().startsWith('data:'));

          for (const line of lines) {
            try {
              const json = JSON.parse(line.replace(/^data:\s*/, ''));
              const result = await handleMessageStream(json, '', sources, added, recievedMessage, streamState, {
                setMessages: setMessagesAdapter,
                setMessageAppeared: chatState.setMessageAppeared || (() => {}),
                setLoading: chatState.setLoading || (() => {}),
                _processSuggestions: chatState._processSuggestions || (async () => {}),
                scheduleAutoSave: chatState.scheduleAutoSave || (() => {}),
              });
              added = result.added;
              recievedMessage = result.recievedMessage;
            } catch (error) {
              console.error('[APPROVAL] Stream parse error:', error);
            }
          }
        }
        scheduler.flush();
        scheduler.cancel();
      } catch (error) {
        console.error('[APPROVAL] Resume failed:', error);
        toast.error(t('resumeError'));
      } finally {
        const originalRequest = queue.find((r) => r.requestId === requestId);
        if (originalRequest && !originalRequest.batchId) {
          removeRequest(requestId);
        }
        setResolving(false);
      }
    },
    [batchDecisions, clearBatchDecisions, queue, removeRequest, setResolving, t],
  );

  const approveAll = useCallback(async () => {
    setResolving(true);
    try {
      await Promise.all(
        queue.map((req) =>
          fetchWithTimeout(`/agents/approval/${req.requestId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ decision: 'approve', allow_always: false }),
          }).catch(() => {}),
        ),
      );
    } finally {
      clearAll();
      setResolving(false);
    }
  }, [clearAll, queue, setResolving]);

  const rejectAll = useCallback(async () => {
    setResolving(true);
    try {
      await Promise.all(
        queue.map((req) =>
          fetchWithTimeout(`/agents/approval/${req.requestId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              decision: 'reject',
              feedback: 'Batch rejected by user',
            }),
          }).catch(() => {}),
        ),
      );
    } finally {
      clearAll();
      setResolving(false);
    }
  }, [clearAll, queue, setResolving]);

  return {
    queue,
    isLoading,
    resolveRequest,
    approveAll,
    rejectAll,
  };
}

export type { ToolApprovalRequest };
