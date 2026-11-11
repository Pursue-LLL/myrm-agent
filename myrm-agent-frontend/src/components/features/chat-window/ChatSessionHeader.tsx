'use client';

/**
 * [INPUT]
 * - ./ParentChatLink, ChatCronLink, ReplayAction, SessionExportButton, DashboardWorkspaceLink (POS: 会话级入口)
 * - ../message-actions/SessionRevertButton (POS: 会话回退)
 * - next-intl recovery.dualTab* (POS: 标签文案)
 *
 * [OUTPUT]
 * - ChatSessionHeader: 会话工具条（父会话 / 定时任务 / 回退 / 回放 / 导出 / 工作区入口）与「对话 / 执行轨迹」标签切换
 * - ChatWindowTab: 标签取值
 *
 * [POS]
 * ChatWindow 活跃会话顶部工具条，只在有会话 id 时渲染；标签状态由 ChatWindow 持有。
 */

import type { ReactNode } from 'react';
import { Activity, MessageSquare } from 'lucide-react';
import { useTranslations } from 'next-intl';
import SessionRevertButton from '../message-actions/SessionRevertButton';
import { ChatCronLink } from './ChatCronLink';
import { DashboardWorkspaceLink } from './DashboardWorkspaceLink';
import { ParentChatLink } from './ParentChatLink';
import ReplayAction from './ReplayAction';
import SessionExportButton from './SessionExportButton';

export type ChatWindowTab = 'chat' | 'trace';

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
}

const TabButton = ({ active, onClick, icon, label }: TabButtonProps) => (
  <button
    type="button"
    aria-pressed={active}
    onClick={onClick}
    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-all ${
      active ? 'bg-background text-foreground shadow-xs font-semibold' : 'text-muted-foreground hover:text-foreground'
    }`}
  >
    {icon}
    <span>{label}</span>
  </button>
);

interface ChatSessionHeaderProps {
  chatId: string;
  activeTab: ChatWindowTab;
  onTabChange: (tab: ChatWindowTab) => void;
}

const ChatSessionHeader = ({ chatId, activeTab, onTabChange }: ChatSessionHeaderProps) => {
  const recoveryT = useTranslations('recovery');

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 border-b border-border/30 bg-muted/20">
      {/* Everything in this group belongs to one chat: another chat starts it afresh, so nothing of the last one lingers. */}
      <div key={chatId} className="flex flex-wrap items-center gap-2">
        <ParentChatLink chatId={chatId} />
        <ChatCronLink chatId={chatId} />
        <SessionRevertButton sessionId={chatId} />
        <ReplayAction chatId={chatId} />
        <SessionExportButton chatId={chatId} />
        <DashboardWorkspaceLink />
      </div>
      <div className="inline-flex items-center rounded-lg bg-muted/60 p-0.5 text-xs font-medium border border-border/40">
        <TabButton
          active={activeTab === 'chat'}
          onClick={() => onTabChange('chat')}
          icon={<MessageSquare className="h-3.5 w-3.5" />}
          label={recoveryT('dualTabChat')}
        />
        <TabButton
          active={activeTab === 'trace'}
          onClick={() => onTabChange('trace')}
          icon={<Activity className="h-3.5 w-3.5 text-amber-500" />}
          label={recoveryT('dualTabTrace')}
        />
      </div>
    </div>
  );
};

export default ChatSessionHeader;
