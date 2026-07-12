'use client';

import { Activity, BrainCircuit, ShieldCheck, Check, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/primitives/button';
import ProgressSteps from '@/components/features/message-box/progress-steps/ProgressSteps';
import { GoalPlanStepsList } from '@/components/features/chat-window/goals/GoalPlanStepsList';
import { MobileStatusLivePreview } from './MobileStatusLivePreview';
import type { Message } from '@/store/chat/types';
import type { Plan } from '@/store/chat/goals/usePlanStore';
import type { GoalState } from '@/components/features/chat-window/goals/GoalStatusCard';
import type { InspectorViewSnapshot } from '@/lib/approval/visualApprovalContext';

interface MobileStatusMessageBodyProps {
  chatId: string;
  lastAssistantMessage: Message | undefined;
  plan: Plan | null;
  activeGoal: GoalState | null;
  loading: boolean;
  browserViewData: InspectorViewSnapshot | null;
  desktopViewData: InspectorViewSnapshot | null;
  browserLoading: boolean;
  desktopLoading: boolean;
  previewTab: 'browser' | 'desktop';
  onPreviewTabChange: (tab: 'browser' | 'desktop') => void;
  previewCollapsed: boolean;
  onTogglePreviewCollapsed: () => void;
  lightboxSrc: string | null;
  onLightboxOpen: (src: string) => void;
  onLightboxClose: () => void;
}

export function MobileStatusMessageBody({
  chatId,
  lastAssistantMessage,
  plan,
  activeGoal,
  loading,
  browserViewData,
  desktopViewData,
  browserLoading,
  desktopLoading,
  previewTab,
  onPreviewTabChange,
  previewCollapsed,
  onTogglePreviewCollapsed,
  lightboxSrc,
  onLightboxOpen,
  onLightboxClose,
}: MobileStatusMessageBodyProps) {
  const router = useRouter();
  const t = useTranslations('agent.mobileCommand');

  if (!lastAssistantMessage) {
    return (
      <div className="flex h-[50vh] flex-col items-center justify-center text-muted-foreground gap-4">
        <div className="p-4 rounded-full bg-muted">
          <Activity className="h-8 w-8 opacity-50" />
        </div>
        <p className="text-sm">{t('noStatus')}</p>
      </div>
    );
  }

  const hasProgress =
    lastAssistantMessage.progressSteps && lastAssistantMessage.progressSteps.length > 0;
  const hasThinking =
    lastAssistantMessage.thinkingItems && lastAssistantMessage.thinkingItems.length > 0;

  return (
    <>
      {plan && plan.steps.length > 0 && (
        <div className="bg-card rounded-2xl border overflow-hidden">
          <GoalPlanStepsList goal={plan.goal} steps={plan.steps} compact />
        </div>
      )}

      <MobileStatusLivePreview
        browserViewData={browserViewData}
        desktopViewData={desktopViewData}
        browserLoading={browserLoading}
        desktopLoading={desktopLoading}
        previewTab={previewTab}
        onPreviewTabChange={onPreviewTabChange}
        previewCollapsed={previewCollapsed}
        onToggleCollapsed={onTogglePreviewCollapsed}
        lightboxSrc={lightboxSrc}
        onLightboxOpen={onLightboxOpen}
        onLightboxClose={onLightboxClose}
      />

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
              {activeGoal.acceptanceResults.filter((r) => r.passed).length}/
              {activeGoal.acceptanceResults.length}
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
            <p className="text-sm text-foreground leading-relaxed line-clamp-5">
              {lastAssistantMessage.content}
            </p>
            <Button
              variant="link"
              className="px-0 mt-2 h-auto text-xs"
              onClick={() => router.push(`/${chatId}`)}
            >
              {t('viewFull')} &rarr;
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
