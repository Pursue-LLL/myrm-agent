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
 *   - Browser/Desktop Live Preview (collapsible screenshot card + Lightbox)
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
import {
  ArrowLeft, Square, Activity, BrainCircuit, ShieldCheck, ShieldX, Send, Check, X,
  Globe, Monitor, ChevronDown, Maximize2,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';

import { scheduleMobilePairRefresh } from '@/lib/mobileRemote';
import { useE2EEStatus } from '@/lib/e2ee/useE2EEStatus';
import E2EESecurityPanel from '@/components/features/e2ee/E2EESecurityPanel';
import SpeechInputButton from '@/components/features/message-input-actions/SpeechInputButton';
import { Button } from '@/components/primitives/button';
import ProgressSteps from '@/components/features/message-box/progress-steps/ProgressSteps';
import VisualApprovalRequestRenderer from '@/components/features/chat-window/approval/VisualApprovalRequestRenderer';
import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import { useToolApprovalResolve } from '@/hooks/useToolApprovalResolve';
import { useVisualApprovalSnapshot } from '@/hooks/useVisualApprovalSnapshot';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { GoalPlanStepsList } from '@/components/features/chat-window/goals/GoalPlanStepsList';
import { useGoalPlanSync } from '@/components/features/chat-window/goals/useGoalPlanSync';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';

export default function MobileStatusBoard({ chatId }: { chatId: string }) {
  const router = useRouter();
  const t = useTranslations('agent.mobileCommand');
  const tToolApproval = useTranslations('toolApproval');
  const tAgent = useTranslations('agent');

  const { messages, loading, stopMessage, isMessagesLoaded, sendMessage, steerMessage } = useChatStore(
    useShallow((state) => ({
      messages: state.messages,
      loading: state.loading,
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
  const { resolveRequest, approveAll, rejectAll, isLoading: isApprovalLoading } = useToolApprovalResolve();
  const [quickInput, setQuickInput] = useState('');
  const [previewCollapsed, setPreviewCollapsed] = useState(false);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const [previewTab, setPreviewTab] = useState<'browser' | 'desktop'>('browser');
  const e2ee = useE2EEStatus();
  const { plan } = usePlanStore();
  const activeGoal = useGoalStore((s) => s.activeGoal);

  useGoalPlanSync(chatId);

  const chatApprovalQueue = useMemo(
    () => approvalQueue.filter((request) => request.chatId === chatId),
    [approvalQueue, chatId],
  );

  const { inlineRequests, modalRequests } = useMemo(
    () => partitionApprovalQueue(chatApprovalQueue),
    [chatApprovalQueue],
  );

  const { status, snapshotFetchFailed, retrySnapshot } = useVisualApprovalSnapshot(inlineRequests);
  const snapshotRetrying = status === 'loading';

  useEffect(() => {
    void useChatStore.getState().loadMessages(chatId);
  }, [chatId]);

  useEffect(() => {
    return scheduleMobilePairRefresh();
  }, []);

  useEffect(() => {
    if (!lightboxSrc) return;
    document.body.style.overflow = 'hidden';
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightboxSrc(null);
    };
    window.addEventListener('keydown', handler);
    return () => {
      document.body.style.overflow = '';
      window.removeEventListener('keydown', handler);
    };
  }, [lightboxSrc]);

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
          <E2EESecurityPanel {...e2ee} />
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
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => void rejectAll(modalRequests)}
                    disabled={isApprovalLoading}
                  >
                    <ShieldX className="mr-1 h-3.5 w-3.5" />
                    {tToolApproval('rejectAll')}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => void approveAll(modalRequests)}
                    disabled={isApprovalLoading}
                  >
                    {t('approveAll')}
                  </Button>
                </div>
              )}
            </div>
            <div className="divide-y space-y-3 p-3">
              {inlineRequests.map((request) => (
                <VisualApprovalRequestRenderer
                  key={request.requestId}
                  request={request}
                  desktopViewData={desktopViewData}
                  browserViewData={browserViewData}
                  desktopLoading={desktopLoading}
                  browserLoading={browserLoading}
                  snapshotFetchFailed={snapshotFetchFailed}
                  snapshotRetrying={snapshotRetrying}
                  onRetrySnapshot={retrySnapshot}
                  onResolve={resolveRequest}
                  isLoading={isApprovalLoading}
                />
              ))}

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
            {plan && plan.steps.length > 0 && (
              <div className="bg-card rounded-2xl border overflow-hidden">
                <GoalPlanStepsList goal={plan.goal} steps={plan.steps} compact />
              </div>
            )}

            {(browserViewData || desktopViewData) && (() => {
              const hasBoth = Boolean(browserViewData) && Boolean(desktopViewData);
              const activeTab = hasBoth ? previewTab : (browserViewData ? 'browser' : 'desktop');
              const activeData = activeTab === 'browser' ? browserViewData : desktopViewData;
              const isLoading = activeTab === 'browser' ? browserLoading : desktopLoading;
              const elapsed = activeData?.updatedAt ? Math.round((Date.now() - activeData.updatedAt) / 1000) : null;
              const timeLabel = elapsed !== null
                ? elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m`
                : '';
              return (
                <div className="bg-card rounded-2xl border overflow-hidden">
                  <button
                    type="button"
                    className="w-full p-3 border-b bg-muted/20 flex items-center gap-2"
                    onClick={() => setPreviewCollapsed((v) => !v)}
                  >
                    {activeTab === 'browser'
                      ? <Globe className="h-4 w-4 text-blue-500" />
                      : <Monitor className="h-4 w-4 text-green-500" />}
                    <h2 className="text-sm font-medium flex-1 text-left">{t('livePreview')}</h2>
                    {timeLabel && (
                      <span className="text-[10px] text-muted-foreground tabular-nums">{timeLabel}</span>
                    )}
                    <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${previewCollapsed ? '-rotate-90' : ''}`} />
                  </button>
                  {!previewCollapsed && (
                    <div className="p-2 space-y-2">
                      {hasBoth && (
                        <div className="flex gap-1">
                          <button
                            type="button"
                            className={`flex-1 text-xs py-1 rounded-lg transition-colors ${previewTab === 'browser' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground'}`}
                            onClick={() => setPreviewTab('browser')}
                          >
                            <Globe className="inline h-3 w-3 mr-1" />{t('browser')}
                          </button>
                          <button
                            type="button"
                            className={`flex-1 text-xs py-1 rounded-lg transition-colors ${previewTab === 'desktop' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground'}`}
                            onClick={() => setPreviewTab('desktop')}
                          >
                            <Monitor className="inline h-3 w-3 mr-1" />{t('desktop')}
                          </button>
                        </div>
                      )}
                      {isLoading && !activeData && (
                        <div className="h-32 rounded-xl bg-muted/30 animate-pulse" />
                      )}
                      {activeData?.screenshotBase64 && (
                        <button
                          type="button"
                          className="relative w-full rounded-xl overflow-hidden bg-muted/30 group"
                          onClick={() => setLightboxSrc(`data:${activeData.mimeType};base64,${activeData.screenshotBase64}`)}
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={`data:${activeData.mimeType};base64,${activeData.screenshotBase64}`}
                            alt={t('livePreview')}
                            className="w-full h-auto max-h-48 object-contain"
                            draggable={false}
                          />
                          <div className="absolute top-2 right-2 p-1 rounded-md bg-black/40 text-white opacity-0 group-hover:opacity-100 transition-opacity">
                            <Maximize2 className="h-3.5 w-3.5" />
                          </div>
                        </button>
                      )}
                      {(() => {
                        const label = activeTab === 'browser'
                          ? (activeData as typeof browserViewData)?.pageUrl
                          : (activeData as typeof desktopViewData)?.windowTitle || (activeData as typeof desktopViewData)?.appName;
                        return label ? <p className="text-[10px] text-muted-foreground truncate px-1">{label}</p> : null;
                      })()}
                    </div>
                  )}
                </div>
              );
            })()}

            {lightboxSrc && (
              <div
                className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center p-4"
                onClick={() => setLightboxSrc(null)}
                role="dialog"
                aria-modal="true"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={lightboxSrc}
                  alt={t('livePreview')}
                  className="max-w-full max-h-full object-contain rounded-lg"
                  draggable={false}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            )}

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

            {activeGoal?.acceptanceResults && activeGoal.acceptanceResults.length > 0 && (
              <div className="bg-card rounded-2xl border overflow-hidden">
                <div className="p-3 border-b bg-muted/20 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-primary" />
                    <h2 className="text-sm font-medium">{t('verifications')}</h2>
                  </div>
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      activeGoal.acceptanceResults.every((r) => r.passed)
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                        : 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                    }`}
                  >
                    {activeGoal.acceptanceResults.filter((r) => r.passed).length}/{activeGoal.acceptanceResults.length}
                  </span>
                </div>
                <div className="p-2 space-y-1">
                  {activeGoal.acceptanceResults.map((result, idx) => (
                    <div
                      key={idx}
                      className={`flex items-center gap-2 p-2 rounded-xl text-xs ${
                        result.passed
                          ? 'bg-green-50/50 dark:bg-green-900/10'
                          : 'bg-red-50/50 dark:bg-red-900/10'
                      }`}
                    >
                      <span className={`flex-shrink-0 ${result.passed ? 'text-green-600' : 'text-red-600'}`}>
                        {result.passed ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
                      </span>
                      <span className="flex-1 truncate text-foreground/80">{result.label}</span>
                      <span className="text-muted-foreground tabular-nums text-[10px]">{result.duration_ms}ms</span>
                    </div>
                  ))}
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
          <SpeechInputButton
            mode="push-to-talk"
            onTranscript={(text) => {
              const trimmed = text.trim();
              if (!trimmed) return;
              if (loading) {
                steerMessage(trimmed);
              } else {
                sendMessage(trimmed);
              }
            }}
          />
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
