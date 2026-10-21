'use client';

/**
 * [INPUT]
 * - @/services/wikiService::wikiService (POS: Wiki governance API)
 * - @/components/primitives/* (POS: UI 基础组件)
 * - next-intl::useTranslations (POS: 六语言文案，全部可见文字取自 settings.wiki.*)
 *
 * [OUTPUT]
 * - WikiGovernanceWorkbench: 知识生命周期治理工作台组件（三队列卡片流：待审核、即将过期、待完善、已归档）
 *
 * [POS]
 * Wiki Settings 顶层知识治理工作台，彻底终结信息腐烂，支持一键延期、归档与复活。
 */

import { useCallback, useEffect, useState, useTransition } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldCheck, Clock, Archive, RefreshCw, AlertTriangle, Undo2, Check } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { wikiService } from '@/services/wikiService';

/** The server keeps an archive undoable for 30s; the offer is withdrawn on the same clock. */
const UNDO_WINDOW_MS = 30_000;

interface ExpiringConcept {
  concept_name: string;
  relative_path: string;
  age_days: number;
  modified_at_iso: string;
  is_permanent: boolean;
  hit_count: number;
  reason: string;
}

interface GovernanceOverviewData {
  pending_count: number;
  expiring_count: number;
  gaps_count: number;
  archived_count: number;
  total_active: number;
  expiring_concepts: ExpiringConcept[];
  archived_concepts: ExpiringConcept[];
}

interface GovernanceActionResponse {
  success: boolean;
  undo_token?: string;
}

interface ActionMessage {
  kind: 'success' | 'error';
  text: string;
}

interface WikiGovernanceWorkbenchProps {
  agentId?: string | null;
  onOpenPendingEdits?: () => void;
  onRefreshParent?: () => void;
}

interface QueueCardProps {
  label: string;
  count: number;
  unit: string;
  badge?: string;
  onClick: () => void;
  /** Set for cards that switch the list below; omitted for cards that open something else. */
  pressed?: boolean;
  activeClassName?: string;
}

function QueueCard({ label, count, unit, badge, onClick, pressed, activeClassName }: QueueCardProps) {
  const stateClassName = pressed ? (activeClassName ?? '') : 'border-border/60 bg-muted/30 hover:bg-muted/60';
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      className={`flex min-w-0 flex-col justify-between rounded-lg border p-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${stateClassName}`}
    >
      <span className="flex flex-wrap items-center justify-between gap-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        {badge ? (
          <Badge
            variant="outline"
            className="border-amber-500/30 bg-amber-500/10 text-[10px] text-amber-700 dark:text-amber-300"
          >
            {badge}
          </Badge>
        ) : null}
      </span>
      <span className="mt-1 flex items-baseline gap-1">
        <span className="text-lg font-bold text-foreground">{count}</span>
        <span className="text-xs text-muted-foreground">{unit}</span>
      </span>
    </button>
  );
}

