'use client';

/**
 * Mobile Command Center - real-time task monitoring, approval, and control.
 *
 * [INPUT]
 * - @/store/useChatStore: Messages, loading state, stop action
 * - @/store/useToolApprovalStore: Pending approval queue
 * - chatId: Active chat identifier
 *
 * [OUTPUT]
 * - MobileStatusBoard: Full-screen mobile command center with:
 *   - Real-time execution progress (Watch Mode)
 *   - Pending approval queue with one-tap approve/reject
 *   - Quick command input for sending new instructions
 *   - Stop task control
 *
 * [POS]
 * Renders as the primary mobile interface for monitoring and controlling
 * desktop Agent execution. Designed for Codex-like "approve/watch/stop"
 * interaction pattern that works for non-technical users.
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Square, Activity, BrainCircuit, ShieldCheck, ShieldX, Send } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';

import { Button } from '@/components/primitives/button';
import ProgressSteps from '@/components/features/message-box/progress-steps/ProgressSteps';
import useChatStore from '@/store/useChatStore';
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
  const [quickInput, setQuickInput] = useState('');

  useEffect(() => {
    initializeChat(chatId);
  }, [chatId, initializeChat]);

  const resolveApproval = useCallback(
    (requestId: string, decision: 'approve' | 'reject') => {
      const req = approvalQueue.find((r) => r.requestId === requestId);
      if (!req) return;

      const resumeValue = {
        decisions: [{ type: decision, extensions: { allowAlways: false } }],
      };

      sendMessage('', req.messageId, undefined, resumeValue);
      useToolApprovalStore.getState().removeRequest(requestId);
    },
    [approvalQueue, sendMessage],
  );

  const handleApprove = useCallback((requestId: string) => resolveApproval(requestId, 'approve'), [resolveApproval]);

  const handleReject = useCallback((requestId: string) => resolveApproval(requestId, 'reject'), [resolveApproval]);

  const handleApproveAll = useCallback(() => {
    // Group by messageId — batch approvals share the same messageId
    const grouped = new Map<string, typeof approvalQueue>();
    for (const req of approvalQueue) {
      const existing = grouped.get(req.messageId) ?? [];
      existing.push(req);
      grouped.set(req.messageId, existing);
    }

    for (const [messageId, reqs] of grouped) {
      const resumeValue = {
        decisions: reqs.map(() => ({ type: 'approve' as const, extensions: { allowAlways: false } })),
      };
      sendMessage('', messageId, undefined, resumeValue);
      for (const req of reqs) {
        useToolApprovalStore.getState().removeRequest(req.requestId);
      }
    }
  }, [approvalQueue, sendMessage]);

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
  const pendingCount = approvalQueue.length;

  return (
    <div className="flex flex-col h-[100dvh] bg-background/50 backdrop-blur-3xl">
      {/* Header */}
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

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Pending Approvals */}
        {pendingCount > 0 && (
          <div className="bg-card rounded-2xl border border-amber-500/30 overflow-hidden">
            <div className="p-3 border-b bg-amber-500/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-amber-500" />
                <h2 className="text-sm font-medium">
                  {t('pendingApprovals')} ({pendingCount})
                </h2>
              </div>
              {pendingCount > 1 && (
                <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleApproveAll}>
                  {t('approveAll')}
                </Button>
              )}
            </div>
            <div className="divide-y">
              {approvalQueue.map((req) => (
                <div key={req.requestId} className="p-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{req.toolName ?? 'Operation'}</p>
                    {req.reason && <p className="text-xs text-muted-foreground truncate mt-0.5">{req.reason}</p>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button size="sm" className="h-8 px-3 text-xs" onClick={() => handleApprove(req.requestId)}>
                      <ShieldCheck className="mr-1 h-3.5 w-3.5" />
                      {t('approve')}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 px-3 text-xs"
                      onClick={() => handleReject(req.requestId)}
                    >
                      <ShieldX className="mr-1 h-3.5 w-3.5" />
                      {t('reject')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {lastAssistantMessage ? (
          <>
            {/* Progress (Watch Mode view) */}
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

            {/* Thinking */}
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

            {/* Result (when task is done) */}
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

      {/* Footer: Stop + Quick Command */}
      <div className="border-t bg-background/80 backdrop-blur-md pb-safe">
        {/* Quick command input */}
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

        {/* Stop button */}
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
