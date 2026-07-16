'use client';

import { useLocale, useTranslations } from 'next-intl';
import { Users, ShieldCheck, Zap } from 'lucide-react';
import { IconAlertCircle, IconLoader, IconUser } from '@/components/features/icons/PremiumIcons';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import type { AgentListItem } from '@/services/agent';
import type { DraftTimeoutAction, ReplyMode, ThreadSharingMode, TopicBinding } from '@/services/channels';

interface ChannelRoutingTopicRowProps {
  agents: AgentListItem[];
  isSaving: boolean;
  onBindTopic: (topicId: string, agentId: string) => void;
  onSetDraftTimeout: (topicId: string, minutes: number, action: DraftTimeoutAction) => void;
  onSetReplyMode: (topicId: string, mode: ReplyMode) => void;
  onSetThreadSharingMode: (topicId: string, mode: ThreadSharingMode) => void;
  topic: TopicBinding;
}

export function ChannelRoutingTopicRow({
  agents,
  isSaving,
  onBindTopic,
  onSetDraftTimeout,
  onSetReplyMode,
  onSetThreadSharingMode,
  topic,
}: ChannelRoutingTopicRowProps) {
  const t = useTranslations('settings.sections.channelRouting');
  const locale = useLocale();

  return (
    <div className="flex flex-col gap-3 p-3 bg-background border rounded-lg hover:border-primary/30 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {topic.avatarUrl ? (
            <img
              src={topic.avatarUrl}
              alt={topic.displayName || topic.topicId}
              className="w-8 h-8 rounded-full bg-muted"
            />
          ) : (
            <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs text-muted-foreground">
              {(topic.displayName || topic.topicId).substring(0, 2).toUpperCase()}
            </div>
          )}
          <div>
            <div className="font-medium text-sm">{topic.displayName || topic.topicId}</div>
            <div className="text-xs text-muted-foreground font-mono">{topic.topicId}</div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isSaving && <IconLoader className="w-4 h-4 animate-spin text-primary/50" />}
          <select
            value={topic.agentId || 'none'}
            onChange={(event) => onBindTopic(topic.topicId, event.target.value)}
            disabled={isSaving}
            className="bg-background border border-input rounded-full text-sm px-3 py-1.5 focus:ring-2 focus:ring-primary/20 outline-none"
          >
            <option value="none">{t('inheritGlobalDefault')}</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {getBuiltinAgentName(agent.id, agent.name, locale)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex items-center gap-2 pl-11">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <IconAlertCircle className="w-3.5 h-3.5 text-muted-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs">
              <p className="text-xs">{t('threadSharing.tooltip')}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <span className="text-xs text-muted-foreground">{t('threadSharing.label')}:</span>
        <div className="flex gap-1">
          <button
            onClick={() => onSetThreadSharingMode(topic.topicId, 'isolated')}
            disabled={isSaving}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors ${
              topic.threadSharingMode === 'isolated'
                ? 'bg-primary/10 text-primary font-medium'
                : 'bg-muted/50 text-muted-foreground hover:bg-muted'
            }`}
          >
            <IconUser className="w-3 h-3" />
            {t('threadSharing.isolated')}
          </button>
          <button
            onClick={() => onSetThreadSharingMode(topic.topicId, 'shared')}
            disabled={isSaving}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors ${
              topic.threadSharingMode === 'shared'
                ? 'bg-primary/10 text-primary font-medium'
                : 'bg-muted/50 text-muted-foreground hover:bg-muted'
            }`}
          >
            <Users className="w-3 h-3" />
            {t('threadSharing.shared')}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 pl-11">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <IconAlertCircle className="w-3.5 h-3.5 text-muted-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs">
              <p className="text-xs">{t('replyMode.tooltip')}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <span className="text-xs text-muted-foreground">{t('replyMode.label')}:</span>
        <div className="flex gap-1">
          <button
            onClick={() => onSetReplyMode(topic.topicId, 'auto')}
            disabled={isSaving}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors ${
              topic.replyMode === 'auto'
                ? 'bg-primary/10 text-primary font-medium'
                : 'bg-muted/50 text-muted-foreground hover:bg-muted'
            }`}
          >
            <Zap className="w-3 h-3" />
            {t('replyMode.auto')}
          </button>
          <button
            onClick={() => onSetReplyMode(topic.topicId, 'draft_review')}
            disabled={isSaving}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors ${
              topic.replyMode === 'draft_review'
                ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium'
                : 'bg-muted/50 text-muted-foreground hover:bg-muted'
            }`}
          >
            <ShieldCheck className="w-3 h-3" />
            {t('replyMode.draftReview')}
          </button>
        </div>
      </div>

      {topic.replyMode === 'draft_review' && (
        <div className="flex items-center gap-3 pl-11 flex-wrap">
          <span className="text-xs text-muted-foreground">{t('replyMode.timeout')}:</span>
          <select
            value={topic.draftTimeoutMinutes}
            onChange={(event) => onSetDraftTimeout(
              topic.topicId,
              Number(event.target.value),
              topic.draftTimeoutAction,
            )}
            disabled={isSaving}
            className="bg-background border border-input rounded text-xs px-2 py-1 focus:ring-2 focus:ring-primary/20 outline-none"
          >
            <option value={1}>1 min</option>
            <option value={3}>3 min</option>
            <option value={5}>5 min</option>
            <option value={10}>10 min</option>
            <option value={15}>15 min</option>
            <option value={30}>30 min</option>
            <option value={60}>1 hour</option>
          </select>
          <span className="text-xs text-muted-foreground">{t('replyMode.onExpiry')}:</span>
          <select
            value={topic.draftTimeoutAction}
            onChange={(event) => onSetDraftTimeout(
              topic.topicId,
              topic.draftTimeoutMinutes,
              event.target.value as DraftTimeoutAction,
            )}
            disabled={isSaving}
            className="bg-background border border-input rounded text-xs px-2 py-1 focus:ring-2 focus:ring-primary/20 outline-none"
          >
            <option value="auto_reject">{t('replyMode.autoReject')}</option>
            <option value="auto_send">{t('replyMode.autoSend')}</option>
          </select>
        </div>
      )}
    </div>
  );
}
