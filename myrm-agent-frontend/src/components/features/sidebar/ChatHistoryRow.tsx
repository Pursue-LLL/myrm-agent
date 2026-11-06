'use client';

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { AiNetworkIcon } from 'hugeicons-react';
import { GripVertical } from 'lucide-react';
import Link from 'next/link';
import { type DragEvent, memo } from 'react';
import ChannelIcon from '@/components/features/settings/sections/integration/channels/ChannelIcon';
import { useDndItemLabels } from '@/hooks/ui/useDndAccessibility';
import { cn } from '@/lib/utils/classnameUtils';
import type { ChatItem } from '@/services/chat';
import { useProjectStore } from '@/store/useProjectStore';
import { ChatHistoryRowMenu, type ChatHistoryRowMenuProps } from './ChatHistoryRowMenu';

const FastSearchIcon = ({ size, className }: { size?: number; className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size || 16}
    height={size || 16}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22" />
    <path d="M20 5.69899C19.0653 5.76636 17.8681 6.12824 17.0379 7.20277C15.5385 9.14361 14.039 9.30556 13.0394 8.65861C11.5399 7.6882 12.8 6.11636 11.0401 5.26215C9.89313 4.70542 9.73321 3.19045 10.3716 2" />
    <path d="M2 11C2.7625 11.6621 3.83046 12.2682 5.08874 12.2682C7.68843 12.2682 8.20837 12.7649 8.20837 14.7518C8.20837 16.7387 8.20837 16.7387 8.72831 18.2288C9.06651 19.1981 9.18472 20.1674 8.5106 21" />
    <path d="M19.8988 19.9288L22 22M21.1083 17.0459C21.1083 19.2805 19.2932 21.0919 17.0541 21.0919C14.8151 21.0919 13 19.2805 13 17.0459C13 14.8114 14.8151 13 17.0541 13C19.2932 13 21.1083 14.8114 21.1083 17.0459Z" />
  </svg>
);

export interface ChatHistoryRowProps extends ChatHistoryRowMenuProps {
  pinIndex?: number;
  isActive: boolean;
  isGenerating?: boolean;
  sessionStatus?: 'generating' | 'awaiting_approval';
  renameId: string | null;
  renameValue: string;
  batchMode?: boolean;
  isSelected?: boolean;
  onToggleSelect?: (id: string) => void;
  formatTime: (d: Date) => string;
  onItemClick?: () => void;
  onRenameSubmit: (id: string) => void;
  onRenameCancel: () => void;
  onRenameValueChange: (v: string) => void;
  sessionDragEnabled?: boolean;
  onSessionDragStart?: (chat: ChatItem, event: DragEvent<HTMLElement>) => void;
}

