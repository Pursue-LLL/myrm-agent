'use client';

import { memo } from 'react';
import Link from 'next/link';
import type { useTranslations } from 'next-intl';
import type { ChatItem } from '@/services/chat';
import { AiNetworkIcon } from 'hugeicons-react';
import ChannelIcon from '@/components/features/settings/sections/ChannelIcon';
import {
  MoreHorizontal,
  Trash2,
  Edit3,
  Download,
  FileText,
  FileJson,
  FileCode2,
  Copy,
  Pin,
  PinOff,
  Timer,
  ArrowRightLeft,
  FolderInput,
  FolderX,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import { cn } from '@/lib/utils/classnameUtils';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useProjectStore } from '@/store/useProjectStore';
import { moveChatToProject } from '@/services/projects';
import useChatStore from '@/store/useChatStore';

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

export interface ChatHistoryRowProps {
  chat: ChatItem;
  pinIndex?: number;
  isMobile: boolean;
  isActive: boolean;
  isGenerating?: boolean;
  renameId: string | null;
  renameValue: string;
  exportingId: string | null;
  batchMode?: boolean;
  isSelected?: boolean;
  onToggleSelect?: (id: string) => void;
  formatTime: (d: Date) => string;
  onItemClick?: () => void;
  onRename: (chat: ChatItem) => void;
  onRenameSubmit: (id: string) => void;
  onRenameCancel: () => void;
  onRenameValueChange: (v: string) => void;
  onDelete: (id: string) => void;
  onExport: (id: string, mode: 'markdown' | 'json' | 'copy' | 'html') => void;
  onPin: (id: string) => void;
  onUnpin: (id: string) => void;
  onCreateAutomation?: (chatId: string, chatTitle: string) => void;
  onHandoff?: (chatId: string, chatTitle: string, source?: string) => void;
  t: ReturnType<typeof useTranslations>;
}

export const ChatHistoryRow = memo<ChatHistoryRowProps>(
  ({
    chat,
    pinIndex,
    isMobile,
    isActive,
    isGenerating,
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
    onPin,
    onUnpin,
    onCreateAutomation,
    onHandoff,
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
          )}
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
                  if (e.key === 'Enter') onRenameSubmit(chat.id);
                  else if (e.key === 'Escape') onRenameCancel();
                }}
                className={cn(
                  'text-sm font-medium text-black/90 dark:text-white/90 bg-transparent border-b border-primary/50 outline-none w-full',
                  isMobile && 'text-xs',
                )}
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
                {isGenerating && (
                  <span className="relative flex-shrink-0 w-2 h-2">
                    <span className="absolute inset-0 rounded-full bg-accent-warm animate-ping opacity-50" />
                    <span className="relative block w-2 h-2 rounded-full bg-accent-warm" />
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
            <DropdownMenu>
              <DropdownMenuTrigger asChild onClick={(e) => e.preventDefault()}>
                <button
                  className={cn(
                    'transition-opacity p-1 hover:bg-black/10 dark:hover:bg-white/10 rounded min-w-[32px] min-h-[32px] flex items-center justify-center',
                    isMobile ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
                  )}
                  aria-label={t('common.more')}
                >
                  <MoreHorizontal size={isMobile ? 14 : 12} className="text-black/40 dark:text-white/40" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                side="bottom"
                sideOffset={4}
                className={cn(isMobile ? 'min-w-[160px]' : 'min-w-[140px]')}
                onClick={(e) => e.stopPropagation()}
              >
                {chat.isPinned ? (
                  <DropdownMenuItem
                    onClick={() => onUnpin(chat.id)}
                    className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                  >
                    <PinOff size={isMobile ? 16 : 14} className="mr-2" />
                    {t('chat.unpin.action')}
                  </DropdownMenuItem>
                ) : (
                  <DropdownMenuItem
                    onClick={() => onPin(chat.id)}
                    className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                  >
                    <Pin size={isMobile ? 16 : 14} className="mr-2" />
                    {t('chat.pin.action')}
                  </DropdownMenuItem>
                )}
                {onCreateAutomation && (
                  <DropdownMenuItem
                    onClick={() => onCreateAutomation(chat.id, chat.title)}
                    className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                  >
                    <Timer size={isMobile ? 16 : 14} className="mr-2" />
                    {t('chat.createAutomation')}
                  </DropdownMenuItem>
                )}
                {onHandoff && (
                  <DropdownMenuItem
                    onClick={() => onHandoff(chat.id, chat.title, chat.source)}
                    className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                  >
                    <ArrowRightLeft size={isMobile ? 16 : 14} className="mr-2" />
                    {t('chat.handoff.menuAction')}
                  </DropdownMenuItem>
                )}
                <MoveToProjectMenu chatId={chat.id} currentProjectId={chat.projectId} isMobile={isMobile} t={t} />
                <DropdownMenuItem
                  onClick={() => onRename(chat)}
                  className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                >
                  <Edit3 size={isMobile ? 16 : 14} className="mr-2" />
                  {t('common.rename')}
                </DropdownMenuItem>
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger
                    className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                    disabled={exportingId === chat.id}
                  >
                    <Download size={isMobile ? 16 : 14} className="mr-2" />
                    {exportingId === chat.id ? t('chat.exportChat.exporting') : t('common.export')}
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent>
                    <DropdownMenuItem
                      onClick={() => onExport(chat.id, 'html')}
                      className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                    >
                      <FileCode2 size={isMobile ? 16 : 14} className="mr-2" />
                      {t('chat.exportChat.exportHtml')}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => onExport(chat.id, 'markdown')}
                      className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                    >
                      <FileText size={isMobile ? 16 : 14} className="mr-2" />
                      {t('chat.exportChat.exportMarkdown')}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => onExport(chat.id, 'json')}
                      className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                    >
                      <FileJson size={isMobile ? 16 : 14} className="mr-2" />
                      {t('chat.exportChat.exportJson')}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => onExport(chat.id, 'copy')}
                      className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
                    >
                      <Copy size={isMobile ? 16 : 14} className="mr-2" />
                      {t('chat.exportChat.copyMarkdown')}
                    </DropdownMenuItem>
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
                <DropdownMenuItem
                  onClick={() => onDelete(chat.id)}
                  className={cn('text-destructive focus:text-destructive', isMobile && 'py-3 text-xs min-h-[44px]')}
                >
                  <Trash2 size={isMobile ? 16 : 14} className="mr-2" />
                  {t('common.delete')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </Link>
      </div>
    </div>
  ),
);
ChatHistoryRow.displayName = 'ChatHistoryRow';

