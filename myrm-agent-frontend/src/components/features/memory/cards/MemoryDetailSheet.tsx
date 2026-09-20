'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import { AlertTriangle, GitCommitHorizontal, MessageSquare, Quote, ShieldAlert, ShieldCheck, Zap } from 'lucide-react';
import type { Memory } from '@/store/memory';
import MemoryTypeIcon from './MemoryTypeIcon';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/primitives/sheet';

interface MemoryDetailSheetProps {
  memory: Memory | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface MergeHistoryEntry {
  timestamp: string;
  action: string;
  summary: string;
}

const MERGE_ACTION_KEYS: Record<string, string> = {
  MERGE: 'fields.merged',
  REPLACE: 'fields.replaced',
  SUPPLEMENT: 'fields.supplemented',
};

export const parseMergeHistory = (raw?: string): MergeHistoryEntry[] => {
  if (!raw) {
    return [];
  }
  return raw
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const [timestamp = '', action = '', ...summaryParts] = line.split('|');
      return { timestamp, action, summary: summaryParts.join('|') };
    });
};

const EvolutionHistory = memo<{ entries: MergeHistoryEntry[] }>(({ entries }) => {
  const t = useTranslations('memory');
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {t('fields.evolutionHistory')}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
          {t('fields.mergeCount', { count: entries.length })}
        </span>
      </div>
      <div className="relative pl-3.5 space-y-2.5 before:absolute before:left-[5px] before:top-1.5 before:bottom-1 before:w-px before:bg-border">
        {entries.map((entry, idx) => (
          <div key={`${entry.timestamp}-${idx}`} className="relative">
            <span
              className={cn(
                'absolute -left-3.5 top-1.5 h-1.5 w-1.5 rounded-full',
                idx === 0 ? 'bg-primary' : 'bg-muted-foreground/40',
              )}
            />
            <div className="flex flex-wrap items-baseline gap-x-2 min-w-0">
              <span className="text-[10px] text-muted-foreground/70 font-mono shrink-0">{entry.timestamp}</span>
              <span className="text-[10px] px-1.5 py-px rounded bg-accent text-accent-foreground font-medium shrink-0">
                {t(MERGE_ACTION_KEYS[entry.action] ?? 'fields.merged')}
              </span>
              <span className="text-xs text-foreground/90 break-all min-w-0">{entry.summary}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

EvolutionHistory.displayName = 'EvolutionHistory';

const formatDateTime = (dateString?: string) => {
  if (!dateString) {
    return '-';
  }
  return new Date(dateString).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const DetailRow = memo<{ label: string; value: React.ReactNode }>(({ label, value }) => (
  <div className="flex flex-col gap-1">
    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</span>
    <div className="text-sm text-foreground">{value || '-'}</div>
  </div>
));

DetailRow.displayName = 'DetailRow';

const MemoryDetailSheet = memo<MemoryDetailSheetProps>(({ memory, open, onOpenChange }) => {
  const t = useTranslations('memory');
  const router = useRouter();

  if (!memory) {
    return null;
  }

  const memoryType = memory.memory_type;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[440px] overflow-y-auto">
        <SheetHeader className="pb-4 border-b border-border/50">
          <div className="flex items-center gap-3">
            <MemoryTypeIcon type={memoryType} size={24} showBackground showTooltip />
            <div>
              <SheetTitle className="text-lg">{memory.projected_label ?? t(`types.${memoryType}`)}</SheetTitle>
              {memory.influence_explanation && (
                <p className="text-xs text-muted-foreground mt-0.5">{memory.influence_explanation}</p>
              )}
            </div>
          </div>
          {memory.status === 'disabled' && (
            <div className="mt-2 text-xs px-2 py-1 rounded bg-muted text-muted-foreground inline-block">
              {t('disabled')}
            </div>
          )}
        </SheetHeader>

        <div className="space-y-6 py-6">
          {/* Content */}
          <div className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {t('fields.content')}
            </span>
            <div className="text-sm text-foreground bg-accent/30 rounded-lg p-3 leading-relaxed whitespace-pre-wrap">
              {memory.content}
            </div>
          </div>

          {/* Source error (correction) */}
          {memory.source_error && (
            <div className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400 bg-amber-500/10 rounded-lg px-3 py-2">
              <AlertTriangle size={12} className="shrink-0 mt-0.5" />
              <span>
                <span className="font-medium">{t('fields.corrects')}:</span> {memory.source_error}
              </span>
            </div>
          )}

          {/* Profile fields */}
          {memoryType === 'profile' && (
            <div className="grid grid-cols-2 gap-4">
              <DetailRow label={t('fields.key')} value={memory.key} />
              <DetailRow label={t('fields.value')} value={memory.value} />
            </div>
          )}

          {/* Procedural fields */}
          {memoryType === 'procedural' && memory.trigger && (
            <div className="space-y-3">
              <div className="flex items-center gap-1.5 text-xs text-amber-500">
                <Zap size={12} />
                <span className="font-medium uppercase tracking-wide">{t('fields.trigger')}</span>
              </div>
              <div className="text-sm text-foreground bg-accent/30 rounded-lg p-3">
                <span>{memory.trigger}</span>
                {memory.tool_name && (
                  <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px] font-medium align-middle">
                    {memory.tool_name}
                  </span>
                )}
                {memory.tool_rule_priority && memory.tool_rule_priority !== 'normal' && (
                  <span
                    className={cn(
                      'ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium align-middle',
                      memory.tool_rule_priority === 'critical'
                        ? 'bg-destructive/10 text-destructive'
                        : 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
                    )}
                  >
                    {memory.tool_rule_priority.toUpperCase()}
                  </span>
                )}
              </div>
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {t('fields.action')}
              </div>
              <div className="text-sm text-foreground bg-accent/30 rounded-lg p-3">{memory.action}</div>
              {(memory.is_veto || memory.veto_pattern) && (
                <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-destructive">
                    <ShieldAlert size={14} className="shrink-0" />
                    <span>{t('fields.vetoGuardrail')}</span>
                  </div>
                  {memory.veto_pattern && (
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-muted-foreground uppercase tracking-wide text-[10px]">
                        {t('fields.vetoPattern')}:
                      </span>
                      <code className="rounded bg-destructive/10 px-1.5 py-0.5 font-mono text-[11px] text-destructive">
                        {memory.veto_pattern}
                      </code>
                      {memory.veto_scope && (
                        <span className="text-[10px] text-muted-foreground">
                          ({t('fields.scope')}: {memory.veto_scope})
                        </span>
                      )}
                    </div>
                  )}
                  {memory.remediation_advice && (
                    <div className="flex items-start gap-1.5 text-xs text-muted-foreground bg-accent/40 rounded p-2">
                      <ShieldCheck size={12} className="shrink-0 mt-0.5 text-emerald-500" />
                      <span>
                        <span className="font-medium text-foreground">
                          {t('fields.remediation')}:
                        </span>{' '}
                        {memory.remediation_advice}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Metadata grid */}
          <div className={cn('grid gap-4', 'grid-cols-2')}>
            <DetailRow
              label={t('importance')}
              value={
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1.5 bg-accent rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all"
                      style={{ width: `${(memory.importance ?? 0.5) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs tabular-nums">{(memory.importance ?? 0.5).toFixed(1)}</span>
                </div>
              }
            />
            <DetailRow
              label={t('fields.confidence')}
              value={<span className="tabular-nums">{(memory.confidence ?? 1.0).toFixed(2)}</span>}
            />
            <DetailRow label={t('createdAt')} value={formatDateTime(memory.created_at)} />
            <DetailRow label={t('updatedAt')} value={formatDateTime(memory.updated_at)} />
            {memory.last_accessed_at && (
              <DetailRow label={t('lastAccessed')} value={formatDateTime(memory.last_accessed_at)} />
            )}
            {(memory.access_count ?? 0) > 0 && <DetailRow label={t('accessCount')} value={memory.access_count} />}
          </div>

          {/* Tags */}
          {memory.tags && memory.tags.length > 0 && (
            <div className="space-y-2">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {t('fields.tags')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {memory.tags.map((tag) => (
                  <span key={tag} className="px-2 py-0.5 text-xs bg-accent/50 border border-border/50 rounded-full">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Related entities */}
          {memory.related_entities && memory.related_entities.length > 0 && (
            <div className="space-y-2">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {t('fields.relatedEntities')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {memory.related_entities.map((entity) => (
                  <span
                    key={entity}
                    className="px-2 py-0.5 text-xs bg-primary/10 text-primary border border-primary/20 rounded-full"
                  >
                    {entity}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Evidence quote snippet */}
          {Boolean(memory.metadata?.quote_snippet) && (
            <div className="space-y-1.5 p-3 rounded-xl bg-accent/20 border border-border/40 text-xs text-muted-foreground">
              <div className="flex items-center gap-1.5 font-medium text-foreground/80">
                <Quote size={13} className="text-primary shrink-0" />
                <span>{t('sourceEvidence')}</span>
              </div>
              <p className="italic text-foreground/90 pl-4 border-l-2 border-primary/30 py-0.5 whitespace-pre-wrap leading-relaxed">
                「{String(memory.metadata?.quote_snippet)}」
              </p>
            </div>
          )}

          {/* Evolution history (merge audit timeline + correction chain) */}
          {(() => {
            const evolutionEntries = parseMergeHistory(memory.merge_history);
            const hasEvolution = evolutionEntries.length > 0 || Boolean(memory.correction_of);
            return hasEvolution ? (
              <>
                {evolutionEntries.length > 0 && <EvolutionHistory entries={evolutionEntries} />}
                {memory.correction_of && (
                  <div className="flex items-start gap-1.5 text-xs bg-primary/5 border border-primary/20 rounded-lg px-3 py-2 text-muted-foreground">
                    <GitCommitHorizontal size={12} className="shrink-0 mt-0.5 text-primary" />
                    <span>
                      <span className="font-medium text-foreground/80">{t('fields.corrects')}</span>{' '}
                      <span className="font-mono">{memory.correction_of.slice(0, 8)}</span>
                    </span>
                  </div>
                )}
              </>
            ) : null;
          })()}

          {/* Source chat link */}
          {memory.source_chat_id && (
            <div className="pt-4 border-t border-border/50">
              <button
                onClick={() => {
                  const url = memory.source_message_id
                    ? `/${memory.source_chat_id}?highlight=${memory.source_message_id}`
                    : `/${memory.source_chat_id}`;
                  router.push(url);
                  onOpenChange(false);
                }}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg w-full',
                  'text-sm font-medium text-primary',
                  'bg-primary/5 hover:bg-primary/10 border border-primary/20',
                  'transition-colors',
                )}
              >
                <MessageSquare size={14} />
                {t('viewSourceChat')}
              </button>
            </div>
          )}

          {/* Technical info */}
          <div className="pt-4 border-t border-border/50 space-y-1">
            <span className="text-[10px] text-muted-foreground/50 font-mono break-all block">
              {t('fields.id')}: {memory.id}
            </span>
            {memory.projected_category && (
              <span className="text-[10px] text-muted-foreground/50 font-mono block">
                category: {memory.projected_category}
              </span>
            )}
            <span className="text-[10px] text-muted-foreground/50 font-mono block">status: {memory.status}</span>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
});

MemoryDetailSheet.displayName = 'MemoryDetailSheet';

export default MemoryDetailSheet;