export const ChatHistoryRow = memo<ChatHistoryRowProps>(
  ({
    chat,
    pinIndex,
    isMobile,
    isActive,
    isGenerating,
    sessionStatus,
    renameId,
    renameValue,
    exportingId,
    batchMode,
    isSelected,
    onToggleSelect,
    formatTime,
    onItemClick,
    onRename,
    onRenameSubmit,
    onRenameCancel,
    onRenameValueChange,
    onDelete,
    onExport,
    onOpenInIDE,
    onShare,
    onPin,
    onUnpin,
    onCreateAutomation,
    onHandoff,
    onFork,
    onOpenInNewWindow,
    onRevealArtifacts,
    isRevealingArtifacts,
    onCaptureEvalCase,
    sessionDragEnabled = false,
    onSessionDragStart,
    t,
  }) => (
    <div className="relative flex items-start">
      {batchMode && (
        <button
          onClick={(e) => {
            e.preventDefault();
            onToggleSelect?.(chat.id);
          }}
          className="flex-shrink-0 mt-2.5 ml-0.5 mr-0.5 p-0.5"
        >
          <div
            className={cn(
              'w-4 h-4 rounded border-2 transition-colors flex items-center justify-center',
              isSelected ? 'bg-primary border-primary' : 'border-black/25 dark:border-white/25 hover:border-primary/60',
            )}
          >
            {isSelected && (
              <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                <path
                  d="M2.5 6L5 8.5L9.5 3.5"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </div>
        </button>
      )}
      <div className="flex-1 min-w-0">
        <Link
          href={batchMode ? '#' : `/${chat.id}`}
          draggable={sessionDragEnabled && !batchMode && renameId !== chat.id}
          onDragStart={(event) => {
            if (!sessionDragEnabled || batchMode || renameId === chat.id) {
              return;
            }
            onSessionDragStart?.(chat, event);
          }}
          onClick={(e) => {
            if (batchMode) {
              e.preventDefault();
              onToggleSelect?.(chat.id);
              return;
            }
            onItemClick?.();
          }}
          className={cn(
            'group flex items-start gap-3 px-2 py-2 lg:py-2 rounded-lg transition-colors hover:bg-black/5 dark:hover:bg-white/5',
            'min-h-[44px]',
            isActive && !batchMode && 'brand-selected-surface',
            batchMode && isSelected && 'bg-primary/8 dark:bg-primary/12',
            chat.projectId && 'border-l-2',
            sessionDragEnabled && !batchMode && 'cursor-grab active:cursor-grabbing',
          )}
          title={sessionDragEnabled && !batchMode ? t('chat.dragDrop.sessionDescription') : undefined}
          style={chat.projectId ? { borderLeftColor: getProjectColor(chat.projectId) } : undefined}
        >
          {chat.source && chat.source !== 'web' ? (
            <ChannelIcon channelId={chat.source} size={isMobile ? 14 : 16} className="mt-0.5 flex-shrink-0" />
          ) : chat.actionMode === 'agent' ? (
            <AiNetworkIcon
              size={isMobile ? 14 : 16}
              className="mt-0.5 text-black/40 dark:text-white/40 flex-shrink-0"
            />
          ) : (
            <FastSearchIcon
              size={isMobile ? 14 : 16}
              className="mt-0.5 text-black/40 dark:text-white/40 flex-shrink-0"
            />
          )}
          <div className="flex-1 min-w-0">
            {renameId === chat.id ? (
              <input
                type="text"
                value={renameValue}
                onChange={(e) => onRenameValueChange(e.target.value)}
                onBlur={() => onRenameSubmit(chat.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    onRenameSubmit(chat.id);
                  } else if (e.key === 'Escape') {
                    onRenameCancel();
                  }
                }}
                className={cn(
                  'text-sm font-medium text-black/90 dark:text-white/90 bg-transparent border-b border-primary/50 outline-none w-full',
                  isMobile && 'text-xs',
                )}
                // oxlint-disable-next-line jsx-a11y/no-autofocus -- focus follows the user action that revealed this field
                autoFocus
                onClick={(e) => e.preventDefault()}
              />
            ) : (
              <div className="flex items-center gap-1.5">
                <p
                  className={cn('text-sm font-medium text-black/90 dark:text-white/90 truncate', isMobile && 'text-xs')}
                >
                  {chat.title}
                </p>
                {(isGenerating || sessionStatus === 'awaiting_approval') && (
                  <span className="relative flex-shrink-0 w-2 h-2">
                    {sessionStatus === 'awaiting_approval' ? (
                      <>
                        <span className="absolute inset-0 rounded-full bg-amber-500 animate-pulse opacity-60" />
                        <span className="relative block w-2 h-2 rounded-full bg-amber-500" />
                      </>
                    ) : (
                      <>
                        <span className="absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-50" />
                        <span className="relative block w-2 h-2 rounded-full bg-emerald-500" />
                      </>
                    )}
                  </span>
                )}
                {pinIndex != null && (
                  <kbd className="flex-shrink-0 inline-flex items-center justify-center w-4 h-4 rounded text-[9px] font-mono font-semibold bg-primary/15 text-primary/80 dark:text-primary/90 ring-1 ring-primary/20">
                    {pinIndex}
                  </kbd>
                )}
              </div>
            )}
            <p
              className={cn('text-xs text-black/60 dark:text-white/60 truncate mt-1', isMobile && 'text-[10px] mt-0.5')}
            >
              {chat.lastMessage}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <p className={cn('text-xs text-black/40 dark:text-white/40', isMobile && 'text-[10px] mt-0.5')}>
                {formatTime(chat.updatedAt)}
              </p>
              {chat.isCompacted && (
                <div className="flex items-center gap-0.5 text-[10px] px-1 py-[1px] rounded bg-primary/10 text-accent-warm font-medium">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
                    <path d="m12 12 4 4 4-4" />
                    <path d="M16 16V9" />
                  </svg>
                  <span className="scale-90 origin-left whitespace-nowrap">{t('chat.compact.badge')}</span>
                </div>
              )}
            </div>
          </div>
          {!batchMode && (
            <ChatHistoryRowMenu
              chat={chat}
              isMobile={isMobile}
              exportingId={exportingId}
              isRevealingArtifacts={isRevealingArtifacts}
              onRename={onRename}
              onDelete={onDelete}
              onExport={onExport}
              onOpenInIDE={onOpenInIDE}
              onShare={onShare}
              onPin={onPin}
              onUnpin={onUnpin}
              onCreateAutomation={onCreateAutomation}
              onHandoff={onHandoff}
              onFork={onFork}
              onOpenInNewWindow={onOpenInNewWindow}
              onRevealArtifacts={onRevealArtifacts}
              onCaptureEvalCase={onCaptureEvalCase}
              t={t}
            />
          )}
        </Link>
      </div>
    </div>
  ),
);
ChatHistoryRow.displayName = 'ChatHistoryRow';

export const SortablePinnedRow = memo<ChatHistoryRowProps>(({ chat, ...rest }) => {
  const { roleDescription } = useDndItemLabels();
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: chat.id,
    attributes: { roleDescription },
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} className="flex items-start gap-0.5">
      <button
        type="button"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        className={cn(
          'mt-2 flex-shrink-0 rounded text-black/30 hover:text-black/50 dark:text-white/30 dark:hover:text-white/50',
          'cursor-grab active:cursor-grabbing touch-none',
          rest.isMobile ? 'flex min-h-[44px] min-w-[44px] items-center justify-center p-2' : 'p-1',
        )}
        aria-label={rest.t('chat.pin.reorderHandle')}
        onClick={(event) => event.preventDefault()}
      >
        <GripVertical size={rest.isMobile ? 14 : 12} aria-hidden />
      </button>
      <div className="min-w-0 flex-1">
        <ChatHistoryRow chat={chat} {...rest} />
      </div>
    </div>
  );
});
SortablePinnedRow.displayName = 'SortablePinnedRow';

function getProjectColor(projectId: string | null | undefined): string | undefined {
  if (!projectId) {
    return undefined;
  }
  const project = useProjectStore.getState().projects.find((p) => p.id === projectId);
  return project?.color;
}
