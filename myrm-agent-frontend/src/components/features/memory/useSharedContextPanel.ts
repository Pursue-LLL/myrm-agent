import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';

import { toast } from '@/hooks/useToast';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { listAgents, type AgentListItem } from '@/services/agent';
import { listChannelInstances, type ChannelInstance } from '@/services/channels';
import { listCronJobs, type CronJob } from '@/services/cron';
import {
  approveSharedContextWriteProposal,
  archiveSharedContext,
  createSharedContext,
  createSharedContextBinding,
  createSharedContextProposalFromHistory,
  createSharedContextWriteProposal,
  deleteSharedContextBinding,
  listSharedContextBindings,
  listSharedContexts,
  listSharedContextWriteProposals,
  rejectSharedContextWriteProposal,
  searchSharedContextHistory,
  updateSharedContext,
  updateSharedContextWriteProposal,
  type SharedContext,
  type SharedContextBinding,
  type SharedContextHistoryMessage,
  type SharedContextMemoryType,
  type SharedContextTargetType,
  type SharedContextWriteProposal,
} from '@/services/memorySharedContexts';

export interface TargetOption {
  type: SharedContextTargetType;
  id: string;
  label: string;
}

export const TARGET_TYPES: SharedContextTargetType[] = ['agent', 'channel', 'cron', 'conversation', 'task'];
export const SHARED_CONTEXT_MEMORY_TYPES: SharedContextMemoryType[] = ['semantic', 'episodic'];

