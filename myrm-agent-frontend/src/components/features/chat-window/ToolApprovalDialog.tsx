'use client';

import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ShieldAlert, CheckCircle2, Hand, MessageSquareX } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { fetchWithTimeout } from '@/lib/api';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import type { ToolApprovalRequest, Source } from '@/store/chat/types';
import { AdaptiveScheduler } from '@/store/chat/adaptiveScheduler';
import type { StreamHandlerState, StreamMutableState } from '@/store/chat/messageStreamHandler';
import {
  getModelSelection,
  getLiteModelSelection,
  getFallbackModelSelection,
  getFallbackLiteModelSelection,
} from '@/store/chat/messageRequest';
import SingleApprovalCard from './SingleApprovalCard';
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

export default function ToolApprovalDialog() {
  const t = useTranslations('toolApproval');
  const { queue, removeRequest, clearAll } = useToolApprovalStore();
  const [isLoading, setIsLoading] = useState(false);
  const toastFiredRef = useRef<Set<string>>(new Set());
  const [batchDecisions, setBatchDecisions] = useState<
    Map<
      string,
      {
        type: DecisionType;
        extra?: {
          edited_args?: Record<string, unknown>;
          feedback?: string;
          allow_always?: boolean;
          allow_domain?: boolean;
        };
      }
    >
  >(new Map());

  // Group requests by batchId
  const { batchGroups, singleRequests } = useMemo(() => {
    const batches: Map<string, ToolApprovalRequest[]> = new Map();
    const singles: ToolApprovalRequest[] = [];

    for (const req of queue) {
      if (req.batchId) {
        const group = batches.get(req.batchId) || [];
        group.push(req);
        batches.set(req.batchId, group);
      } else {
        singles.push(req);
      }
    }

    // Sort batch groups by batchIndex
    for (const group of batches.values()) {
      group.sort((a, b) => (a.batchIndex ?? 0) - (b.batchIndex ?? 0));
    }

    return {
      batchGroups: Array.from(batches.entries()),
      singleRequests: singles,
    };
  }, [queue]);

  const handleResolve = useCallback(
    async (
      requestId: string,
      decision: DecisionType,
      extra?: {
        edited_args?: Record<string, unknown>;
        feedback?: string;
        allow_always?: boolean;
        allow_domain?: boolean;
      },
    ) => {
      setIsLoading(true);
      try {
        let request = queue.find((r) => r.requestId === requestId);
        if (!request) return;

        let resumeValue: { decisions: ApprovalDecision[] };

        // Check if this is part of a batch
        if (request.batchId) {
          // Batch approval: collect decision for this tool
          const newDecisions = new Map(batchDecisions);
          newDecisions.set(requestId, { type: decision, extra });
          setBatchDecisions(newDecisions);

          // Check if all tools in batch have decisions
          const batchRequests = queue.filter((r) => r.batchId === request.batchId);
          const allDecided = batchRequests.every((r) => newDecisions.has(r.requestId));

          if (!allDecided) {
            // Wait for other tools' decisions
            toast.info(
              t('batchPending', {
                decided: newDecisions.size,
                total: batchRequests.length,
              }),
            );
            setIsLoading(false);
            return;
          }

          // All tools decided, construct batch resume_value
          const sortedRequests = batchRequests.sort((a, b) => (a.batchIndex ?? 0) - (b.batchIndex ?? 0));
          const decisions = sortedRequests.map((r) => {
            const dec = newDecisions.get(r.requestId)!;
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

          // Use first request's context for resume
          request = sortedRequests[0];

          // Clean up batch decisions
          setBatchDecisions(new Map());

          // Remove all batch requests after submission
          for (const req of batchRequests) {
            removeRequest(req.requestId);
          }
        } else {
          // Single approval: construct single-decision resume_value
          const singleDecision = {
            type: decision,
            args: extra?.edited_args,
            feedback: extra?.feedback,
            extensions: {
              allowAlways: extra?.allow_always ?? false,
              ...(extra?.allow_domain && { allowDomain: true }),
            },
          };

          resumeValue = { decisions: [singleDecision] };

          // Single request: will be removed in finally block
        }

        // 获取当前 chat 状态
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

        // 重新调用 agent-stream，传入 resume_value
        const { createAISearchStream } = await import('@/services/chat');

        // Resume 请求必须包含原始请求的 model_selection 等配置
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

        // 复用现有的 stream 处理逻辑
        const { handleMessageStream } = await import('@/store/chat/messageStreamHandler');
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) {
          console.error('[APPROVAL] No response body');
          return;
        }

        let added = false;
        let recievedMessage = '';
        const sources: Source[] = [];
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
            } catch (e) {
              console.error('[APPROVAL] Stream parse error:', e);
            }
          }
        }
        scheduler.flush();
        scheduler.cancel();
      } catch (error) {
        console.error('[APPROVAL] Resume failed:', error);
        toast.error(t('resumeError'));
      } finally {
        // Only remove single requests here; batch requests already removed above
        const originalRequest = queue.find((r) => r.requestId === requestId);
        if (originalRequest && !originalRequest.batchId) {
          removeRequest(requestId);
        }
        setIsLoading(false);
      }
    },
    [queue, removeRequest, t, batchDecisions],
  );

  useEffect(() => {
    if (queue.length === 0) return;

    const checkExpired = () => {
      const now = Date.now();
      for (const req of queue) {
        if (req.expiresAt * 1000 <= now && !toastFiredRef.current.has(req.requestId)) {
          toastFiredRef.current.add(req.requestId);
          const behavior = req.timeoutBehavior || 'deny';
          const decision: DecisionType = behavior === 'allow' ? 'approve' : 'reject';
          toast.warning(behavior === 'allow' ? t('timeoutAutoApproved') : t('timeoutAutoDenied'));
          handleResolve(req.requestId, decision, {
            feedback: `Auto-${decision === 'approve' ? 'approved' : 'denied'} due to approval timeout`,
          });
        }
      }
    };

    checkExpired();
    const timer = setInterval(checkExpired, 1000);
    return () => clearInterval(timer);
  }, [queue, t, handleResolve]);

  const handleApproveAll = useCallback(async () => {
    setIsLoading(true);
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
      setIsLoading(false);
    }
  }, [queue, clearAll]);

  const handleRejectAll = useCallback(async () => {
    setIsLoading(true);
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
      setIsLoading(false);
    }
  }, [queue, clearAll]);

  if (queue.length === 0) return null;

  const allHandover = queue.every((r) => r.displayMode === 'handover');

  return (
    <Dialog open={queue.length > 0} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-lg max-h-[80vh]" onPointerDownOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {allHandover ? (
              <Hand className="h-5 w-5 text-primary" />
            ) : (
              <ShieldAlert className="h-5 w-5 text-amber-500" />
            )}
            {allHandover
              ? t('handoverDialogTitle')
              : queue.length > 1
                ? t('batchTitle', { count: queue.length })
                : t('title')}
          </DialogTitle>
          <DialogDescription>{allHandover ? t('handoverDialogDescription') : t('description')}</DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[50vh]">
          <div className="space-y-3 pr-3">
            {/* Render batch groups */}
            {batchGroups.map(([batchId, requests]) => (
              <div key={batchId} className="space-y-3 p-4 rounded-lg border-2 border-primary/20 bg-primary/5">
                <div className="flex items-center gap-2 text-sm font-medium text-primary mb-2">
                  <ShieldAlert className="h-4 w-4" />
                  {t('batchGroup', { count: requests.length })}
                </div>
                {requests.map((req) => (
                  <SingleApprovalCard
                    key={req.requestId}
                    request={req}
                    onResolve={handleResolve}
                    isLoading={isLoading}
                  />
                ))}
              </div>
            ))}
            {/* Render single requests */}
            {singleRequests.map((req) => (
              <SingleApprovalCard key={req.requestId} request={req} onResolve={handleResolve} isLoading={isLoading} />
            ))}
          </div>
        </ScrollArea>

        {queue.length > 1 && (
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={handleRejectAll} disabled={isLoading}>
              <MessageSquareX className="mr-1 h-4 w-4" />
              {t('rejectAll')}
            </Button>
            <Button onClick={handleApproveAll} disabled={isLoading}>
              <CheckCircle2 className="mr-1 h-4 w-4" />
              {t('approveAll')}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
