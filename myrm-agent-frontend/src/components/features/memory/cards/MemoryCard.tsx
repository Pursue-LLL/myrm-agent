'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import {
  Check,
  X,
  Trash2,
  Pencil,
  MoreHorizontal,
  AlertTriangle,
  EyeOff,
  Eye,
  MessageSquarePlus,
  MessageSquare,
  BookOpen,
  Clock,
  Lock,
  ShieldAlert,
  Tag,
} from 'lucide-react';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';
import { cn } from '@/lib/utils/classnameUtils';
import type { PendingMemory, Memory, MemoryType } from '@/store/memory';
import MemoryTypeIcon from './MemoryTypeIcon';
import { EvidenceBadge } from './EvidenceBadge';
import { MemoryCardBadges } from './MemoryCardBadges';
import { MemoryProceduralDetails } from './MemoryProceduralDetails';
import PendingTargetHint from './PendingTargetHint';

interface MemoryCardProps {
  memory: PendingMemory | Memory;
  variant?: 'pending' | 'confirmed';
  selected?: boolean;
  onSelect?: () => void;
  onApprove?: (editedContent?: string) => void;
  onReject?: () => void;
  onEdit?: () => void;
  onDelete?: (permanent?: boolean) => void;
  onToggleDisable?: () => void;
  onChatFromMemory?: () => void;
  /** Procedural rules only: protect the rule from agent edits/deletes, or release it. */
  onToggleProtect?: (nextLocked: boolean) => void;
  onClick?: () => void;
  className?: string;
}

