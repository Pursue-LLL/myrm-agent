'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  bindTopicAgent,
  getChannelTopics,
  listChannelStatuses,
  setChannelDefaultAgent,
  type ChannelStatus,
  type DraftTimeoutAction,
  type ReplyMode,
  type TopicBinding,
  type ThreadSharingMode,
} from '@/services/channels';
import { listAgents, type AgentListItem } from '@/services/agent';
import { filterChannelBindableAgents } from '@/services/channels/channelAgentBinding';

interface UseChannelRoutingOptions {
  initialLoadError: string;
  topicsLoadError: string;
  agentBoundToast: string;
  agentBindError: string;
  threadSharingUpdatedToast: string;
  threadSharingError: string;
  replyModeUpdatedToast: string;
  replyModeError: string;
  draftTimeoutUpdatedToast: string;
  draftTimeoutError: string;
  globalAgentSetToast: string;
  globalAgentError: string;
}

export function useChannelRouting(messages: UseChannelRoutingOptions) {
  const [channels, setChannels] = useState<ChannelStatus[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [topics, setTopics] = useState<TopicBinding[]>([]);
  const [globalAgentId, setGlobalAgentId] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(true);
  const [loadingTopics, setLoadingTopics] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);

  const selectedChannelStatus = channels.find((channel) => channel.name === selectedChannel) ?? null;

  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const [channelsRes, agentsRes] = await Promise.all([
          listChannelStatuses(),
          listAgents(1, 100),
        ]);
        const connectedChannels = channelsRes.filter((channel) => channel.connected);
        setChannels(connectedChannels);
        setAgents(agentsRes.items);

        if (connectedChannels.length > 0) {
          setSelectedChannel(connectedChannels[0].name);
        }
      } catch (error) {
        console.error('Failed to fetch initial data:', error);
        toast.error(messages.initialLoadError);
      } finally {
        setLoadingChannels(false);
      }
    };

    void fetchInitialData();
  }, [
    messages.initialLoadError,
  ]);

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
        toast.error(messages.topicsLoadError);
      } finally {
        setLoadingTopics(false);
      }
    };

    void fetchTopics();
  }, [selectedChannel, messages.topicsLoadError]);

  const handleBindTopic = async (topicId: string, agentId: string) => {
    if (!selectedChannel) return;
    setSaving(topicId);
    try {
      const newAgentId = agentId === 'none' ? null : agentId;
      await bindTopicAgent(selectedChannel, topicId, newAgentId);
      setTopics((prev) => prev.map((topic) => (
        topic.topicId === topicId ? { ...topic, agentId: newAgentId } : topic
      )));
      toast.success(messages.agentBoundToast);
    } catch (error) {
      console.error('Failed to bind agent:', error);
      toast.error(messages.agentBindError);
    } finally {
      setSaving(null);
    }
  };

  const handleSetThreadSharingMode = async (topicId: string, mode: ThreadSharingMode) => {
    if (!selectedChannel) return;
    setSaving(topicId);
    try {
      const topic = topics.find((item) => item.topicId === topicId);
      await bindTopicAgent(selectedChannel, topicId, topic?.agentId ?? null, mode);
      setTopics((prev) => prev.map((item) => (
        item.topicId === topicId ? { ...item, threadSharingMode: mode } : item
      )));
      toast.success(messages.threadSharingUpdatedToast);
    } catch (error) {
      console.error('Failed to set sharing mode:', error);
      toast.error(messages.threadSharingError);
    } finally {
      setSaving(null);
    }
  };

  const handleSetReplyMode = async (topicId: string, mode: ReplyMode) => {
    if (!selectedChannel) return;
    setSaving(topicId);
    try {
      const topic = topics.find((item) => item.topicId === topicId);
      await bindTopicAgent(
        selectedChannel,
        topicId,
        topic?.agentId ?? null,
        topic?.threadSharingMode,
        mode,
        topic?.draftTimeoutMinutes,
        topic?.draftTimeoutAction,
      );
      setTopics((prev) => prev.map((item) => (
        item.topicId === topicId ? { ...item, replyMode: mode } : item
      )));
      toast.success(messages.replyModeUpdatedToast);
    } catch (error) {
      console.error('Failed to set reply mode:', error);
      toast.error(messages.replyModeError);
    } finally {
      setSaving(null);
    }
  };

  const handleSetDraftTimeout = async (
    topicId: string,
    minutes: number,
    action: DraftTimeoutAction,
  ) => {
    if (!selectedChannel) return;
    setSaving(topicId);
    try {
      const topic = topics.find((item) => item.topicId === topicId);
      await bindTopicAgent(
        selectedChannel,
        topicId,
        topic?.agentId ?? null,
        topic?.threadSharingMode,
        topic?.replyMode,
        minutes,
        action,
      );
      setTopics((prev) => prev.map((item) => (
        item.topicId === topicId
          ? { ...item, draftTimeoutMinutes: minutes, draftTimeoutAction: action }
          : item
      )));
      toast.success(messages.draftTimeoutUpdatedToast);
    } catch (error) {
      console.error('Failed to set draft timeout:', error);
      toast.error(messages.draftTimeoutError);
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
      toast.success(messages.globalAgentSetToast);
    } catch (error) {
      console.error('Failed to set global agent:', error);
      toast.error(messages.globalAgentError);
    } finally {
      setSaving(null);
    }
  };

  return {
    agents,
    channelBindableAgents: filterChannelBindableAgents(agents),
    channels,
    globalAgentId,
    handleBindTopic,
    handleSetDraftTimeout,
    handleSetGlobalAgent,
    handleSetReplyMode,
    handleSetThreadSharingMode,
    loadingChannels,
    loadingTopics,
    saving,
    selectedChannel,
    selectedChannelStatus,
    setSelectedChannel,
    topics,
  };
}
