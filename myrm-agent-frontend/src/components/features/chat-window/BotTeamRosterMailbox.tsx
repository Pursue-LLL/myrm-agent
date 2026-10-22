'use client';

import React, { useState } from 'react';
import {
  Users,
  Mail,
  Send,
  AtSign,
  X,
  Circle,
  Briefcase,
  ChevronRight,
} from 'lucide-react';

export type BotStatusType = 'idle' | 'busy' | 'offline';
export type MessagePriorityType = 'low' | 'normal' | 'high' | 'urgent';

export interface BotProfileData {
  bot_id: string;
  handle: string;
  display_name: string;
  role_description: string;
  avatar_seed?: string;
  model_tier?: string;
  skills?: string[];
  tools?: string[];
  status: BotStatusType;
  active_task_id?: string | null;
  unread_count?: number;
}

export interface BotMessageData {
  message_id: string;
  from_bot: string;
  to_bot: string;
  thread_id?: string;
  subject: string;
  body: string;
  priority: MessagePriorityType;
  is_read: boolean;
  timestamp?: string;
}

export interface BotTeamRosterMailboxProps {
  sessionId: string;
  bots: BotProfileData[];
  selectedBotId?: string;
  inboxMessages?: BotMessageData[];
  onSelectBot?: (botId: string) => void;
  onSendMessage?: (toBot: string, subject: string, body: string, priority: MessagePriorityType) => void;
  onDispatchMentions?: (text: string) => void;
  onMarkRead?: (botId: string, messageIds: string[]) => void;
  onClose?: () => void;
  className?: string;
}

const STATUS_CONFIG: Record<BotStatusType, { label: string; color: string; badgeColor: string }> = {
  idle: {
    label: '就绪',
    color: 'bg-emerald-500',
    badgeColor: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800',
  },
  busy: {
    label: '忙碌',
    color: 'bg-amber-500',
    badgeColor: 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border-amber-200 dark:border-amber-800',
  },
  offline: {
    label: '离线',
    color: 'bg-gray-400',
    badgeColor: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 border-gray-300 dark:border-gray-700',
  },
};

