'use client';

/**
 * Mobile Command Center - real-time task monitoring, approval, and control.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Square, Activity, Send, MessageCircleQuestion } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';

import { scheduleMobilePairRefresh } from '@/lib/mobileRemote';
import { useE2EEStatus } from '@/lib/e2ee/useE2EEStatus';
import E2EESecurityPanel from '@/components/features/e2ee/E2EESecurityPanel';
import SpeechInputButton from '@/components/features/message-input-actions/SpeechInputButton';
import { Button } from '@/components/primitives/button';
import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import { useToolApprovalResolve } from '@/hooks/approval/useToolApprovalResolve';
import { useVisualApprovalSnapshot } from '@/hooks/approval/useVisualApprovalSnapshot';
import useBrowserInspectorStore, {
  selectScopedBrowserViewData,
} from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore, {
  selectScopedDesktopViewData,
} from '@/store/useDesktopInspectorStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { useGoalPlanSync } from '@/components/features/chat-window/goals/useGoalPlanSync';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { MobileStatusApprovalsSection } from './MobileStatusApprovalsSection';
import { MobileStatusMessageBody } from './MobileStatusMessageBody';
import RunStatusChip from '@/components/features/copilot/RunStatusChip';
import SessionAdvisorPanel from '@/components/features/copilot/SessionAdvisorPanel';

export default function MobileStatusBoard({ chatId }: { chatId: string }) {
  const router = useRouter();
  const t = useTranslations('agent.mobileCommand');
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
  const desktopViewData = useDesktopInspectorStore((state) =>
    selectScopedDesktopViewData(state.viewData, chatId),
  );
  const browserViewData = useBrowserInspectorStore((state) =>
    selectScopedBrowserViewData(state.viewData, chatId),
  );
  const desktopLoading = useDesktopInspectorStore((state) => state.isSnapshotLoading);
  const browserLoading = useBrowserInspectorStore((state) => state.isSnapshotLoading);
  const { resolveRequest, approveAll, rejectAll, isLoading: isApprovalLoading } = useToolApprovalResolve();
  const [quickInput, setQuickInput] = useState('');
  const [previewCollapsed, setPreviewCollapsed] = useState(false);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const [previewTab, setPreviewTab] = useState<'browser' | 'desktop'>('browser');
  const [advisorOpen, setAdvisorOpen] = useState(false);
  const [advisorQuestion, setAdvisorQuestion] = useState('');
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

  const autoStartFired = useRef(false);

  useEffect(() => {
    void useChatStore.getState().loadMessages(chatId);
  }, [chatId]);

  useEffect(() => scheduleMobilePairRefresh(), []);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ question?: string }>).detail;
      setAdvisorQuestion(detail?.question ?? '');
      setAdvisorOpen(true);
    };
    window.addEventListener('copilot-open-advisor', handler);
    return () => window.removeEventListener('copilot-open-advisor', handler);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const host = window.location.hostname;
    if (host !== 'localhost' && host !== '127.0.0.1') return;
    window.__MYRM_E2E_MOBILE_CC__ = {
      setLoading: (loading: boolean) => {
        useChatStore.setState({ loading });
      },
    };
    return () => {
      delete window.__MYRM_E2E_MOBILE_CC__;
    };
  }, []);

  useEffect(() => {
    if (!isMessagesLoaded || loading || autoStartFired.current) return;
    const pendingMessage = sessionStorage.getItem('myrm_mobile_autostart_message');
    if (!pendingMessage) return;
    autoStartFired.current = true;
    sessionStorage.removeItem('myrm_mobile_autostart_message');
    sendMessage(pendingMessage);
  }, [isMessagesLoaded, loading, sendMessage]);

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
    const askMatch = text.match(/^\/(?:ask|side)\s*(.*)$/i);
    if (askMatch) {
      setAdvisorQuestion(askMatch[1]?.trim() ?? '');
      setAdvisorOpen(true);
      setQuickInput('');
      return;
    }
    if (loading) steerMessage(text);
    else sendMessage(text);
    setQuickInput('');
  }, [quickInput, sendMessage, steerMessage, loading]);

  const handleOpenFullConversation = useCallback(() => {
    router.push(`/${chatId}`);
  }, [router, chatId]);

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
  const pendingCount = chatApprovalQueue.length;

  return (
    <div className="flex flex-col h-[100dvh] bg-background/50 backdrop-blur-3xl">
      <div className="flex items-center p-4 border-b bg-background/80 sticky top-0 z-50">
        <Button variant="ghost" size="icon" onClick={() => router.back()} className="shrink-0">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="ml-3 flex min-w-0 flex-col">
          <h1 className="text-base font-semibold leading-tight">{t('title')}</h1>
          <span className="text-xs text-muted-foreground">{loading ? t('running') : t('finished')}</span>
          {loading ? (
            <Button
              type="button"
              variant="link"
              className="h-auto justify-start p-0 text-xs font-normal text-primary"
              data-testid="mobile-command-view-full-conversation"
              onClick={handleOpenFullConversation}
            >
              {t('viewFull')} &rarr;
            </Button>
          ) : null}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 gap-1 px-2 text-xs"
            onClick={() => setAdvisorOpen(true)}
          >
            <MessageCircleQuestion className="h-3.5 w-3.5" />
            {t('advisorOpen')}
          </Button>
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

      <RunStatusChip chatId={chatId} />

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <MobileStatusApprovalsSection
          pendingCount={pendingCount}
          inlineRequests={inlineRequests}
          modalRequests={modalRequests}
          desktopViewData={desktopViewData}
          browserViewData={browserViewData}
          desktopLoading={desktopLoading}
          browserLoading={browserLoading}
          snapshotFetchFailed={snapshotFetchFailed}
          snapshotRetrying={snapshotRetrying}
          onRetrySnapshot={retrySnapshot}
          onResolve={resolveRequest}
          onApproveAll={approveAll}
          onRejectAll={rejectAll}
          isApprovalLoading={isApprovalLoading}
        />

        <MobileStatusMessageBody
          chatId={chatId}
          lastAssistantMessage={lastAssistantMessage}
          plan={plan}
          activeGoal={activeGoal}
          loading={loading}
          browserViewData={browserViewData}
          desktopViewData={desktopViewData}
          browserLoading={browserLoading}
          desktopLoading={desktopLoading}
          previewTab={previewTab}
          onPreviewTabChange={setPreviewTab}
          previewCollapsed={previewCollapsed}
          onTogglePreviewCollapsed={() => setPreviewCollapsed((v) => !v)}
          lightboxSrc={lightboxSrc}
          onLightboxOpen={setLightboxSrc}
          onLightboxClose={() => setLightboxSrc(null)}
        />
      </div>

      <div className="border-t bg-background/80 backdrop-blur-md pb-safe">
        <div className="p-3 flex items-center gap-2">
          <SpeechInputButton
            mode="push-to-talk"
            onTranscript={(text) => {
              const trimmed = text.trim();
              if (!trimmed) return;
              if (loading) steerMessage(trimmed);
              else sendMessage(trimmed);
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

      <SessionAdvisorPanel
        chatId={chatId}
        open={advisorOpen}
        onOpenChange={(open) => {
          setAdvisorOpen(open);
          if (!open) {
            setAdvisorQuestion('');
          }
        }}
        initialQuestion={advisorQuestion}
      />
    </div>
  );
}
