/**
 * FiveContractDeliveryStatusPanel — Visualizes the 5-contract engineering delivery lifecycle.
 *
 * Phases:
 * 1. Task Intent (任务意图与范围)
 * 2. Scene Environment (现场沙箱与权限)
 * 3. Action Execution (动作调用与执行)
 * 4. Delivery Artifact (交付物与变更产出)
 * 5. Acceptance Verification (验收测试与事实核验)
 *
 * I: chatId, className
 * O: Collapsible, responsive status card with progress indicators, status badges, and contract audit records
 */

'use client';

import React, { useEffect, useState, useTransition } from 'react';
import { useTranslations } from 'next-intl';
import {
  CheckCircle2,
  Clock,
  AlertTriangle,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Workflow,
  Sparkles,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import {
  getChatDeliveryContracts,
  type FiveContractSnapshotResponse,
  type PhaseContractRecord,
} from '@/services/chat';

interface FiveContractDeliveryStatusPanelProps {
  chatId: string;
  className?: string;
}

const PHASE_KEYS = [
  'task_intent',
  'scene_environment',
  'action_execution',
  'delivery_artifact',
  'acceptance_verification',
] as const;

export function FiveContractDeliveryStatusPanel({
  chatId,
  className = '',
}: FiveContractDeliveryStatusPanelProps) {
  const t = useTranslations('chat.deliveryContracts');
  const [snapshot, setSnapshot] = useState<FiveContractSnapshotResponse | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isPending, startTransition] = useTransition();

  const fetchContracts = React.useCallback(async () => {
    try {
      const data = await getChatDeliveryContracts(chatId);
      setSnapshot(data);
    } catch {
      // Non-intrusive fallback for empty or brand new chat
    }
  }, [chatId]);

  useEffect(() => {
    fetchContracts();
  }, [fetchContracts]);

  if (!snapshot || !snapshot.contracts) {
    return null;
  }

  const getStatusIcon = (status: PhaseContractRecord['status']) => {
    switch (status) {
      case 'satisfied':
        return <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />;
      case 'violated':
        return <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0" />;
      case 'in_progress':
        return <Clock className="w-4 h-4 text-sky-500 animate-spin shrink-0" />;
      default:
        return <Clock className="w-4 h-4 text-muted-foreground shrink-0" />;
    }
  };

  const getStatusBadge = (status: PhaseContractRecord['status']) => {
    switch (status) {
      case 'satisfied':
        return (
          <Badge variant="outline" className="text-[10px] bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800">
            {t('status.satisfied')}
          </Badge>
        );
      case 'violated':
        return (
          <Badge variant="outline" className="text-[10px] bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-400 dark:border-rose-800">
            {t('status.violated')}
          </Badge>
        );
      case 'in_progress':
        return (
          <Badge variant="outline" className="text-[10px] bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-400 dark:border-sky-800">
            {t('status.inProgress')}
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="text-[10px] text-muted-foreground border-border">
            {t('status.pending')}
          </Badge>
        );
    }
  };

  return (
    <div
      className={`border rounded-xl bg-card/60 backdrop-blur-sm shadow-xs transition-all duration-200 overflow-hidden ${className}`}
    >
      {/* Header Bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-muted/20 border-b">
        <div className="flex items-center gap-2">
          <Workflow className="w-4 h-4 text-primary shrink-0" />
          <span className="text-xs font-semibold tracking-wide text-foreground">
            {t('title')}
          </span>
          <span className="text-[11px] font-mono text-muted-foreground">
            {snapshot.overall_progress_pct}%
          </span>
          {snapshot.is_fully_satisfied && (
            <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
              <ShieldCheck className="w-3 h-3 mr-1 inline" />
              {t('allSatisfied')}
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-foreground"
            onClick={() => startTransition(() => fetchContracts())}
            disabled={isPending}
            title={t('refresh')}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isPending ? 'animate-spin' : ''}`} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-foreground"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </Button>
        </div>
      </div>

      {/* 5-Step Compact Progress Strip */}
      <div className="grid grid-cols-5 gap-1 p-2 bg-background/50">
        {PHASE_KEYS.map((key, idx) => {
          const record = snapshot.contracts[key];
          const isSatisfied = record?.status === 'satisfied';
          const isViolated = record?.status === 'violated';
          const isInProgress = record?.status === 'in_progress';

          return (
            <div
              key={key}
              className={`flex flex-col gap-1 p-1.5 rounded-md border text-center transition-colors ${
                isSatisfied
                  ? 'border-emerald-500/30 bg-emerald-500/5'
                  : isViolated
                  ? 'border-rose-500/30 bg-rose-500/5'
                  : isInProgress
                  ? 'border-sky-500/30 bg-sky-500/5'
                  : 'border-transparent bg-muted/10'
              }`}
            >
              <div className="flex items-center justify-between text-[10px] font-medium text-muted-foreground">
                <span>0{idx + 1}</span>
                {getStatusIcon(record?.status || 'pending')}
              </div>
              <span className="text-[11px] font-medium truncate text-foreground">
                {t(`phases.${key}`)}
              </span>
              <div className="w-full bg-secondary h-1 rounded-full overflow-hidden mt-0.5">
                <div
                  className={`h-full transition-all duration-300 ${
                    isSatisfied
                      ? 'bg-emerald-500'
                      : isViolated
                      ? 'bg-rose-500'
                      : 'bg-primary'
                  }`}
                  style={{ width: `${record?.progress_pct || 0}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Expanded Details List */}
      {isExpanded && (
        <div className="border-t p-3 space-y-2.5 bg-background/80">
          {PHASE_KEYS.map((key, idx) => {
            const record = snapshot.contracts[key];
            if (!record) return null;

            return (
              <div
                key={key}
                className="flex items-start justify-between p-2 rounded-lg border bg-card/40 hover:bg-card/80 transition-colors gap-3"
              >
                <div className="flex items-start gap-2.5 min-w-0 flex-1">
                  <div className="mt-0.5">{getStatusIcon(record.status)}</div>
                  <div className="flex flex-col min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-foreground">
                        {idx + 1}. {t(`phases.${key}`)}
                      </span>
                      {getStatusBadge(record.status)}
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
                      {record.summary || t('noSummary')}
                    </p>
                    {record.evidence && record.evidence.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {record.evidence.map((ev, evIdx) => (
                          <span
                            key={evIdx}
                            className="inline-flex items-center text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                          >
                            <Sparkles className="w-2.5 h-2.5 mr-1 text-primary/70" />
                            {ev}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <span className="text-[11px] font-mono font-medium text-muted-foreground shrink-0 mt-0.5">
                  {record.progress_pct}%
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
