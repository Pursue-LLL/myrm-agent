'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils/classnameUtils';
import { AlertTriangle, Zap, MessageSquare } from 'lucide-react';
import type { Memory } from '@/store/memory';
import MemoryTypeIcon from './MemoryTypeIcon';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/primitives/sheet';

interface MemoryDetailSheetProps {
  memory: Memory | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const formatDateTime = (dateString?: string) => {
  if (!dateString) return '-';
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

  if (!memory) return null;

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
