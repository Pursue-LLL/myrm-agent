'use client';

/**
 * [INPUT]
 * - store/useChatStore::chatId, contextPinnedFiles (+ load error / setters) (POS: Chat state management store.)
 * - services/chat::getContextPins, setContextPins (POS: Chat service — context pin CRUD.)
 * - services/fork-api::forkConversation (POS: Fork API client — dynamic import in the panel.)
 * - services/contextHealth::ContextHealth (POS: Statistics context-health DTO layer.)
 * - ./ContextBreakdown, ./ContextCompressControl, ./TurnGrowthSparkline (POS: Panel sections.)
 * - ./contextUsageFormat::STATUS_DOT_COLORS, formatTokens (POS: Pure display helpers.)
 *
 * [OUTPUT]
 * - ContextStrategyPanel: popover / bottom-sheet body with token breakdown, strategy health, pins, compress and fork actions.
 *
 * [POS]
 * Detail panel opened from the context usage ring. Shows compaction / pruning / cache health, lets the user pin files,
 * compress the context on demand and, from 75% usage, fork the conversation into a new topic.
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import { getContextPins, setContextPins } from '@/services/chat';
import type { ContextHealth } from '@/services/contextHealth';
import type { ContextBudget } from '@/store/chat/types';
import { ContextBreakdown, hasContextBreakdown } from './ContextBreakdown';
import { ContextCompressControl } from './ContextCompressControl';
import TurnGrowthSparkline from './TurnGrowthSparkline';
import type { ContextWatermarkMetrics } from './useContextWatermarkMetrics';
import { STATUS_DOT_COLORS, formatTokens } from './contextUsageFormat';

interface ContextStrategyPanelProps {
  health: ContextHealth | null;
  loading: boolean;
  chatId: string | null;
  usagePercent: number;
  contextBudget: ContextBudget | null;
  watermarkMetrics?: ContextWatermarkMetrics;
  onNavigateDetails: () => void;
  onRefreshHealth: () => void;
}

export function ContextStrategyPanel({
  health,
  loading,
  chatId,
  usagePercent,
  contextBudget,
  watermarkMetrics,
  onNavigateDetails,
  onRefreshHealth,
}: ContextStrategyPanelProps) {
  const t = useTranslations('chat.contextUsage.strategy');
  const contextPinnedFiles = useChatStore((state) => state.contextPinnedFiles);
  const contextPinnedFilesLoadError = useChatStore((state) => state.contextPinnedFilesLoadError);
  const setContextPinnedFiles = useChatStore((state) => state.setContextPinnedFiles);
  const setContextPinnedFilesLoadError = useChatStore((state) => state.setContextPinnedFilesLoadError);
  const [forking, setForking] = useState(false);
  const [pinInput, setPinInput] = useState('');
  const [pinsLoading, setPinsLoading] = useState(false);
  const [pinsSaving, setPinsSaving] = useState(false);

  const loadPins = useCallback(async (): Promise<string[]> => {
    if (!chatId) {
      return [];
    }
    setPinsLoading(true);
    try {
      const { files } = await getContextPins(chatId);
      if (useChatStore.getState().chatId !== chatId) {
        return [];
      }
      setContextPinnedFiles(files);
      setContextPinnedFilesLoadError(null);
      return files;
    } catch {
      if (useChatStore.getState().chatId === chatId) {
        setContextPinnedFilesLoadError('load_failed');
      }
      return [];
    } finally {
      if (useChatStore.getState().chatId === chatId) {
        setPinsLoading(false);
      }
    }
  }, [chatId, setContextPinnedFiles, setContextPinnedFilesLoadError]);

  const handleAddPin = useCallback(async () => {
    const normalized = pinInput.trim();
    if (!chatId || !normalized || pinsSaving) {
      return;
    }
    setPinsSaving(true);
    try {
      const nextFiles = [...contextPinnedFiles.filter((item) => item !== normalized), normalized];
      const { files } = await setContextPins(chatId, nextFiles);
      setContextPinnedFiles(files);
      setPinInput('');
    } catch (err) {
      console.error('[ContextUsagePins] failed to add pin', err);
    } finally {
      setPinsSaving(false);
    }
  }, [chatId, pinInput, contextPinnedFiles, pinsSaving, setContextPinnedFiles]);

  const handleRemovePin = useCallback(
    async (filePath: string) => {
      if (!chatId || pinsSaving) {
        return;
      }
      setPinsSaving(true);
      try {
        const { files } = await setContextPins(
          chatId,
          contextPinnedFiles.filter((item) => item !== filePath),
        );
        setContextPinnedFiles(files);
      } catch (err) {
        console.error('[ContextUsagePins] failed to remove pin', err);
      } finally {
        setPinsSaving(false);
      }
    },
    [chatId, contextPinnedFiles, pinsSaving, setContextPinnedFiles],
  );

  const canFork = !!chatId && usagePercent >= 75 && !forking;

  const handleFork = useCallback(async () => {
    if (!chatId || forking) {
      return;
    }
    setForking(true);
    try {
      const [{ forkConversation }, { default: workspaceStore }, { showI18nToast }] = await Promise.all([
        import('@/services/fork-api'),
        import('@/store/useWorkspaceStore'),
        import('@/services/i18nToastService'),
      ]);
      const response = await forkConversation(chatId, -1);
      if (response.success && response.data.new_chat_id) {
        showI18nToast('chat.fork.success', undefined, { type: 'success' });
        workspaceStore.getState().addPane(response.data.new_chat_id);
      } else {
        showI18nToast('chat.fork.failed', undefined, { type: 'error' });
      }
    } catch (e) {
      console.error('[ContextUsageFork]', e);
      try {
        const { showI18nToast } = await import('@/services/i18nToastService');
        showI18nToast('chat.fork.failed', undefined, { type: 'error' });
      } catch {
        /* toast import failed — already logged above */
      }
    } finally {
      setForking(false);
    }
  }, [chatId, forking]);

  if (loading) {
    return (
      <div data-testid="context-usage-panel" className="flex flex-col gap-2 p-3 min-w-[220px] animate-pulse">
        <div className="h-4 bg-muted rounded w-24" />
        <div className="h-3 bg-muted rounded w-full" />
        <div className="h-3 bg-muted rounded w-3/4" />
      </div>
    );
  }

  const compaction = health?.compaction;
  const pruning = health?.pruning;
  const cache = health?.cache;

  return (
    <div data-testid="context-usage-panel" className="flex flex-col gap-2.5 p-3 min-w-[220px]">
      {contextBudget && hasContextBreakdown(contextBudget) ? (
        <ContextBreakdown budget={contextBudget} className="pb-2 border-b border-border/40" />
      ) : null}
      {watermarkMetrics && watermarkMetrics.historyTurnTokens.length > 0 ? (
        <TurnGrowthSparkline metrics={watermarkMetrics} width={220} height={36} />
      ) : null}
      {health ? (
        <>
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-foreground">{t('title')}</span>
            <span
              className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                health.status === 'critical'
                  ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                  : health.status === 'warning'
                    ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                    : health.status === 'healthy'
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      : 'bg-muted text-muted-foreground'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT_COLORS[health.status]}`} />
              {t(`status.${health.status}`)}
            </span>
          </div>

          <div className="flex flex-col gap-1.5 text-[11px]">
            {compaction?.active && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span>{t('compaction')}</span>
                <span className="tabular-nums text-foreground">
                  {compaction.count > 0
                    ? t('compactionSaved', { count: compaction.count, tokens: formatTokens(compaction.tokens_saved) })
                    : t('compactionIdle')}
                </span>
              </div>
            )}

            {pruning?.active && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span>{t('pruning')}</span>
                <span className="tabular-nums text-foreground">
                  {pruning.archived > 0 ? t('pruningArchived', { count: pruning.archived }) : t('pruningIdle')}
                </span>
              </div>
            )}

            {cache?.active && (
              <div className="flex items-center justify-between text-muted-foreground">
                <span>{t('cache')}</span>
                <span className="tabular-nums text-foreground">
                  {t('cacheHitRate', { rate: (cache.cache_hit_rate * 100).toFixed(0) })}
                </span>
              </div>
            )}

            {!compaction?.active && !pruning?.active && !cache?.active && (
              <span className="text-muted-foreground">{t('allInactive')}</span>
            )}
          </div>

          {(pruning?.archive_restore_blocked_count ?? 0) > 0 && (
            <div className="mt-1 pt-1.5 border-t border-border/50 text-[10px] text-rose-600 dark:text-rose-400">
              {t('restoreBlocked', { count: pruning?.archive_restore_blocked_count ?? 0 })}
            </div>
          )}
        </>
      ) : (
        <span className="text-xs text-muted-foreground">{t('noData')}</span>
      )}

      <div className="mt-1 pt-1.5 border-t border-border/50 flex flex-col gap-1.5">
        <span className="text-[10px] font-medium text-muted-foreground">{t('pinnedFiles')}</span>
        {pinsLoading ? (
          <span className="text-[10px] text-muted-foreground">{t('pinsLoading')}</span>
        ) : contextPinnedFilesLoadError ? (
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-rose-600 dark:text-rose-400">{t('pinsLoadError')}</span>
            <button
              type="button"
              onClick={() => void loadPins()}
              className="text-primary hover:text-primary/80 transition-colors"
            >
              {t('pinsRetry')}
            </button>
          </div>
        ) : contextPinnedFiles.length === 0 ? (
          <span className="text-[10px] text-muted-foreground">{t('pinsEmpty')}</span>
        ) : (
          <ul className="flex flex-col gap-1 max-h-24 overflow-y-auto">
            {contextPinnedFiles.map((filePath) => (
              <li
                key={filePath}
                data-testid="context-pin-item"
                data-pin-path={filePath}
                className="flex items-center gap-1 text-[10px]"
              >
                <span className="flex-1 truncate text-foreground/80" title={filePath}>
                  {filePath}
                </span>
                <button
                  type="button"
                  disabled={pinsSaving}
                  onClick={() => void handleRemovePin(filePath)}
                  className="shrink-0 text-muted-foreground hover:text-rose-500 transition-colors"
                >
                  {t('removePin')}
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex gap-1">
          <input
            type="text"
            value={pinInput}
            onChange={(event) => setPinInput(event.target.value)}
            placeholder={t('pinPlaceholder')}
            className="flex-1 text-[11px] px-2 py-1.5 rounded-md border border-border/60 bg-background"
          />
          <button
            type="button"
            disabled={!chatId || !pinInput.trim() || pinsSaving}
            onClick={() => void handleAddPin()}
            className="text-[11px] px-2 py-1.5 rounded-md border border-border/60 bg-muted hover:bg-muted/80 disabled:opacity-50"
          >
            {t('addPin')}
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground leading-snug">{t('archiveRestoreHint')}</p>
        <ContextCompressControl chatId={chatId} usagePercent={usagePercent} onCompacted={onRefreshHealth} />

        {canFork && (
          <button
            type="button"
            onClick={handleFork}
            disabled={forking}
            className="w-full text-[11px] font-medium py-1.5 px-2 rounded-md transition-colors bg-accent/60 text-accent-foreground hover:bg-accent dark:bg-accent/40 dark:hover:bg-accent/60"
          >
            {forking ? t('forking') : t('forkNewTopic')}
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={onNavigateDetails}
        className="text-[10px] text-primary-dark hover:text-primary-dark/80 dark:text-primary-light dark:hover:text-primary-light/80 text-left transition-colors"
      >
        {t('viewDetails')}
      </button>
    </div>
  );
}
