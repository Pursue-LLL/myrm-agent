'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Plus, Layout, FileDiff, X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { useShallow } from 'zustand/react/shallow';
import useChatStore from '@/store/useChatStore';
import { Button } from '@/components/primitives/button';
import PaneCard from './PaneCard';
import ActiveSessionsBar from './ActiveSessionsBar';
import ReviewPanel from './ReviewPanel';

export default function WorkspaceLayout() {
  const t = useTranslations('multiPane');
  const router = useRouter();
  const { panes, activePaneId, addPane, removePane, setActivePaneId, startPolling, stopPolling, maxConcurrent } =
    useWorkspaceStore(
      useShallow((s) => ({
        panes: s.panes,
        activePaneId: s.activePaneId,
        addPane: s.addPane,
        removePane: s.removePane,
        setActivePaneId: s.setActivePaneId,
        startPolling: s.startPolling,
        stopPolling: s.stopPolling,
        maxConcurrent: s.maxConcurrent,
      })),
    );

  const chatHistory = useChatStore((s) => s.chatHistoryItems);
  const loadChatHistory = useChatStore((s) => s.loadChatHistory);
  const setInputMessage = useChatStore((s) => s.setInputMessage);
  const [reviewOpenMobile, setReviewOpenMobile] = useState(false);

  const handleSendFeedback = useCallback(
    (chatId: string, feedback: string) => {
      setInputMessage(feedback);
      router.push(`/${chatId}`);
    },
    [setInputMessage, router],
  );

  useEffect(() => {
    startPolling();
    loadChatHistory();
    return () => stopPolling();
  }, [startPolling, stopPolling, loadChatHistory]);

  const canAddPane = panes.length < maxConcurrent;
  const activePane = useMemo(() => panes.find((p) => p.id === activePaneId), [panes, activePaneId]);

  return (
    <div className="flex h-full bg-background">
      {/* Left: Pane Grid */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Header Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/50">
          <div className="flex items-center gap-3">
            <Layout size={20} className="text-primary" />
            <h1 className="text-lg font-semibold">{t('title')}</h1>
          </div>
          <div className="flex items-center gap-3">
            <ActiveSessionsBar />
            {panes.length > 0 && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setReviewOpenMobile(true)}
                className="gap-2 rounded-lg lg:hidden"
                aria-label="Open review panel"
              >
                <FileDiff size={16} />
                Review
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => addPane()}
              disabled={!canAddPane}
              className="gap-2 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 border-0 shadow-none animate-none"
            >
              <Plus size={16} />
              {t('addPane')}
            </Button>
          </div>
        </div>

        {/* Pane Grid */}
        <div className="flex-1 p-6 overflow-auto">
          {panes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-4 overflow-visible py-8">
              <Layout size={48} className="opacity-30" />
              <p className="text-sm">{t('noActiveSessions')}</p>
              <Button type="button" onClick={() => addPane()} className="gap-2 rounded-lg">
                <Plus size={16} />
                {t('addPane')}
              </Button>
            </div>
          ) : (
            <div
              className={cn(
                'grid gap-4 grid-cols-1',
                panes.length >= 2 && 'sm:grid-cols-2',
                panes.length >= 3 && 'lg:grid-cols-3',
              )}
            >
              {panes.map((pane) => (
                <PaneCard
                  key={pane.id}
                  pane={pane}
                  isActive={pane.id === activePaneId}
                  chatHistory={chatHistory}
                  onSelect={() => setActivePaneId(pane.id)}
                  onClose={() => removePane(pane.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: Review Panel */}
      {panes.length > 0 && (
        <div className="w-[400px] border-l border-border/50 hidden lg:flex flex-col">
          <ReviewPanel
            sessionId={activePane?.chatId ?? null}
            workspacePath={activePane?.snapshot?.agentConfig?.projectDir ?? null}
            onSendFeedback={handleSendFeedback}
          />
        </div>
      )}

      {/* Mobile: Review Drawer */}
      {reviewOpenMobile && panes.length > 0 && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Review changes">
          <button
            type="button"
            aria-label="Close review"
            className="absolute inset-0 bg-background/80 backdrop-blur-sm cursor-default"
            onClick={() => setReviewOpenMobile(false)}
          />
          <div className="absolute inset-x-0 bottom-0 top-12 rounded-t-2xl border-t border-border bg-background shadow-xl flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/50">
              <span className="text-sm font-semibold">Review changes</span>
              <button
                type="button"
                onClick={() => setReviewOpenMobile(false)}
                aria-label="Close review panel"
                className="p-1.5 rounded-full hover:bg-muted transition-colors text-muted-foreground"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 min-h-0">
              <ReviewPanel
                sessionId={activePane?.chatId ?? null}
                workspacePath={activePane?.snapshot?.agentConfig?.projectDir ?? null}
                onSendFeedback={(chatId, feedback) => {
                  setReviewOpenMobile(false);
                  handleSendFeedback(chatId, feedback);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
