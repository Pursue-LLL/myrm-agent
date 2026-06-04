'use client';

/**
 * Mobile Command Center - real-time task monitoring, approval, and control.
 *
 * [INPUT]
 * - @/store/useChatStore: Messages, loading state, stop action
 * - @/store/useToolApprovalStore: Pending approval queue
 * - @/hooks/useToolApprovalResolve: Stream resume for approve/reject
 * - @/hooks/useVisualApprovalSnapshot: Snapshot fallback for inline visual approvals
 * - chatId: Active chat identifier
 *
 * [OUTPUT]
 * - MobileStatusBoard: Full-screen mobile command center with:
 *   - Real-time execution progress (Watch Mode)
 *   - Inline visual approvals (BBox screenshot) and modal text approvals
 *   - Quick command input for sending new instructions
 *   - Stop task control
 *
 * [POS]
 * Renders as the primary mobile interface for monitoring and controlling
 * desktop Agent execution. Visual browser/desktop approvals reuse the same
 * inline surface rules as the desktop chat window.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Square, Activity, BrainCircuit, ShieldCheck, Send } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';

import { Button } from '@/components/primitives/button';
import ProgressSteps from '@/components/features/message-box/progress-steps/ProgressSteps';
import VisualApprovalArtifactCard from '@/components/features/chat-window/VisualApprovalArtifactCard';
import VisualApprovalPendingCard from '@/components/features/chat-window/VisualApprovalPendingCard';
import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import {
  hasVisualApprovalContext,
  resolveVisualApprovalContextForRequest,
} from '@/lib/approval/visualApprovalContext';
import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import { useToolApprovalResolve } from '@/hooks/useToolApprovalResolve';
import { useVisualApprovalSnapshot } from '@/hooks/useVisualApprovalSnapshot';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

export default function MobileStatusBoard({ chatId }: { chatId: string }) {
  const router = useRouter();
  const t = useTranslations('agent.mobileCommand');
  const tAgent = useTranslations('agent');

  const { messages, loading, initializeChat, stopMessage, isMessagesLoaded, sendMessage, steerMessage } = useChatStore(
    useShallow((state) => ({
      messages: state.messages,
      loading: state.loading,
      initializeChat: state.initializeChat,
      stopMessage: state.stopMessage,
      isMessagesLoaded: state.isMessagesLoaded,
      sendMessage: state.sendMessage,
      steerMessage: state.steerMessage,
    })),
  );

  const approvalQueue = useToolApprovalStore((s) => s.queue);
  const desktopViewData = useDesktopInspectorStore((state) => state.viewData);
  const browserViewData = useBrowserInspectorStore((state) => state.viewData);
  const desktopLoading = useDesktopInspectorStore((state) => state.isSnapshotLoading);
  const browserLoading = useBrowserInspectorStore((state) => state.isSnapshotLoading);
  const { resolveRequest, approveAll, isLoading: isApprovalLoading } = useToolApprovalResolve();
  const [quickInput, setQuickInput] = useState('');

  const chatApprovalQueue = useMemo(
    () => approvalQueue.filter((request) => request.chatId === chatId),
    [approvalQueue, chatId],
  );

  const { inlineRequests, modalRequests } = useMemo(
    () => partitionApprovalQueue(chatApprovalQueue),
    [chatApprovalQueue],
  );

  useVisualApprovalSnapshot(inlineRequests);

  useEffect(() => {
    initializeChat(chatId);
  }, [chatId, initializeChat]);

  const handleSendQuickCommand = useCallback(() => {
    const text = quickInput.trim();
    if (!text) return;

    if (loading) {
      steerMessage(text);
    } else {
      sendMessage(text);
    }
    setQuickInput('');
  }, [quickInput, sendMessage, steerMessage, loading]);

  if (!isMessagesLoaded) {
    return (
      <div className="flex h-[100dvh] items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Activity className="h-8 w-8 animate-pulse text-primary" />
          <span className="text-sm text-muted-foreground">{tAgent('loading')}</span>
        </div>
      </div>
    );
  }

  const lastAssistantMessage = [...messages].reverse().find((m) => m.role === 'assistant');
  const hasProgress = lastAssistantMessage?.progressSteps && lastAssistantMessage.progressSteps.length > 0;
  const hasThinking = lastAssistantMessage?.thinkingItems && lastAssistantMessage.thinkingItems.length > 0;
  const pendingCount = chatApprovalQueue.length;

  return (
    <div className="flex flex-col h-[100dvh] bg-background/50 backdrop-blur-3xl">
      <div className="flex items-center p-4 border-b bg-background/80 sticky top-0 z-50">
        <Button variant="ghost" size="icon" onClick={() => router.back()} className="shrink-0">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="ml-3 flex flex-col">
          <h1 className="text-base font-semibold leading-tight">{t('title')}</h1>
          <span className="text-xs text-muted-foreground">{loading ? t('running') : t('finished')}</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {pendingCount > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-[10px] font-bold text-destructive-foreground">
              {pendingCount}
            </span>
          )}
          {loading && (
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-primary" />
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {pendingCount > 0 && (
          <div className="bg-card rounded-2xl border border-amber-500/30 overflow-hidden">
            <div className="p-3 border-b bg-amber-500/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-amber-500" />
                <h2 className="text-sm font-medium">
                  {t('pendingApprovals')} ({pendingCount})
                </h2>
              </div>
              {modalRequests.length > 1 && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => void approveAll(modalRequests)}
                  disabled={isApprovalLoading}
                >
                  {t('approveAll')}
                </Button>
              )}
            </div>
            <div className="divide-y space-y-3 p-3">
              {inlineRequests.map((request) => {
                const visualContext = resolveVisualApprovalContextForRequest(
                  request,
                  desktopViewData,
                  browserViewData,
                );

                if (visualContext) {
                  return (
                    <VisualApprovalArtifactCard
                      key={request.requestId}
                      request={request}
                      desktopViewData={desktopViewData}
                      browserViewData={browserViewData}
                      onResolve={resolveRequest}
                      isLoading={isApprovalLoading}
                    />
                  );
                }

                const waitingForSnapshot =
                  (request.toolName.startsWith('desktop_') && desktopLoading) ||
                  (request.toolName.startsWith('browser_') && browserLoading) ||
                  !hasVisualApprovalContext(request, desktopViewData, browserViewData);

                if (waitingForSnapshot) {
                  return <VisualApprovalPendingCard key={request.requestId} request={request} />;
                }

                return null;
              })}

              {modalRequests.map((request) => (
                <SingleApprovalCard
                  key={request.requestId}
                  request={request}
                  onResolve={resolveRequest}
                  isLoading={isApprovalLoading}
                  compact
                  hideVisualHighlight
                />
              ))}
            </div>
          </div>
        )}

        {lastAssistantMessage ? (
          <>
            {hasProgress && (
              <div className="bg-card rounded-2xl border overflow-hidden">
                <div className="p-3 border-b bg-muted/20 flex items-center gap-2">
                  <Activity className="h-4 w-4 text-primary" />
                  <h2 className="text-sm font-medium">{t('progress')}</h2>
                </div>
                <div className="p-2">
                  <ProgressSteps
                    messageId={lastAssistantMessage.messageId}
                    steps={lastAssistantMessage.progressSteps!}
                    loading={loading}
                  />
                </div>
              </div>
            )}

            {hasThinking && (
              <div className="bg-card rounded-2xl border overflow-hidden">
                <div className="p-3 border-b bg-muted/20 flex items-center gap-2">
                  <BrainCircuit className="h-4 w-4 text-purple-500" />
                  <h2 className="text-sm font-medium">{t('thinking')}</h2>
                </div>
                <div className="p-3">
                  <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap line-clamp-6">
                    {lastAssistantMessage.thinkingItems![lastAssistantMessage.thinkingItems!.length - 1]}
                  </p>
                </div>
              </div>
            )}

            {!loading && lastAssistantMessage.content && (
              <div className="bg-card rounded-2xl border overflow-hidden">
                <div className="p-3 border-b bg-muted/20 flex items-center gap-2">
                  <h2 className="text-sm font-medium">{t('result')}</h2>
                </div>
                <div className="p-3">
                  <p className="text-sm text-foreground leading-relaxed line-clamp-5">{lastAssistantMessage.content}</p>
                  <Button variant="link" className="px-0 mt-2 h-auto text-xs" onClick={() => router.push(`/${chatId}`)}>
                    {t('viewFull')} &rarr;
                  </Button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="flex h-[50vh] flex-col items-center justify-center text-muted-foreground gap-4">
            <div className="p-4 rounded-full bg-muted">
              <Activity className="h-8 w-8 opacity-50" />
            </div>
            <p className="text-sm">{t('noStatus')}</p>
          </div>
        )}
      </div>

      <div className="border-t bg-background/80 backdrop-blur-md pb-safe">
        <div className="p-3 flex items-center gap-2">
          <input
            type="text"
            value={quickInput}
            onChange={(e) => setQuickInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendQuickCommand()}
            placeholder={loading ? t('steerPlaceholder') : t('quickCommandPlaceholder')}
            className="flex-1 h-10 rounded-xl border bg-secondary/50 px-3 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
          />
          <Button
            size="icon"
            className="h-10 w-10 rounded-xl shrink-0"
            onClick={handleSendQuickCommand}
            disabled={!quickInput.trim()}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>

        {loading && (
          <div className="px-3 pb-3">
            <Button variant="destructive" className="w-full h-11 text-sm font-medium rounded-xl" onClick={stopMessage}>
              <Square className="mr-2 h-4 w-4 fill-current" />
              {t('stopTask')}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
