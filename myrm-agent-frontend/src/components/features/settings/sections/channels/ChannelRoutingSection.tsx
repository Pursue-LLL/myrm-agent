'use client';

/**
 * [INPUT]
 * @/services/channels (POS: Frontend channel management API client)
 * @/services/agent (POS: Frontend Agent API client)
 * @/components/features/memory/SharedContextTargetBinding (POS: Shared Context runtime binding component)
 *
 * [OUTPUT]
 * ChannelRoutingSection: Channel-level Agent routing, thread sharing, and Shared Context binding UI.
 *
 * [POS]
 * Settings section for configuring connected channel routing and inherited Shared Contexts.
 */

import { useEffect, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { IconPlug, IconAlertCircle, IconLoader, IconUser } from '@/components/features/icons/PremiumIcons';
import { Users } from 'lucide-react';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import SettingsSection from './SettingsSection';
import {
  bindTopicAgent,
  getChannelTopics,
  listChannelStatuses,
  setChannelDefaultAgent,
  type ChannelStatus,
  type TopicBinding,
  type ThreadSharingMode,
} from '@/services/channels';
import { listAgents } from '@/services/agent';
import type { AgentListItem } from '@/services/agent';
import { toast } from 'sonner';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { SharedContextTargetBinding } from '@/components/features/memory/SharedContextTargetBinding';

export default function ChannelRoutingSection() {
  const t = useTranslations('settings.sections.channelRouting');
  const locale = useLocale();

  const [channels, setChannels] = useState<ChannelStatus[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);

  const [topics, setTopics] = useState<TopicBinding[]>([]);
  const [globalAgentId, setGlobalAgentId] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentListItem[]>([]);

  const [loadingChannels, setLoadingChannels] = useState(true);
  const [loadingTopics, setLoadingTopics] = useState(false);
  const [saving, setSaving] = useState<string | null>(null); // topicId or 'global'

  const selectedChannelStatus = channels.find((channel) => channel.name === selectedChannel) ?? null;

  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const [channelsRes, agentsRes] = await Promise.all([
          listChannelStatuses(),
          listAgents(1, 100), // fetch up to 100 agents
        ]);
        const connectedChannels = channelsRes.filter((channel) => channel.connected);
        setChannels(connectedChannels);
        setAgents(agentsRes.items);

        if (connectedChannels.length > 0) {
          setSelectedChannel(connectedChannels[0].name);
        }
      } catch (error) {
        console.error('Failed to fetch initial data:', error);
        toast.error(t('errors.initialLoad'));
      } finally {
        setLoadingChannels(false);
      }
    };

    fetchInitialData();
  }, [t]);

  useEffect(() => {
    if (!selectedChannel) return;

    const fetchTopics = async () => {
      setLoadingTopics(true);
      try {
        const res = await getChannelTopics(selectedChannel);
        setTopics(res.topics);
        setGlobalAgentId(res.globalAgentId);
      } catch (error) {
        console.error('Failed to fetch topics:', error);
        toast.error(t('errors.topicsLoad'));
      } finally {
        setLoadingTopics(false);
      }
    };

    fetchTopics();
  }, [selectedChannel, t]);

  const handleBindTopic = async (topicId: string, agentId: string) => {
    if (!selectedChannel) return;
    setSaving(topicId);
    try {
      const newAgentId = agentId === 'none' ? null : agentId;
      await bindTopicAgent(selectedChannel, topicId, newAgentId);
      setTopics((prev) => prev.map((t) => (t.topicId === topicId ? { ...t, agentId: newAgentId } : t)));
      toast.success(t('toasts.agentBound'));
    } catch (error) {
      console.error('Failed to bind agent:', error);
      toast.error(t('errors.agentBind'));
    } finally {
      setSaving(null);
    }
  };

  const handleSetThreadSharingMode = async (topicId: string, mode: ThreadSharingMode) => {
    if (!selectedChannel) return;
    setSaving(topicId);
    try {
      const topic = topics.find((t) => t.topicId === topicId);
      await bindTopicAgent(selectedChannel, topicId, topic?.agentId ?? null, mode);
      setTopics((prev) => prev.map((t) => (t.topicId === topicId ? { ...t, threadSharingMode: mode } : t)));
      toast.success(t('toasts.threadSharingUpdated'));
    } catch (error) {
      console.error('Failed to set sharing mode:', error);
      toast.error(t('errors.threadSharing'));
    } finally {
      setSaving(null);
    }
  };

  const handleSetGlobalAgent = async (agentId: string) => {
    if (!selectedChannel) return;
    setSaving('global');
    try {
      const newAgentId = agentId === 'none' ? null : agentId;
      await setChannelDefaultAgent(selectedChannel, newAgentId);
      setGlobalAgentId(newAgentId);
      toast.success(t('toasts.globalAgentSet'));
    } catch (error) {
      console.error('Failed to set global agent:', error);
      toast.error(t('errors.globalAgent'));
    } finally {
      setSaving(null);
    }
  };

  if (loadingChannels) {
    return (
      <div className="flex items-center justify-center py-12">
        <IconLoader className="w-8 h-8 animate-spin text-primary/50" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Left sidebar: Channels */}
          <div className="w-full lg:w-48 flex-shrink-0 border-r pr-4">
            <h3 className="text-sm font-medium mb-3 text-muted-foreground">{t('connectedChannels')}</h3>
            {channels.length === 0 ? (
              <div className="text-sm text-muted-foreground flex items-center gap-2 p-3 bg-muted/30 rounded-lg">
                <IconAlertCircle className="w-4 h-4" />
                {t('noConnectedChannels')}
              </div>
            ) : (
              <div className="space-y-1">
                {channels.map((channel) => (
                  <button
                    key={channel.name}
                    onClick={() => setSelectedChannel(channel.name)}
                    className={`w-full text-left px-3 py-2 rounded-full text-sm transition-colors ${
                      selectedChannel === channel.name
                        ? 'bg-primary/10 text-primary font-medium'
                        : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <span>{channel.displayName || channel.name}</span>
                    {channel.displayName && channel.displayName !== channel.name ? (
                      <span className="block truncate text-[11px] opacity-70">{channel.name}</span>
                    ) : null}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Right content: Topics */}
          <div className="flex-1 min-w-0">
            {selectedChannel ? (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b pb-4">
                  <h3 className="text-lg font-medium">
                    {t('routingFor', {
                      channel: selectedChannelStatus?.displayName || selectedChannel,
                    })}
                  </h3>
                </div>

                {loadingTopics ? (
                  <div className="flex items-center justify-center py-12">
                    <IconLoader className="w-6 h-6 animate-spin text-primary/50" />
                  </div>
                ) : (
                  <div className="space-y-6">
                    <SharedContextTargetBinding
                      targetType="channel"
                      targetId={selectedChannel}
                      targetLabel={t('sharedContexts.targetLabel')}
                      className="bg-muted/20"
                    />

                    {/* Global Default Agent */}
                    <div className="bg-muted/30 p-4 rounded-lg border border-border/50">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <h4 className="font-medium text-sm">{t('globalDefaultAgent')}</h4>
                          <p className="text-xs text-muted-foreground">{t('globalDefaultAgentDesc')}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          {saving === 'global' && <IconLoader className="w-4 h-4 animate-spin text-primary/50" />}
                          <select
                            value={globalAgentId || 'none'}
                            onChange={(e) => handleSetGlobalAgent(e.target.value)}
                            disabled={saving === 'global'}
                            className="bg-background border border-input rounded-full text-sm px-3 py-1.5 focus:ring-2 focus:ring-primary/20 outline-none"
                          >
                            <option value="none">{t('noDefaultAgent')}</option>
                            {agents.map((agent) => (
                              <option key={agent.id} value={agent.id}>
                                {getBuiltinAgentName(agent.id, agent.name, locale)}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </div>

                    {/* Topic Bindings */}
                    <div>
                      <h4 className="font-medium text-sm mb-3">{t('topicBindings')}</h4>
                      {topics.length === 0 ? (
                        <div className="text-sm text-muted-foreground p-4 bg-muted/20 rounded-lg border border-dashed text-center">
                          {t('noActiveTopics')}
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {topics.map((topic) => (
                            <div
                              key={topic.topicId}
                              className="flex flex-col gap-3 p-3 bg-background border rounded-lg hover:border-primary/30 transition-colors"
                            >
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
                                  {saving === topic.topicId && (
                                    <IconLoader className="w-4 h-4 animate-spin text-primary/50" />
                                  )}
                                  <select
                                    value={topic.agentId || 'none'}
                                    onChange={(e) => handleBindTopic(topic.topicId, e.target.value)}
                                    disabled={saving === topic.topicId}
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

                              {/* Thread Sharing Mode */}
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
                                    onClick={() => handleSetThreadSharingMode(topic.topicId, 'isolated')}
                                    disabled={saving === topic.topicId}
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
                                    onClick={() => handleSetThreadSharingMode(topic.topicId, 'shared')}
                                    disabled={saving === topic.topicId}
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
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full min-h-[200px] text-muted-foreground flex-col gap-2">
                <IconPlug className="w-8 h-8 opacity-20" />
                <p>{t('selectChannelPrompt')}</p>
              </div>
            )}
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