const PRIORITY_BADGES: Record<MessagePriorityType, { label: string; style: string }> = {
  urgent: { label: '紧急', style: 'bg-rose-100 text-rose-700 dark:bg-rose-900/50 dark:text-rose-300' },
  high: { label: '高', style: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300' },
  normal: { label: '普通', style: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300' },
  low: { label: '低', style: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300' },
};

export const BotTeamRosterMailbox: React.FC<BotTeamRosterMailboxProps> = ({
  bots,
  selectedBotId,
  inboxMessages = [],
  onSelectBot,
  onSendMessage,
  onDispatchMentions,
  onMarkRead,
  onClose,
  className = '',
}) => {
  const [activeBotId, setActiveBotId] = useState<string>(selectedBotId || (bots[0]?.bot_id ?? ''));
  const [showCompose, setShowCompose] = useState<boolean>(false);
  const [composeSubject, setComposeSubject] = useState<string>('');
  const [composeBody, setComposeBody] = useState<string>('');
  const [composePriority, setComposePriority] = useState<MessagePriorityType>('normal');
  const [mentionDraft, setMentionDraft] = useState<string>('');

  const activeBot = bots.find((b) => b.bot_id === activeBotId) || bots[0];

  const handleSelect = (botId: string) => {
    setActiveBotId(botId);
    if (onSelectBot) {
      onSelectBot(botId);
    }
  };

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeBot || !composeBody.trim() || !onSendMessage) {
      return;
    }
    onSendMessage(
      activeBot.handle,
      composeSubject.trim() || 'Workstation Direct Message',
      composeBody.trim(),
      composePriority,
    );
    setComposeSubject('');
    setComposeBody('');
    setShowCompose(false);
  };

  const handleDispatchMentions = (e: React.FormEvent) => {
    e.preventDefault();
    if (!mentionDraft.trim() || !onDispatchMentions) {
      return;
    }
    onDispatchMentions(mentionDraft.trim());
    setMentionDraft('');
  };

  const handleMarkAllRead = () => {
    if (!activeBot || !onMarkRead) {
      return;
    }
    const unreadIds = inboxMessages.filter((m) => !m.is_read).map((m) => m.message_id);
    if (unreadIds.length > 0) {
      onMarkRead(activeBot.bot_id, unreadIds);
    }
  };

  return (
    <section
      aria-label="Bot Mode Team Roster & Mailbox"
      className={`flex flex-col border border-border/80 bg-background/95 backdrop-blur-md rounded-xl shadow-xl overflow-hidden transition-all duration-300 ${className}`}
    >
      <div className="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-foreground flex items-center gap-2">
              AI 同事花名册与工位信箱
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary/15 text-primary font-medium">
                {bots.length} 名成员
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">对标 Hermes Bot Mode · @mention 寻址投递</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowCompose(!showCompose)}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
            发信
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close Bot Mode Panel"
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border min-h-[320px] max-h-[500px]">
        <div className="p-3 overflow-y-auto space-y-2 bg-muted/10">
          <div className="text-xs font-medium text-muted-foreground px-1 pb-1">具名同事工位</div>
          {bots.length === 0 ? (
            <div className="p-4 text-center text-xs text-muted-foreground">暂无注册的 AI 同事</div>
          ) : (
            bots.map((bot) => {
              const statusMeta = STATUS_CONFIG[bot.status];
              const isSelected = activeBot?.bot_id === bot.bot_id;
              return (
                <button
                  key={bot.bot_id}
                  type="button"
                  onClick={() => handleSelect(bot.bot_id)}
                  className={`w-full text-left p-2.5 rounded-lg border transition-all flex items-start gap-2.5 ${
                    isSelected ? 'border-primary/50 bg-primary/5 shadow-sm' : 'border-border/60 hover:border-border hover:bg-muted/40'
                  }`}
                >
                  <div className="relative flex-shrink-0">
                    <div className="w-8 h-8 rounded-full bg-secondary/80 flex items-center justify-center font-bold text-xs uppercase text-foreground">
                      {bot.display_name.slice(0, 2)}
                    </div>
                    <span
                      aria-label={`状态: ${statusMeta.label}`}
                      className={`absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2 border-background ${statusMeta.color}`}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-xs font-semibold text-foreground truncate">{bot.display_name}</span>
                      {(bot.unread_count ?? 0) > 0 && (
                        <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-rose-500 text-white animate-pulse">
                          {bot.unread_count}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] font-mono text-primary flex items-center gap-0.5">
                      <AtSign className="w-2.5 h-2.5" />
                      {bot.handle.replace(/^@/, '')}
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5">{bot.role_description}</p>
                  </div>
                  <ChevronRight className={`w-3.5 h-3.5 self-center ${isSelected ? 'text-primary' : 'text-muted-foreground/40'}`} />
                </button>
              );
            })
          )}
        </div>

        <div className="col-span-2 flex flex-col p-4 overflow-y-auto space-y-4">
          {activeBot ? (
            <>
              <div className="flex items-start justify-between border-b border-border/60 pb-3">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold text-base">
                    {activeBot.display_name.slice(0, 2)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-bold text-foreground">{activeBot.display_name}</h4>
                      <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{activeBot.handle}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${STATUS_CONFIG[activeBot.status].badgeColor}`}>
                        {STATUS_CONFIG[activeBot.status].label}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{activeBot.role_description}</p>
                    {activeBot.active_task_id && (
                      <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1 flex items-center gap-1 font-mono">
                        <Briefcase className="w-3 h-3" />
                        任务在执行: {activeBot.active_task_id}
                      </p>
                    )}
                  </div>
                </div>
                {activeBot.model_tier && (
                  <span className="text-[11px] px-2 py-0.5 rounded bg-secondary text-secondary-foreground font-mono">
                    Tier: {activeBot.model_tier}
                  </span>
                )}
              </div>

              {showCompose && (
                <form onSubmit={handleSend} className="p-3 rounded-lg border border-primary/30 bg-primary/5 space-y-2 animate-in fade-in">
                  <div className="flex items-center justify-between text-xs font-semibold text-foreground">
                    <span>向 {activeBot.handle} 投递对等信件</span>
                    <select
                      value={composePriority}
                      onChange={(e) => setComposePriority(e.target.value as MessagePriorityType)}
                      aria-label="消息优先级"
                      className="text-xs bg-background border border-border rounded px-1.5 py-0.5"
                    >
                      <option value="low">低优先级</option>
                      <option value="normal">普通优先级</option>
                      <option value="high">高优先级</option>
                      <option value="urgent">紧急打断</option>
                    </select>
                  </div>
                  <input
                    type="text"
                    value={composeSubject}
                    onChange={(e) => setComposeSubject(e.target.value)}
                    placeholder="主题 (Subject)..."
                    className="w-full text-xs px-2.5 py-1.5 rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <textarea
                    rows={2}
                    value={composeBody}
                    onChange={(e) => setComposeBody(e.target.value)}
                    placeholder="正文与参数任务描述..."
                    className="w-full text-xs px-2.5 py-1.5 rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary resize-none"
                  />
                  <div className="flex justify-end gap-2">
                    <button type="button" onClick={() => setShowCompose(false)} className="px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground">
                      取消
                    </button>
                    <button type="submit" className="px-3 py-1 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90">
                      发送
                    </button>
                  </div>
                </form>
              )}

              <form onSubmit={handleDispatchMentions} className="flex gap-2">
                <input
                  type="text"
                  value={mentionDraft}
                  onChange={(e) => setMentionDraft(e.target.value)}
                  placeholder="文本包含 @handle 自动广播寻址分发..."
                  className="flex-1 text-xs px-2.5 py-1.5 rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button
                  type="submit"
                  className="px-3 py-1.5 text-xs font-medium rounded border border-border hover:bg-muted text-foreground flex items-center gap-1"
                >
                  <AtSign className="w-3.5 h-3.5 text-primary" />
                  广播
                </button>
              </form>

              <div className="space-y-2 flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Mail className="w-3.5 h-3.5 text-primary" />
                    工位信箱收件 ({inboxMessages.length})
                  </span>
                  {inboxMessages.some((m) => !m.is_read) && (
                    <button type="button" onClick={handleMarkAllRead} className="text-[11px] text-primary hover:underline">
                      全部标为已读
                    </button>
                  )}
                </div>

                {inboxMessages.length === 0 ? (
                  <div className="p-6 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                    收件箱暂无往来信件
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    {inboxMessages.map((msg) => {
                      const prioMeta = PRIORITY_BADGES[msg.priority];
                      return (
                        <div
                          key={msg.message_id}
                          className={`p-2.5 rounded-lg border text-xs transition-colors ${
                            msg.is_read ? 'border-border/60 bg-card/60 text-muted-foreground' : 'border-primary/40 bg-primary/5 text-foreground font-medium'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <span className="font-semibold text-xs text-foreground flex items-center gap-1">
                              {!msg.is_read && <Circle className="w-2 h-2 fill-primary text-primary" />}
                              {msg.subject}
                            </span>
                            <span className={`px-1.5 py-0.2 rounded text-[10px] ${prioMeta.style}`}>
                              {prioMeta.label}
                            </span>
                          </div>
                          <p className="text-xs text-foreground/90 whitespace-pre-wrap">{msg.body}</p>
                          <div className="flex items-center justify-between mt-2 pt-1 border-t border-border/40 text-[10px] text-muted-foreground">
                            <span>From: {msg.from_bot}</span>
                            <span>{msg.timestamp || '刚刚'}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="p-8 text-center text-xs text-muted-foreground">请在左侧选择 AI 同事工位</div>
          )}
        </div>
      </div>
    </section>
  );
};

export default BotTeamRosterMailbox;
