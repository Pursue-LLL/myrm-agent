/**
 * [INPUT] '@/services/agent'::listAgentSnapshots, rollbackAgentProfileToSnapshot
 * [OUTPUT] AgentProfileTimeMachine: Agent 配置快照历史与按版本回滚
 * [POS] AgentEditPanel 底部折叠面板，提供 WebUI 配置时光机能力
 */
'use client';

import React, { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { format } from 'date-fns';
import { WorkHistoryIcon, Clock01Icon } from 'hugeicons-react';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/primitives/collapsible';
import { cn } from '@/lib/utils/classnameUtils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { listAgentSnapshots, rollbackAgentProfileToSnapshot, type AgentProfileSnapshotItem } from '@/services/agent';
import { IconChevronDown } from '@/components/features/icons/PremiumIcons';

interface AgentProfileTimeMachineProps {
  agentId: string;
  snapshotCount: number;
  onRestored: () => void;
}

function snapshotPreview(data: Record<string, unknown>): string {
  const name = typeof data.display_name === 'string' ? data.display_name : '';
  const prompt = typeof data.system_prompt === 'string' ? data.system_prompt : '';
  if (name && prompt) {
    return `${name} · ${prompt.slice(0, 80)}${prompt.length > 80 ? '…' : ''}`;
  }
  return name || prompt.slice(0, 120) || '—';
}

const PREVIEW_FIELDS = [
  'display_name',
  'system_prompt',
  'model',
  'skill_ids',
  'mcp_ids',
  'enabled_builtin_tools',
] as const;

function snapshotFieldPreview(
  data: Record<string, unknown>,
  labelFor: (field: (typeof PREVIEW_FIELDS)[number]) => string,
): string[] {
  return PREVIEW_FIELDS.flatMap((field) => {
    const value = data[field];
    if (value === undefined || value === null || value === '') {
      return [];
    }
    const text = typeof value === 'string' ? value : Array.isArray(value) ? value.join(', ') : JSON.stringify(value);
    return [`${labelFor(field)}: ${text.slice(0, 120)}${text.length > 120 ? '…' : ''}`];
  });
}

export function AgentProfileTimeMachine({
  agentId,
  snapshotCount,
  onRestored,
  expanded,
  onExpandedChange,
}: AgentProfileTimeMachineProps & { expanded?: boolean; onExpandedChange?: (expanded: boolean) => void }) {
  const t = useTranslations('agent.timeMachine');
  const [internalExpanded, setInternalExpanded] = useState(false);

  const isExpanded = expanded !== undefined ? expanded : internalExpanded;

  const handleExpandedChange = (newState: boolean) => {
    if (onExpandedChange) {
      onExpandedChange(newState);
    } else {
      setInternalExpanded(newState);
    }
    if (newState) {
      void fetchHistory();
    }
  };
  const [history, setHistory] = useState<AgentProfileSnapshotItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [pendingRestore, setPendingRestore] = useState<AgentProfileSnapshotItem | null>(null);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listAgentSnapshots(agentId);
      setHistory(data);
    } catch (error) {
      console.error('Agent snapshot history fetch error:', error);
      toast.error(t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [agentId, t]);

  const fieldLabel = useCallback((field: string) => {
    const labels: Record<string, string> = {
      display_name: 'Name',
      system_prompt: 'Prompt',
      model: 'Model',
      skill_ids: 'Skills',
      mcp_ids: 'MCPs',
      enabled_builtin_tools: 'Built-in Tools',
    };
    return labels[field] || field;
  }, []);

  const translateReason = useCallback(
    (reason: string) => {
      if (reason === 'webui-update') return t('reasons.webui-update');
      if (reason === 'pre-rollback') return t('reasons.pre-rollback');
      return reason;
    },
    [t],
  );

  const handleRestore = async (record: AgentProfileSnapshotItem) => {
    setRestoring(record.id);
    try {
      await rollbackAgentProfileToSnapshot(agentId, record.id);
      toast.success(t('restoreSuccess'));
      onRestored();
      await fetchHistory();
    } catch (error) {
      console.error('Agent snapshot rollback error:', error);
      toast.error(t('restoreFailed'));
    } finally {
      setRestoring(null);
      setPendingRestore(null);
    }
  };

  return (
    <>
      <Collapsible open={isExpanded} onOpenChange={handleExpandedChange} className="mt-6">
        <div className="rounded-2xl border border-border/50 bg-card/60 overflow-hidden">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 px-4 sm:px-5 py-4 text-left hover:bg-muted/30 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <WorkHistoryIcon size={18} />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-foreground">{t('title')}</p>
                    {snapshotCount > 0 ? (
                      <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                        {t('count', { count: snapshotCount })}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground line-clamp-2 sm:truncate">{t('description')}</p>
                </div>
              </div>
              <IconChevronDown
                className={cn(
                  'h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200',
                  expanded && 'rotate-180',
                )}
              />
            </button>
          </CollapsibleTrigger>

          <CollapsibleContent>
            <div className="border-t border-border/40 px-4 sm:px-5 py-4 space-y-3">
              <p className="text-xs text-muted-foreground leading-relaxed">{t('hint')}</p>

              <ScrollArea className="h-[min(360px,50vh)] pr-3">
                {loading ? (
                  <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                    {t('loading')}
                  </div>
                ) : history.length === 0 ? (
                  <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                    {t('empty')}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {history.map((record, index) => {
                      const date = new Date(record.created_at);
                      const isMostRecent = index === 0;

                      return (
                        <div
                          key={record.id}
                          className={cn(
                            'rounded-xl border p-4',
                            isMostRecent
                              ? 'border-primary/40 bg-primary/5'
                              : 'border-border/40 bg-secondary/20 dark:bg-secondary/10',
                          )}
                        >
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div className="min-w-0 space-y-1.5">
                              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                                <Clock01Icon size={14} className="text-primary shrink-0" />
                                {format(date, 'yyyy-MM-dd HH:mm:ss')}
                              </div>
                              {record.reason ? (
                                <p className="text-xs text-muted-foreground truncate">
                                  {translateReason(record.reason)}
                                </p>
                              ) : null}
                              <p className="text-xs text-muted-foreground/90 line-clamp-3 font-mono break-all">
                                {snapshotPreview(record.snapshot_data)}
                              </p>
                            </div>

                            <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
                              {isMostRecent ? (
                                <span className="text-[11px] font-medium text-primary px-2.5 py-1 rounded-full bg-primary/10 self-start sm:self-end">
                                  {t('mostRecent')}
                                </span>
                              ) : null}
                              <Button
                                variant={isMostRecent ? 'default' : 'secondary'}
                                size="sm"
                                className="self-stretch sm:self-end"
                                onClick={() => setPendingRestore(record)}
                                disabled={restoring === record.id}
                              >
                                {restoring === record.id ? t('restoring') : t('restore')}
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </ScrollArea>
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>

      <AlertDialog open={pendingRestore !== null} onOpenChange={(open) => !open && setPendingRestore(null)}>
        <AlertDialogContent className="max-w-lg">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3 text-sm text-muted-foreground">
                <p>{t('confirmDescription')}</p>
                {pendingRestore ? (
                  <div className="rounded-lg border border-border/50 bg-muted/30 p-3 font-mono text-xs space-y-1">
                    {snapshotFieldPreview(pendingRestore.snapshot_data, fieldLabel).map((line) => (
                      <p key={line} className="break-all">
                        {line}
                      </p>
                    ))}
                  </div>
                ) : null}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-2">
            <AlertDialogCancel>{t('confirmCancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => pendingRestore && void handleRestore(pendingRestore)}
              disabled={restoring !== null}
            >
              {restoring ? t('restoring') : t('confirmRestore')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
