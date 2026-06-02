'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { ExternalLink, X, Clock, Bot, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { PaneConfig } from '@/store/useWorkspaceStore';
import type { ChatHistoryItem } from '@/store/chat/types';
import useWorkspaceStore from '@/store/useWorkspaceStore';

interface PaneCardProps {
  pane: PaneConfig;
  isActive: boolean;
  chatHistory: ChatHistoryItem[];
  onSelect: () => void;
  onClose: () => void;
}

export default function PaneCard({ pane, isActive, chatHistory, onSelect, onClose }: PaneCardProps) {
  const t = useTranslations('multiPane');
  const router = useRouter();
  const { activeSessions, updatePaneChatId } = useWorkspaceStore((s) => ({
    activeSessions: s.activeSessions,
    updatePaneChatId: s.updatePaneChatId,
  }));

  const activeSession = pane.chatId ? activeSessions.find((s) => s.chatId === pane.chatId) : null;
  const isRunning = !!activeSession;
  const chatInfo = pane.chatId ? chatHistory.find((c) => c.id === pane.chatId) : null;

  const recentChats = useMemo(
    () => [...chatHistory].sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime()).slice(0, 10),
    [chatHistory],
  );

  const handleOpenChat = () => {
    if (pane.chatId) {
      router.push(`/${pane.chatId}`);
    }
  };

  const handleSelectChat = (chatId: string) => {
    updatePaneChatId(pane.id, chatId);
  };

  return (
    <div
      onClick={onSelect}
      className={cn(
        'relative flex flex-col rounded-xl border transition-all cursor-pointer',
        'bg-card hover:shadow-md',
        isActive ? 'border-primary/50 ring-1 ring-primary/20' : 'border-border/50 hover:border-border',
        isRunning && 'border-green-500/30',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/30">
        <div className="flex items-center gap-2 min-w-0">
          <Bot size={16} className={cn(isRunning ? 'text-green-500' : 'text-muted-foreground')} />
          <span className="text-sm font-medium truncate">{chatInfo?.title || pane.title}</span>
        </div>
        <div className="flex items-center gap-1">
          {isRunning && (
            <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              {t('running')}
            </span>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            className="p-1 rounded-full hover:bg-muted transition-colors text-muted-foreground"
            aria-label={t('closePane')}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 px-4 py-3 min-h-[80px]">
        {pane.chatId ? (
          <div className="space-y-2">
            {chatInfo?.lastMessage && (
              <p className="text-xs text-muted-foreground line-clamp-3">{chatInfo.lastMessage}</p>
            )}
            {activeSession && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Clock size={12} />
                <span>{t('elapsed', { seconds: activeSession.elapsedSeconds })}</span>
                <span className="text-muted-foreground/50">|</span>
                <span>{activeSession.agentType}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground/80 font-medium">{t('selectChat')}</p>
            {recentChats.length > 0 ? (
              <div className="max-h-[200px] overflow-y-auto space-y-1">
                {recentChats.map((chat) => (
                  <button
                    key={chat.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSelectChat(chat.id);
                    }}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded-full text-left
                      hover:bg-muted/70 transition-colors group"
                  >
                    <MessageSquare size={12} className="text-muted-foreground shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium truncate group-hover:text-primary transition-colors">
                        {chat.title}
                      </p>
                      {chat.lastMessage && (
                        <p className="text-[10px] text-muted-foreground/60 truncate">{chat.lastMessage}</p>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground/50 italic">{t('noChats')}</p>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      {pane.chatId && (
        <div className="px-4 py-2 border-t border-border/30">
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleOpenChat();
            }}
            className="flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 transition-colors"
          >
            <ExternalLink size={12} />
            {t('openChat')}
          </button>
        </div>
      )}
    </div>
  );
}
