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
  Zap,
  AlertTriangle,
  EyeOff,
  Eye,
  MessageSquarePlus,
  MessageSquare,
  BookOpen,
  Clock,
  Lock,
} from 'lucide-react';
import { Tag } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { PendingMemory, Memory, MemoryType } from '@/store/memory';
import MemoryTypeIcon from './MemoryTypeIcon';

interface MemoryCardProps {
  memory: PendingMemory | Memory;
  variant?: 'pending' | 'confirmed';
  selected?: boolean;
  onSelect?: () => void;
  onApprove?: (editedContent?: string) => void;
  onReject?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  onToggleDisable?: () => void;
  onChatFromMemory?: () => void;
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
    onClick,
    className,
  }) => {
    const t = useTranslations('memory');
    const router = useRouter();
    const [isHovered, setIsHovered] = useState(false);
    const [showActions, setShowActions] = useState(false);

    const isPending = variant === 'pending';
    const memoryType = memory.memory_type as MemoryType;
    const confirmed = isMemory(memory) ? memory : null;
    const canEdit = confirmed && (memoryType === 'semantic' || memoryType === 'episodic');
    const isDisabled = confirmed?.status === 'disabled';

    const displayLabel = confirmed?.projected_label ?? t(`types.${memoryType}`);

    const displayContent = (() => {
      if (memoryType !== 'profile') return memory.content;
      if (confirmed?.value) return confirmed.value;
      if ('extra_data' in memory && memory.extra_data) {
        const val = memory.extra_data.value;
        if (typeof val === 'string') return val;
      }
      const colonIdx = memory.content.indexOf(': ');
      return colonIdx > 0 ? memory.content.slice(colonIdx + 2) : memory.content;
    })();

    return (
      <div
        className={cn(
          'group relative rounded-xl border transition-all duration-200',
          'bg-card hover:bg-accent/30',
          selected ? 'border-primary ring-2 ring-primary/20' : 'border-border/50 hover:border-border',
          'hover:shadow-md hover:shadow-primary/5',
          isDisabled && 'opacity-50',
          className,
        )}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => {
          setIsHovered(false);
          setShowActions(false);
        }}
      >
        {isPending && onSelect && (
          <div
            className={cn(
              'absolute -left-2 -top-2 z-10 transition-all duration-200',
              isHovered || selected ? 'opacity-100 scale-100' : 'opacity-0 scale-75',
            )}
          >
            <button
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
            <div className="flex items-center gap-2.5">
              <MemoryTypeIcon type={memoryType} size={18} showBackground showTooltip />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{displayLabel}</span>
              {isDisabled && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                  {t('disabled')}
                </span>
              )}
              {confirmed?.is_user_locked && (
                <Lock size={12} className="text-amber-500" title={t('locked')} />
              )}
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
                        <button
                          onClick={() => {
                            setShowActions(false);
                            onDelete();
                          }}
                          className="w-full px-3 py-1.5 text-sm text-left hover:bg-accent flex items-center gap-2 text-destructive"
                        >
                          <Trash2 size={14} />
                          {t('delete')}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {confirmed?.influence_explanation && (
            <p className="text-[11px] text-muted-foreground/60 mb-2 italic">{confirmed.influence_explanation}</p>
          )}

          <p
            className={cn(
              'text-sm text-foreground leading-relaxed line-clamp-3',
              onClick && 'cursor-pointer hover:text-primary/80 transition-colors',
            )}
            onClick={onClick}
          >
            {displayContent}
          </p>

          {confirmed?.source_error && (
            <div className="mt-2 flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400 bg-amber-500/10 rounded-lg px-2.5 py-1.5">
              <AlertTriangle size={12} className="shrink-0 mt-0.5" />
              <span>
                <span className="font-medium">{t('fields.corrects')}:</span> {confirmed.source_error}
              </span>
            </div>
          )}

          {confirmed && memoryType === 'procedural' && confirmed.trigger && (
            <div className="mt-2 space-y-1 text-xs text-muted-foreground">
              <div className="flex items-center gap-1.5 flex-wrap">
                <Zap size={12} className="text-amber-500" />
                <span>
                  {t('fields.trigger')}: {confirmed.trigger}
                </span>
                {confirmed.tool_name && (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px] font-medium">
                    {confirmed.tool_name}
                  </span>
                )}
                {confirmed.tool_rule_priority && confirmed.tool_rule_priority !== 'normal' && (
                  <span
                    className={cn(
                      'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium',
                      confirmed.tool_rule_priority === 'critical'
                        ? 'bg-destructive/10 text-destructive'
                        : 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
                    )}
                  >
                    {confirmed.tool_rule_priority.toUpperCase()}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 pl-[18px]">
                <span>
                  {t('fields.action')}: {confirmed.action}
                </span>
              </div>
              {confirmed.reasoning && (
                <div className="flex items-center gap-1.5 pl-[18px] text-muted-foreground/80 mt-0.5">
                  <span className="italic">
                    <span className="font-medium mr-1">Why:</span> {confirmed.reasoning}
                  </span>
                </div>
              )}
              {confirmed.application && (
                <div className="flex items-center gap-1.5 pl-[18px] text-muted-foreground/80 mt-0.5">
                  <span className="italic">
                    <span className="font-medium mr-1">How:</span> {confirmed.application}
                  </span>
                </div>
              )}
            </div>
          )}

          {confirmed && (confirmed.access_count !== undefined) && (
            <div className="mt-3 pt-3 border-t border-border/50 flex items-center justify-between text-[11px] text-muted-foreground">
              <div className="flex items-center gap-1">
                <BookOpen size={12} className="opacity-70" />
                <span>
                  Used <span className="font-medium text-foreground">{confirmed.access_count}</span> times
                </span>
              </div>
              {confirmed.last_accessed_at && (
                <div className="flex items-center gap-1 opacity-70">
                  <Clock size={12} />
                  <span>Last: {formatDate(confirmed.last_accessed_at)}</span>
                </div>
              )}
            </div>
          )}

          {confirmed?.tags && confirmed.tags.length > 0 && (
            <div className="mt-2.5 flex items-center gap-1.5 flex-wrap">
              <Tag size={11} className="text-muted-foreground/60 shrink-0" />
              {confirmed.tags.slice(0, 5).map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-accent/60 text-[10px] font-medium text-muted-foreground"
                >
                  {tag}
                </span>
              ))}
              {confirmed.tags.length > 5 && (
                <span className="text-[10px] text-muted-foreground/50">+{confirmed.tags.length - 5}</span>
              )}
            </div>
          )}

          {memory.source_chat_id && (
            <div className="mt-3 pt-3 border-t border-border/50">
              <button
                onClick={() => {
                  const url = memory.source_message_id
                    ? `/${memory.source_chat_id}?highlight=${memory.source_message_id}`
                    : `/${memory.source_chat_id}`;
                  router.push(url);
                }}
                className="flex items-center gap-1.5 text-xs text-primary/70 hover:text-primary transition-colors"
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