export function WikiGovernanceWorkbench({
  agentId,
  onOpenPendingEdits,
  onRefreshParent,
}: WikiGovernanceWorkbenchProps) {
  const t = useTranslations('settings.wiki');
  const [data, setData] = useState<GovernanceOverviewData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'expiring' | 'archived'>('expiring');
  const [undoToken, setUndoToken] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<ActionMessage | null>(null);
  const [, startTransition] = useTransition();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await wikiService.getGovernanceOverview(agentId, 90);
      setData(res);
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (!undoToken) {
      return;
    }
    const timer = window.setTimeout(() => setUndoToken(null), UNDO_WINDOW_MS);
    return () => window.clearTimeout(timer);
  }, [undoToken]);

  /** Runs one governance call; the user only ever sees our own copy, never the server's message text. */
  const runAction = async (
    action: () => Promise<GovernanceActionResponse>,
    successText: string,
  ): Promise<GovernanceActionResponse | null> => {
    try {
      const res = await action();
      if (!res.success) {
        setActionMessage({ kind: 'error', text: t('actionError') });
        return null;
      }
      setActionMessage({ kind: 'success', text: successText });
      startTransition(() => {
        loadData();
        onRefreshParent?.();
      });
      return res;
    } catch {
      setActionMessage({ kind: 'error', text: t('actionError') });
      return null;
    }
  };

  const handleExtend = (name: string) =>
    runAction(() => wikiService.extendGovernanceConcepts([name], agentId), t('extendSuccess', { name }));

  const handleArchive = async (name: string) => {
    const res = await runAction(
      () => wikiService.archiveGovernanceConcepts([name], 'Manual archive from workbench', agentId),
      t('archiveSuccess', { name }),
    );
    if (res?.undo_token) {
      setUndoToken(res.undo_token);
    }
  };

  const handleUndo = async () => {
    if (!undoToken) {
      return;
    }
    await runAction(() => wikiService.undoGovernanceArchive(undoToken, agentId), t('undoSuccess'));
    // A refused token is spent on the server too, so the offer ends with the attempt either way.
    setUndoToken(null);
  };

  const handleRevive = (name: string) =>
    runAction(() => wikiService.reviveGovernanceConcepts([name], agentId), t('reviveSuccess', { name }));

  if (!data) {
    return null;
  }

  const activeConcepts = activeTab === 'expiring' ? data.expiring_concepts : data.archived_concepts;

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">{t('governanceTitle')}</h3>
        </div>
        <div className="flex items-center gap-2">
          {undoToken ? (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleUndo}
              className="h-7 text-xs gap-1 border border-primary/30"
            >
              <Undo2 className="h-3.5 w-3.5" />
              {t('undoAction')}
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={loadData}
            disabled={loading}
            className="h-7 w-7 p-0"
            aria-label={t('refreshGovernance')}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <QueueCard
          label={t('pendingQueue')}
          count={data.pending_count}
          unit={t('countUnit')}
          onClick={() => onOpenPendingEdits?.()}
        />
        <QueueCard
          label={t('expiringQueue')}
          count={data.expiring_count}
          unit={t('countUnit')}
          badge={data.expiring_count > 0 ? t('needsReview') : undefined}
          onClick={() => setActiveTab('expiring')}
          pressed={activeTab === 'expiring'}
          activeClassName="border-amber-500/50 bg-amber-500/10"
        />
        <div className="flex min-w-0 flex-col justify-between rounded-lg border border-border/60 bg-muted/30 p-2.5">
          <span className="text-xs text-muted-foreground">{t('gapsQueue')}</span>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-lg font-bold text-foreground">{data.gaps_count}</span>
            <span className="text-xs text-muted-foreground">{t('itemUnit')}</span>
          </div>
        </div>
        <QueueCard
          label={t('archivedQueue')}
          count={data.archived_count}
          unit={t('countUnit')}
          onClick={() => setActiveTab('archived')}
          pressed={activeTab === 'archived'}
          activeClassName="border-sky-500/50 bg-sky-500/10"
        />
      </div>

      {actionMessage ? (
        <output className="flex items-center gap-1.5 rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">
          {actionMessage.kind === 'error' ? (
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-destructive" />
          ) : (
            <Check className="h-3.5 w-3.5 shrink-0 text-primary" />
          )}
          {actionMessage.text}
        </output>
      ) : null}

      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-x-2 px-0.5 text-xs text-muted-foreground">
          <span>{activeTab === 'expiring' ? t('expiringListTitle') : t('archivedListTitle')}</span>
          <span>{t('totalItems', { count: activeConcepts.length })}</span>
        </div>

        <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
          {activeConcepts.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border py-6 text-center text-xs text-muted-foreground">
              {activeTab === 'expiring' ? t('emptyExpiring') : t('emptyArchived')}
            </div>
          ) : (
            activeConcepts.map((concept) => (
              <div
                key={concept.concept_name}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/80 bg-background/50 p-2.5 transition-colors"
              >
                <div className="flex min-w-0 items-center gap-2">
                  {activeTab === 'expiring' ? (
                    <Clock className="h-4 w-4 shrink-0 text-amber-500" />
                  ) : (
                    <Archive className="h-4 w-4 shrink-0 text-sky-500" />
                  )}
                  <div className="min-w-0">
                    <div className="truncate text-xs font-medium text-foreground">{concept.concept_name}</div>
                    {activeTab === 'expiring' ? (
                      <div className="text-[11px] text-muted-foreground">
                        {t('daysUnchanged', { days: concept.age_days })}
                      </div>
                    ) : null}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  {activeTab === 'expiring' ? (
                    <>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => handleExtend(concept.concept_name)}
                        className="h-6 px-2 text-[11px]"
                      >
                        {t('extendButton')}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => handleArchive(concept.concept_name)}
                        className="h-6 px-2 text-[11px] text-destructive hover:bg-destructive/10"
                      >
                        {t('archiveButton')}
                      </Button>
                    </>
                  ) : (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleRevive(concept.concept_name)}
                      className="h-6 px-2 text-[11px] text-primary"
                    >
                      {t('reviveButton')}
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
