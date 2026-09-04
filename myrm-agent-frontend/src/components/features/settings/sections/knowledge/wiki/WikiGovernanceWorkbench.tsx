'use client';

/**
 * [INPUT]
 * - @/services/wikiService::wikiService (POS: Wiki governance API)
 * - @/components/primitives/* (POS: UI 基础组件)
 * - next-intl::useTranslations (POS: 双语文案)
 *
 * [OUTPUT]
 * - WikiGovernanceWorkbench: 知识生命周期治理工作台组件（三队列卡片流：待审核、即将过期、待完善、已归档）
 *
 * [POS]
 * Wiki Settings 顶层知识治理工作台，彻底终结信息腐烂，支持一键延期、归档与复活。
 */

import React, { useEffect, useState, useTransition } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldCheck, Clock, Archive, RefreshCw, AlertTriangle, Undo2, Check } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { wikiService } from '@/services/wikiService';

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

interface WikiGovernanceWorkbenchProps {
  agentId?: string | null;
  onOpenPendingEdits?: () => void;
  onRefreshParent?: () => void;
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
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await wikiService.getGovernanceOverview(agentId, 90);
      setData(res);
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [agentId]);

  const handleExtend = async (conceptName: string) => {
    try {
      const res = await wikiService.extendGovernanceConcepts([conceptName], agentId);
      setActionMessage(res.message);
      startTransition(() => {
        loadData();
        onRefreshParent?.();
      });
    } catch {
      setActionMessage('Operation failed');
    }
  };

  const handleArchive = async (conceptName: string) => {
    try {
      const res = await wikiService.archiveGovernanceConcepts([conceptName], 'Manual archive from workbench', agentId);
      if (res.undo_token) {
        setUndoToken(res.undo_token);
      }
      setActionMessage(res.message);
      startTransition(() => {
        loadData();
        onRefreshParent?.();
      });
    } catch {
      setActionMessage('Archive failed');
    }
  };

  const handleUndo = async () => {
    if (!undoToken) return;
    try {
      const res = await wikiService.undoGovernanceArchive(undoToken, agentId);
      setUndoToken(null);
      setActionMessage(res.message);
      startTransition(() => {
        loadData();
        onRefreshParent?.();
      });
    } catch {
      setActionMessage('Undo failed');
    }
  };

  const handleRevive = async (conceptName: string) => {
    try {
      const res = await wikiService.reviveGovernanceConcepts([conceptName], agentId);
      setActionMessage(res.message);
      startTransition(() => {
        loadData();
        onRefreshParent?.();
      });
    } catch {
      setActionMessage('Revive failed');
    }
  };

  if (!data) return null;

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-4 shadow-xs">
      {/* Header with Title & Stats */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            {t('governanceTitle') || '知识生命周期治理工作台'}
          </h3>
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
              {t('undoAction') || '撤销归档'}
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={loadData}
            disabled={loading}
            className="h-7 w-7 p-0"
            aria-label="Refresh governance"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* 4 Summary Badges */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {/* Queue 1: Pending */}
        <div
          role="button"
          tabIndex={0}
          onClick={onOpenPendingEdits}
          onKeyDown={(e) => e.key === 'Enter' && onOpenPendingEdits?.()}
          className="flex cursor-pointer flex-col justify-between rounded-lg border border-border/60 bg-muted/30 p-2.5 transition-colors hover:bg-muted/60"
        >
          <span className="text-xs text-muted-foreground">{t('pendingQueue') || '待审核草稿'}</span>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-lg font-bold text-foreground">{data.pending_count}</span>
            <span className="text-xs text-muted-foreground">篇</span>
          </div>
        </div>

        {/* Queue 2: Expiring */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => setActiveTab('expiring')}
          onKeyDown={(e) => e.key === 'Enter' && setActiveTab('expiring')}
          className={`flex cursor-pointer flex-col justify-between rounded-lg border p-2.5 transition-colors ${
            activeTab === 'expiring'
              ? 'border-amber-500/50 bg-amber-500/10'
              : 'border-border/60 bg-muted/30 hover:bg-muted/60'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">{t('expiringQueue') || '即将过期(>90d)'}</span>
            {data.expiring_count > 0 ? (
              <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600 text-[10px]">
                需复核
              </Badge>
            ) : null}
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-lg font-bold text-foreground">{data.expiring_count}</span>
            <span className="text-xs text-muted-foreground">篇</span>
          </div>
        </div>

        {/* Queue 3: Gaps */}
        <div className="flex flex-col justify-between rounded-lg border border-border/60 bg-muted/30 p-2.5">
          <span className="text-xs text-muted-foreground">{t('gapsQueue') || '知识断层'}</span>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-lg font-bold text-foreground">{data.gaps_count}</span>
            <span className="text-xs text-muted-foreground">项</span>
          </div>
        </div>

        {/* Queue 4: Archived */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => setActiveTab('archived')}
          onKeyDown={(e) => e.key === 'Enter' && setActiveTab('archived')}
          className={`flex cursor-pointer flex-col justify-between rounded-lg border p-2.5 transition-colors ${
            activeTab === 'archived'
              ? 'border-sky-500/50 bg-sky-500/10'
              : 'border-border/60 bg-muted/30 hover:bg-muted/60'
          }`}
        >
          <span className="text-xs text-muted-foreground">{t('archivedQueue') || '已隔离归档'}</span>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-lg font-bold text-foreground">{data.archived_count}</span>
            <span className="text-xs text-muted-foreground">篇</span>
          </div>
        </div>
      </div>

      {actionMessage ? (
        <div className="rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground flex items-center gap-1.5">
          <Check className="h-3.5 w-3.5 text-primary" />
          {actionMessage}
        </div>
      ) : null}

      {/* Concept Action List Container */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-muted-foreground px-0.5">
          <span>{activeTab === 'expiring' ? '待复核老化概念列表' : '已隔离归档概念列表'}</span>
          <span>共 {activeTab === 'expiring' ? data.expiring_concepts.length : data.archived_concepts.length} 项</span>
        </div>

        <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
          {activeTab === 'expiring' ? (
            data.expiring_concepts.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border py-6 text-center text-xs text-muted-foreground">
                暂无老化概念，所有知识均为活跃常青状态
              </div>
            ) : (
              data.expiring_concepts.map((concept) => (
                <div
                  key={concept.concept_name}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/80 bg-background/50 p-2.5 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Clock className="h-4 w-4 shrink-0 text-amber-500" />
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium text-foreground">{concept.concept_name}</div>
                      <div className="text-[11px] text-muted-foreground">已 {concept.age_days} 天未更新</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleExtend(concept.concept_name)}
                      className="h-6 text-[11px] px-2"
                    >
                      延期90天
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => handleArchive(concept.concept_name)}
                      className="h-6 text-[11px] px-2 text-destructive hover:bg-destructive/10"
                    >
                      归档
                    </Button>
                  </div>
                </div>
              ))
            )
          ) : data.archived_concepts.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border py-6 text-center text-xs text-muted-foreground">
              暂无已归档概念
            </div>
          ) : (
            data.archived_concepts.map((concept) => (
              <div
                key={concept.concept_name}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/80 bg-background/50 p-2.5 transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Archive className="h-4 w-4 shrink-0 text-sky-500" />
                  <div className="min-w-0">
                    <div className="truncate text-xs font-medium text-foreground">{concept.concept_name}</div>
                    <div className="text-[11px] text-muted-foreground">物理隔离于 archive/ 目录</div>
                  </div>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleRevive(concept.concept_name)}
                  className="h-6 text-[11px] px-2 text-primary"
                >
                  一键复活
                </Button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