export const SortablePinnedRow = memo<ChatHistoryRowProps>(({ chat, ...rest }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: chat.id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <ChatHistoryRow chat={chat} {...rest} />
    </div>
  );
});
SortablePinnedRow.displayName = 'SortablePinnedRow';

function MoveToProjectMenu({
  chatId,
  currentProjectId,
  isMobile,
  t,
}: {
  chatId: string;
  currentProjectId?: string | null;
  isMobile: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  const projects = useProjectStore((s) => s.projects);

  const handleMove = async (projectId: string | null) => {
    await moveChatToProject(chatId, projectId);
    const items = useChatStore.getState().chatHistoryItems;
    useChatStore.setState({
      chatHistoryItems: items.map((item) => (item.id === chatId ? { ...item, projectId } : item)),
    });
  };

  if (projects.length === 0) return null;

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}>
        <FolderInput size={isMobile ? 16 : 14} className="mr-2" />
        {t('project.moveTo')}
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent>
        {currentProjectId && (
          <DropdownMenuItem onClick={() => handleMove(null)} className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}>
            <FolderX size={isMobile ? 16 : 14} className="mr-2 text-muted-foreground" />
            {t('project.removeFromProject')}
          </DropdownMenuItem>
        )}
        {projects.map((p) => (
          <DropdownMenuItem
            key={p.id}
            onClick={() => handleMove(p.id)}
            disabled={currentProjectId === p.id}
            className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
          >
            <span className="w-2.5 h-2.5 rounded-full mr-2 flex-shrink-0" style={{ backgroundColor: p.color }} />
            {p.name}
            {currentProjectId === p.id && (
              <span className="ml-auto text-[10px] text-muted-foreground">{t('project.current')}</span>
            )}
          </DropdownMenuItem>
        ))}
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

function getProjectColor(projectId: string | null | undefined): string | undefined {
  if (!projectId) return undefined;
  const project = useProjectStore.getState().projects.find((p) => p.id === projectId);
  return project?.color;
}