const formatDate = (dateString: string) => {
  const date = new Date(dateString);
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const isMemory = (m: PendingMemory | Memory): m is Memory => 'updated_at' in m;

const MemoryCard = memo<MemoryCardProps>(
  ({
    memory,
    variant = 'pending',
    selected = false,
    onSelect,
    onApprove,
    onReject,
    onEdit,
    onDelete,
    onToggleDisable,
    onChatFromMemory,
    onToggleProtect,
    onClick,
    className,
  }) => {
    const t = useTranslations('memory');
    const router = useRouter();
    const [showActions, setShowActions] = useState(false);

    const isPending = variant === 'pending';
    const memoryType = memory.memory_type as MemoryType;
    const confirmed = isMemory(memory) ? memory : null;
    const canEdit =
      confirmed && (memoryType === 'semantic' || memoryType === 'episodic' || memoryType === 'procedural');
    const isDisabled = confirmed?.status === 'disabled';

    const displayLabel = confirmed?.projected_label ?? t(`types.${memoryType}`);

    const displayContent = (() => {
      if (memoryType !== 'profile') {
        return memory.content;
      }
      if (confirmed?.value) {
        return confirmed.value;
      }
      if ('extra_data' in memory && memory.extra_data) {
        const val = memory.extra_data.value;
        if (typeof val === 'string') {
          return val;
        }
      }
      const colonIdx = memory.content.indexOf(': ');
      return colonIdx > 0 ? memory.content.slice(colonIdx + 2) : memory.content;
    })();

    return (
      // oxlint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- keyboard path is the content button below; the card-level click is a pointer convenience
      <div
        data-testid="memory-card"
        className={cn(
          'group relative rounded-xl border transition-all duration-200',
          'bg-card hover:bg-accent/30',
          selected ? 'border-primary ring-2 ring-primary/20' : 'border-border/50 hover:border-border',
          'hover:shadow-md hover:shadow-primary/5',
          isDisabled && 'opacity-50',
          onClick && 'cursor-pointer',
          className,
        )}
        onClick={(e) => {
          if (!onClick) {
            return;
          }
          const target = e.target as HTMLElement;
          if (target.closest('button, [role="button"], input, a, [data-prevent-card-click]')) {
            return;
          }
          onClick();
        }}
        onMouseLeave={() => setShowActions(false)}
      >
        {isPending && onSelect && (
          <div
            className={cn(
              'absolute -left-2 -top-2 z-10 transition-all duration-200',
              selected
                ? 'opacity-100 scale-100'
                : cn(
                    REVEAL_ON_HOVER,
                    'scale-75 group-hover:scale-100 group-focus-within:scale-100 pointer-coarse:scale-100',
                  ),
            )}
          >
            <button
              type="button"
              aria-label={t('selectMemory')}
              aria-pressed={selected}
              onClick={onSelect}
              className={cn(
                'h-6 w-6 rounded-full border-2 flex items-center justify-center transition-all',
                'bg-background',
                selected
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-muted-foreground/30 hover:border-primary',
              )}
            >
              {selected && <Check size={12} strokeWidth={3} />}
            </button>
          </div>
        )}

        <div className="p-4">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex items-center gap-2.5 flex-wrap">
              <MemoryTypeIcon type={memoryType} size={18} showBackground showTooltip />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{displayLabel}</span>
              <MemoryCardBadges memory={memory} confirmed={confirmed} isPending={isPending} />
            </div>

            <div className="flex items-center gap-1">
              <span className="text-xs text-muted-foreground/70">{formatDate(memory.created_at)}</span>
              {!isPending && (
                <div className="relative">
                  <button
                    onClick={() => setShowActions(!showActions)}
                    className={cn('p-1 rounded-full transition-colors', 'hover:bg-accent', showActions && 'bg-accent')}
                  >
                    <MoreHorizontal size={14} className="text-muted-foreground" />
                  </button>
                  {showActions && (
                    <div className="absolute right-0 top-full mt-1 z-20 bg-popover border border-border rounded-lg shadow-lg py-1 min-w-[160px]">
                      {onToggleDisable && (
                        <button
                          onClick={() => {
                            setShowActions(false);
                            onToggleDisable();
                          }}
                          className="w-full px-3 py-1.5 text-sm text-left hover:bg-accent flex items-center gap-2"
                        >
                          {isDisabled ? <Eye size={14} /> : <EyeOff size={14} />}
                          {isDisabled ? t('enable') : t('disable')}
                        </button>
                      )}
                      {onChatFromMemory && (
                        <button
                          onClick={() => {
                            setShowActions(false);
                            onChatFromMemory();
                          }}
                          className="w-full px-3 py-1.5 text-sm text-left hover:bg-accent flex items-center gap-2"
                        >
                          <MessageSquarePlus size={14} />
                          {t('chatFromMemory')}
                        </button>
                      )}
                      {memoryType === 'procedural' && onToggleProtect && (
                        <button
                          onClick={() => {
                            setShowActions(false);
                            onToggleProtect(!confirmed?.is_user_locked);
                          }}
                          className="w-full px-3 py-1.5 text-sm text-left hover:bg-accent flex items-center gap-2"
                        >
                          <Lock size={14} className={confirmed?.is_user_locked ? 'text-amber-500' : undefined} />
                          {confirmed?.is_user_locked ? t('releaseProtection') : t('protectRule')}
                        </button>
                      )}
                      {canEdit && onEdit && (
                        <button
                          onClick={() => {
                            setShowActions(false);
                            onEdit();
                          }}
                          className="w-full px-3 py-1.5 text-sm text-left hover:bg-accent flex items-center gap-2"
                        >
                          <Pencil size={14} />
                          {t('edit')}
                        </button>
                      )}
                      {onDelete && (
                        <>
                          <button
                            onClick={() => {
                              setShowActions(false);
                              onDelete(false);
                            }}
                            className="w-full px-3 py-1.5 text-sm text-left hover:bg-accent flex items-center gap-2 text-muted-foreground hover:text-foreground"
                          >
                            <Trash2 size={14} />
                            {t('delete')}
                          </button>
                          {canEdit && (
                            <button
                              onClick={() => {
                                setShowActions(false);
                                onDelete(true);
                              }}
                              className="w-full px-3 py-1.5 text-sm text-left hover:bg-destructive/10 flex items-center gap-2 text-destructive font-medium"
                            >
                              <ShieldAlert size={14} />
                              {t('trash.permanentDelete')}
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {'influence_explanation' in memory && memory.influence_explanation && (
            <p className="text-[11px] text-muted-foreground/60 mb-2 italic">{memory.influence_explanation}</p>
          )}

          {onClick ? (
            <button
              type="button"
              data-testid="memory-card-content-btn"
              className={cn(
                'text-sm text-foreground leading-relaxed line-clamp-3 text-left',
                'cursor-pointer hover:text-primary/80 transition-colors',
              )}
              onClick={onClick}
            >
              {displayContent}
            </button>
          ) : (
            <p className="text-sm text-foreground leading-relaxed line-clamp-3">{displayContent}</p>
          )}

          {isPending && 'resolution_action' in memory && <PendingTargetHint memory={memory} className="mt-2.5" clamp />}

          {confirmed?.source_error && (
            <div className="mt-2 flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400 bg-amber-500/10 rounded-lg px-2.5 py-1.5">
              <AlertTriangle size={12} className="shrink-0 mt-0.5" />
              <span>
                <span className="font-medium">{t('fields.corrects')}:</span> {confirmed.source_error}
              </span>
            </div>
          )}

          {confirmed && <MemoryProceduralDetails confirmed={confirmed} />}

          {confirmed && confirmed.access_count !== undefined && (
            <div className="mt-3 pt-3 border-t border-border/50 flex items-center justify-between text-[11px] text-muted-foreground">
              <div className="flex items-center gap-1">
                <BookOpen size={12} className="opacity-70" />
                <span>{t('usedTimes', { count: confirmed.access_count })}</span>
              </div>
              {confirmed.last_accessed_at && (
                <div className="flex items-center gap-1 opacity-70">
                  <Clock size={12} />
                  <span>{t('lastUsedAt', { time: formatDate(confirmed.last_accessed_at) })}</span>
                </div>
              )}
            </div>
          )}

          {(() => {
            const tags = confirmed?.tags ?? ('tags' in memory && Array.isArray(memory.tags) ? memory.tags : []);
            if (!tags || tags.length === 0) {
              return null;
            }
            return (
              <div className="mt-2.5 flex items-center gap-1.5 flex-wrap">
                <Tag size={11} className="text-muted-foreground/60 shrink-0" />
                {tags.slice(0, 5).map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-accent/60 text-[10px] font-medium text-muted-foreground"
                  >
                    {tag}
                  </span>
                ))}
                {tags.length > 5 && <span className="text-[10px] text-muted-foreground/50">+{tags.length - 5}</span>}
              </div>
            );
          })()}

          {memory.source_chat_id && (
            <div className="mt-3 pt-3 border-t border-border/50 flex items-center justify-between gap-2 flex-wrap">
              <EvidenceBadge
                sourceId={memory.source_chat_id}
                messageId={memory.source_message_id}
                channelId={'source_channel_id' in memory ? memory.source_channel_id : undefined}
                quoteSnippet={'quote_snippet' in memory ? memory.quote_snippet : undefined}
                authorName={'author_name' in memory ? memory.author_name : undefined}
                authorId={'author_id' in memory ? memory.author_id : undefined}
                isUserLocked={confirmed?.is_user_locked}
                t={t}
              />
              <button
                onClick={() => {
                  const url = memory.source_message_id
                    ? `/${memory.source_chat_id}?highlight=${memory.source_message_id}`
                    : `/${memory.source_chat_id}`;
                  router.push(url);
                }}
                className="flex items-center gap-1.5 text-xs text-primary/70 hover:text-primary transition-colors ml-auto"
              >
                <MessageSquare size={12} />
                <span>{t('viewSourceChat')}</span>
              </button>
            </div>
          )}

          {isPending && (onApprove || onReject) && (
            <div className="flex items-center gap-2 mt-4 pt-3 border-t border-border/50">
              {onReject && (
                <button
                  onClick={onReject}
                  className={cn(
                    'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg',
                    'text-sm font-medium transition-all duration-200',
                    'border border-border/50 hover:border-destructive/50',
                    'text-muted-foreground hover:text-destructive',
                    'hover:bg-destructive/5',
                  )}
                >
                  <X size={14} />
                  {t('reject')}
                </button>
              )}
              {onApprove && (
                <button
                  onClick={() => onApprove()}
                  className={cn(
                    'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg',
                    'text-sm font-medium transition-all duration-200',
                    'bg-primary/10 hover:bg-primary/20',
                    'text-primary border border-primary/20 hover:border-primary/40',
                  )}
                >
                  <Check size={14} />
                  {t('accept')}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  },
);

MemoryCard.displayName = 'MemoryCard';

export default MemoryCard;
