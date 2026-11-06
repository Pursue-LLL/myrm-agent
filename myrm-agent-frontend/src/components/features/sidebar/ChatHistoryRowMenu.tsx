'use client';

/**
 * [INPUT]
 * - @/components/primitives/dropdown-menu (POS: 下拉菜单原语)
 * - @/services/chatExportPack::exportSessionZipPack (POS: 会话 ZIP 导出)
 * - @/services/projects::moveChatToProject (POS: 会话移入项目)
 * - @/store/useProjectStore::useProjectStore (POS: 项目列表)
 * - @/store/useChatStore::useChatStore (POS: 会话历史缓存)
 *
 * [OUTPUT]
 * - ChatHistoryRowMenu: 会话条目的「更多」菜单。
 * - ChatHistoryRowMenuProps: 菜单与条目共用的会话属性与操作回调。
 *
 * [POS]
 * 一行会话的全部操作入口（置顶、新窗口、自动化、交接、分叉、移入项目、重命名、导出、IDE 打开、分享、定位产物、沉淀评测用例、删除）；
 * 菜单项由调用方是否提供回调决定出现与否，手机上菜单项放大到 44px 触控高度。
 */
import {
  Archive,
  ArrowRightLeft,
  Copy,
  Download,
  Edit3,
  ExternalLink,
  FileCode2,
  FileJson,
  FileText,
  FlaskConical,
  FolderInput,
  FolderOpen,
  FolderX,
  GitFork,
  MoreHorizontal,
  Pin,
  PinOff,
  Printer,
  Share2,
  Timer,
  Trash2,
} from 'lucide-react';
import type { useTranslations } from 'next-intl';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import type { IdeHandoffTarget } from '@/lib/ide-handoff';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import type { ChatItem } from '@/services/chat';
import { exportSessionZipPack } from '@/services/chatExportPack';
import { moveChatToProject } from '@/services/projects';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';

export interface ChatHistoryRowMenuProps {
  chat: ChatItem;
  isMobile: boolean;
  exportingId: string | null;
  isRevealingArtifacts?: boolean;
  onRename: (chat: ChatItem) => void;
  onDelete: (id: string) => void;
  onExport: (id: string, mode: 'markdown' | 'json' | 'copy' | 'html' | 'print') => void;
  onOpenInIDE?: (id: string, target: IdeHandoffTarget) => void;
  onShare?: (id: string) => void;
  onPin: (id: string) => void;
  onUnpin: (id: string) => void;
  onCreateAutomation?: (chatId: string, chatTitle: string) => void;
  onHandoff?: (chatId: string, chatTitle: string, source?: string) => void;
  onFork?: (chatId: string) => void;
  onOpenInNewWindow?: (chatId: string) => void;
  onRevealArtifacts?: (chatId: string) => void;
  onCaptureEvalCase?: (chatId: string) => void;
  t: ReturnType<typeof useTranslations>;
}

export function ChatHistoryRowMenu({
  chat,
  isMobile,
  exportingId,
  isRevealingArtifacts = false,
  onRename,
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
  onCaptureEvalCase,
  t,
}: ChatHistoryRowMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild onClick={(e) => e.preventDefault()}>
        <button
          className={cn(
            'transition-opacity p-1 hover:bg-black/10 dark:hover:bg-white/10 rounded min-w-[32px] min-h-[32px] flex items-center justify-center',
            REVEAL_ON_HOVER,
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
          <DropdownMenuItem onClick={() => onUnpin(chat.id)} className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}>
            <PinOff size={isMobile ? 16 : 14} className="mr-2" />
            {t('chat.unpin.action')}
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem onClick={() => onPin(chat.id)} className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}>
            <Pin size={isMobile ? 16 : 14} className="mr-2" />
            {t('chat.pin.action')}
          </DropdownMenuItem>
        )}
        {onOpenInNewWindow && (
          <DropdownMenuItem
            onClick={() => onOpenInNewWindow(chat.id)}
            className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
          >
            <ExternalLink size={isMobile ? 16 : 14} className="mr-2" />
            {t('chat.openInNewWindow')}
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
        {onFork && (
          <DropdownMenuItem onClick={() => onFork(chat.id)} className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}>
            <GitFork size={isMobile ? 16 : 14} className="mr-2" />
            {t('chat.fork.buttonTitle')}
          </DropdownMenuItem>
        )}
        <MoveToProjectMenu chatId={chat.id} currentProjectId={chat.projectId} isMobile={isMobile} t={t} />
        <DropdownMenuItem onClick={() => onRename(chat)} className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}>
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
            <DropdownMenuItem
              onClick={() => onExport(chat.id, 'print')}
              className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
            >
              <Printer size={isMobile ? 16 : 14} className="mr-2" />
              {t('chat.exportChat.print')}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                exportSessionZipPack(chat.id).catch((err: unknown) => {
                  toast.error(err instanceof Error ? err.message : t('chat.exportChat.exportZipFailed'));
                });
              }}
              className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
            >
              <Archive size={isMobile ? 16 : 14} className="mr-2" />
              {t('chat.exportChat.exportZipPack')}
            </DropdownMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        {onOpenInIDE && (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger
              className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
              disabled={exportingId === chat.id}
            >
              <ExternalLink size={isMobile ? 16 : 14} className="mr-2" />
              {t('chat.ideHandoff.openInIDE')}
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuItem
                onClick={() => onOpenInIDE(chat.id, 'cursor')}
                className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
              >
                {t('chat.ideHandoff.cursor')}
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => onOpenInIDE(chat.id, 'vscode')}
                className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
              >
                {t('chat.ideHandoff.vscode')}
              </DropdownMenuItem>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        )}
        {onShare && (
          <DropdownMenuItem onClick={() => onShare(chat.id)} className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}>
            <Share2 size={isMobile ? 16 : 14} className="mr-2" />
            {t('chat.share.share')}
          </DropdownMenuItem>
        )}
        {onRevealArtifacts && (
          <DropdownMenuItem
            onClick={() => onRevealArtifacts(chat.id)}
            disabled={isRevealingArtifacts}
            className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
          >
            <FolderOpen size={isMobile ? 16 : 14} className="mr-2" />
            {isRevealingArtifacts ? t('chat.revealArtifacts.revealing') : t('chat.revealArtifacts.action')}
          </DropdownMenuItem>
        )}
        {onCaptureEvalCase && (
          <DropdownMenuItem
            onClick={() => onCaptureEvalCase(chat.id)}
            className={cn(isMobile && 'py-3 text-xs min-h-[44px]')}
          >
            <FlaskConical size={isMobile ? 16 : 14} className="mr-2 text-primary" />
            {t('chat.captureEvalCase.action')}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          onClick={() => onDelete(chat.id)}
          className={cn('text-destructive focus:text-destructive', isMobile && 'py-3 text-xs min-h-[44px]')}
        >
          <Trash2 size={isMobile ? 16 : 14} className="mr-2" />
          {t('common.delete')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

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

  if (projects.length === 0) {
    return null;
  }

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