export const formatSharedContextDate = (value?: string | null) => {
  if (!value) return '';
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

export function useSharedContextPanel() {
  const t = useTranslations('memory.sharedContexts');
  const tMemory = useTranslations('memory');
  const locale = useLocale();

  const [contexts, setContexts] = useState<SharedContext[]>([]);
  const [selectedContextId, setSelectedContextId] = useState('');
  const [bindings, setBindings] = useState<SharedContextBinding[]>([]);
  const [proposals, setProposals] = useState<SharedContextWriteProposal[]>([]);
  const [historyHits, setHistoryHits] = useState<SharedContextHistoryMessage[]>([]);
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [channels, setChannels] = useState<ChannelInstance[]>([]);
  const [cronJobs, setCronJobs] = useState<CronJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [targetType, setTargetType] = useState<SharedContextTargetType>('agent');
  const [targetId, setTargetId] = useState('');
  const [proposalType, setProposalType] = useState<SharedContextMemoryType>('semantic');
  const [proposalContent, setProposalContent] = useState('');
  const [editingProposalId, setEditingProposalId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [historyQuery, setHistoryQuery] = useState('');
  const [historyType, setHistoryType] = useState<SharedContextMemoryType>('semantic');

  const selectedContext = contexts.find((context) => context.id === selectedContextId) ?? null;
  const selectedContextIsActive = selectedContext?.status === 'active';
  const pendingProposals = proposals.filter((proposal) => proposal.status === 'pending');

  const targetOptions = useMemo<TargetOption[]>(() => {
    if (targetType === 'agent') {
      return agents.map((agent) => ({
        type: 'agent',
        id: agent.id,
        label: getBuiltinAgentName(agent.id, agent.name || agent.id, locale),
      }));
    }
    if (targetType === 'channel') {
      return channels.map((channel) => ({
        type: 'channel',
        id: channel.instanceId,
        label: channel.displayName || channel.channelName || channel.instanceId,
      }));
    }
    if (targetType === 'cron') {
      return cronJobs.map((job) => ({ type: 'cron', id: job.id, label: job.name || job.id }));
    }
    return [];
  }, [agents, channels, cronJobs, targetType, locale]);

  const loadContexts = useCallback(async () => {
    setLoading(true);
    try {
      const response = await listSharedContexts();
      setContexts(response.items);
      setSelectedContextId((current) => {
        if (current && response.items.some((context) => context.id === current)) return current;
        return response.items[0]?.id ?? '';
      });
    } catch (error) {
      toast({
        title: t('errors.loadContexts'),
        description: error instanceof Error ? error.message : tMemory('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [t, tMemory]);

  const loadTargetOptions = useCallback(async () => {
    const [agentResponse, channelResponse, cronResponse] = await Promise.allSettled([
      listAgents(1, 100),
      listChannelInstances(),
      listCronJobs({ limit: 100 }),
    ]);
    if (agentResponse.status === 'fulfilled') setAgents(agentResponse.value.items);
    if (channelResponse.status === 'fulfilled') setChannels(channelResponse.value);
    if (cronResponse.status === 'fulfilled') setCronJobs(cronResponse.value.items);
  }, []);

  const loadContextDetails = useCallback(
    async (contextId: string) => {
      if (!contextId) return;
      setDetailsLoading(true);
      try {
        const [bindingResponse, proposalResponse] = await Promise.all([
          listSharedContextBindings(contextId),
          listSharedContextWriteProposals(contextId, { limit: 100 }),
        ]);
        setBindings(bindingResponse.items);
        setProposals(proposalResponse.items);
      } catch (error) {
        toast({
          title: t('errors.loadDetails'),
          description: error instanceof Error ? error.message : tMemory('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setDetailsLoading(false);
      }
    },
    [t, tMemory],
  );

  useEffect(() => {
    void loadContexts();
    void loadTargetOptions();
  }, [loadContexts, loadTargetOptions]);

  useEffect(() => {
    if (selectedContextId) void loadContextDetails(selectedContextId);
  }, [selectedContextId, loadContextDetails]);

  const refreshSelected = useCallback(async () => {
    await loadContexts();
    if (selectedContextId) await loadContextDetails(selectedContextId);
  }, [loadContextDetails, loadContexts, selectedContextId]);

  const handleCreateContext = useCallback(async () => {
    const name = newName.trim();
    if (!name) return;
    setActionId('create-context');
    try {
      const context = await createSharedContext({ name, description: newDescription.trim() });
      setNewName('');
      setNewDescription('');
      setContexts((items) => [context, ...items]);
      setSelectedContextId(context.id);
      toast({ title: t('toasts.contextCreated') });
    } catch (error) {
      toast({
        title: t('errors.createContext'),
        description: error instanceof Error ? error.message : tMemory('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [newDescription, newName, t, tMemory]);

  const handleArchiveContext = useCallback(async () => {
    if (!selectedContext || selectedContext.status !== 'active') return;
    setActionId(`archive-${selectedContext.id}`);
    try {
      const archived = await archiveSharedContext(selectedContext.id);
      setContexts((items) => items.map((item) => (item.id === archived.id ? archived : item)));
      toast({ title: t('toasts.contextArchived') });
    } catch (error) {
      toast({
        title: t('errors.archiveContext'),
        description: error instanceof Error ? error.message : tMemory('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [selectedContext, t, tMemory]);

  const handleCreateBinding = useCallback(async () => {
    if (!selectedContextId || !selectedContextIsActive || !targetId.trim()) return;
    setActionId('create-binding');
    try {
      const binding = await createSharedContextBinding(selectedContextId, {
        target_type: targetType,
        target_id: targetId.trim(),
      });
      setBindings((items) => [binding, ...items.filter((item) => item.id !== binding.id)]);
      setTargetId('');
      toast({ title: t('toasts.bindingCreated') });
    } catch (error) {
      toast({
        title: t('errors.createBinding'),
        description: error instanceof Error ? error.message : tMemory('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [selectedContextId, selectedContextIsActive, targetId, targetType, t, tMemory]);

  const handleDeleteBinding = useCallback(
    async (binding: SharedContextBinding) => {
      setActionId(binding.id);
      try {
        await deleteSharedContextBinding(binding.context_id, binding.id);
        setBindings((items) => items.filter((item) => item.id !== binding.id));
        toast({ title: t('toasts.bindingDeleted') });
      } catch (error) {
        toast({
          title: t('errors.deleteBinding'),
          description: error instanceof Error ? error.message : tMemory('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [t, tMemory],
  );

  const handleCreateProposal = useCallback(async () => {
    if (!selectedContextId || !selectedContextIsActive || !proposalContent.trim()) return;
    setActionId('create-proposal');
    try {
      const proposal = await createSharedContextWriteProposal(selectedContextId, {
        memory_type: proposalType,
        content: proposalContent.trim(),
        source_type: 'manual',
      });
      setProposalContent('');
      setProposals((items) => [proposal, ...items]);
      toast({ title: t('toasts.proposalCreated') });
    } catch (error) {
      toast({
        title: t('errors.createProposal'),
        description: error instanceof Error ? error.message : tMemory('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [proposalContent, proposalType, selectedContextId, selectedContextIsActive, t, tMemory]);

  const updateProposalInState = useCallback((proposal: SharedContextWriteProposal) => {
    setProposals((items) => items.map((item) => (item.id === proposal.id ? proposal : item)));
  }, []);

  const handleApproveProposal = useCallback(
    async (proposalId: string) => {
      if (!selectedContextIsActive) return;
      setActionId(proposalId);
      try {
        updateProposalInState(await approveSharedContextWriteProposal(proposalId));
        toast({ title: t('toasts.proposalApproved') });
      } catch (error) {
        toast({
          title: t('errors.approveProposal'),
          description: error instanceof Error ? error.message : tMemory('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [selectedContextIsActive, t, tMemory, updateProposalInState],
  );

  const handleRejectProposal = useCallback(
    async (proposalId: string) => {
      setActionId(proposalId);
      try {
        updateProposalInState(await rejectSharedContextWriteProposal(proposalId));
        toast({ title: t('toasts.proposalRejected') });
      } catch (error) {
        toast({
          title: t('errors.rejectProposal'),
          description: error instanceof Error ? error.message : tMemory('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [t, tMemory, updateProposalInState],
  );

  const handleSaveProposal = useCallback(
    async (proposalId: string) => {
      if (!selectedContextIsActive || !editingContent.trim()) return;
      setActionId(proposalId);
      try {
        updateProposalInState(await updateSharedContextWriteProposal(proposalId, { content: editingContent.trim() }));
        setEditingProposalId(null);
        setEditingContent('');
        toast({ title: t('toasts.proposalUpdated') });
      } catch (error) {
        toast({
          title: t('errors.updateProposal'),
          description: error instanceof Error ? error.message : tMemory('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [editingContent, selectedContextIsActive, t, tMemory, updateProposalInState],
  );

  const handleSearchHistory = useCallback(async () => {
    if (!selectedContextId || !historyQuery.trim()) return;
    setActionId('history-search');
    try {
      const response = await searchSharedContextHistory(selectedContextId, {
        query: historyQuery.trim(),
        limit: 10,
      });
      setHistoryHits(response.items);
    } catch (error) {
      toast({
        title: t('errors.searchHistory'),
        description: error instanceof Error ? error.message : tMemory('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [historyQuery, selectedContextId, t, tMemory]);

  const handlePromoteHistory = useCallback(
    async (message: SharedContextHistoryMessage) => {
      if (!selectedContextId || !selectedContextIsActive) return;
      setActionId(message.message_id);
      try {
        const proposal = await createSharedContextProposalFromHistory(selectedContextId, {
          message_id: message.message_id,
          memory_type: historyType,
        });
        setProposals((items) => [proposal, ...items]);
        toast({ title: t('toasts.historyPromoted') });
      } catch (error) {
        toast({
          title: t('errors.promoteHistory'),
          description: error instanceof Error ? error.message : tMemory('unknownError'),
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [historyType, selectedContextId, selectedContextIsActive, t, tMemory],
  );

  const correctionAutoApprove = useMemo(() => {
    if (!selectedContext?.policy) return true;
    const value = selectedContext.policy.correction_auto_approve;
    return value !== false;
  }, [selectedContext]);

  const goalCompletionAutoApprove = useMemo(() => {
    if (!selectedContext?.policy) return true;
    const value = selectedContext.policy.goal_completion_auto_approve;
    return value !== false;
  }, [selectedContext]);

  const handleToggleCorrectionAutoApprove = useCallback(async () => {
    if (!selectedContextId || !selectedContextIsActive) return;
    setActionId('toggle-correction');
    try {
      const newPolicy = { ...selectedContext?.policy, correction_auto_approve: !correctionAutoApprove };
      const updated = await updateSharedContext(selectedContextId, { policy: newPolicy });
      setContexts((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      toast({ title: t('toasts.policyUpdated') });
    } catch (error) {
      toast({
        title: t('errors.updatePolicy'),
        description: error instanceof Error ? error.message : tMemory('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [correctionAutoApprove, selectedContext, selectedContextId, selectedContextIsActive, t, tMemory]);

  const handleToggleGoalCompletionAutoApprove = useCallback(async () => {
    if (!selectedContextId || !selectedContextIsActive) return;
    setActionId('toggle-goal-completion');
    try {
      const newPolicy = {
        ...selectedContext?.policy,
        goal_completion_auto_approve: !goalCompletionAutoApprove,
      };
      const updated = await updateSharedContext(selectedContextId, { policy: newPolicy });
      setContexts((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      toast({ title: t('toasts.policyUpdated') });
    } catch (error) {
      toast({
        title: t('errors.updatePolicy'),
        description: error instanceof Error ? error.message : tMemory('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [goalCompletionAutoApprove, selectedContext, selectedContextId, selectedContextIsActive, t, tMemory]);

  return {
    contexts,
    selectedContext,
    selectedContextIsActive,
    selectedContextId,
    setSelectedContextId,
    bindings,
    proposals,
    pendingProposals,
    historyHits,
    loading,
    detailsLoading,
    actionId,
    newName,
    setNewName,
    newDescription,
    setNewDescription,
    targetType,
    setTargetType,
    targetId,
    setTargetId,
    targetOptions,
    proposalType,
    setProposalType,
    proposalContent,
    setProposalContent,
    editingProposalId,
    setEditingProposalId,
    editingContent,
    setEditingContent,
    historyQuery,
    setHistoryQuery,
    historyType,
    setHistoryType,
    refreshSelected,
    handleCreateContext,
    handleArchiveContext,
    handleCreateBinding,
    handleDeleteBinding,
    handleCreateProposal,
    handleApproveProposal,
    handleRejectProposal,
    handleSaveProposal,
    handleSearchHistory,
    handlePromoteHistory,
    correctionAutoApprove,
    handleToggleCorrectionAutoApprove,
    goalCompletionAutoApprove,
    handleToggleGoalCompletionAutoApprove,
  };
}
