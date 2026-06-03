'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import type { ChannelOverrides } from './DmPolicySelector';
import type { ChannelActivityInfo } from './ChannelList';
import type {
  ChannelPairing,
  ChannelIssue,
  WhatsAppStatus,
  DmPolicy,
  GroupPolicy,
  GroupTriggerConfig,
  GroupInfo,
  ReactionLevel,
} from '@/services/channels';
import {
  listPairings,
  createPairing,
  deletePairing,
  updatePairingStatus,
  updatePairingDisplayName,
  getWhatsAppStatus,
  getChannelsConfig,
  saveChannelsConfig,
  listGroups,
  updateEnabledGroups,
  listChannelStatuses,
  toggleChannel,
} from '@/services/channels';

interface ChannelStatusEntry {
  name: string;
  status: string;
  connected: boolean;
  last_active_at: number | null;
  issues?: ChannelIssue[];
}

export function useChannelsState(t: (key: string, values?: Record<string, string | number>) => string) {
  const [pairings, setPairings] = useState<ChannelPairing[]>([]);
  const [pairingsLoading, setPairingsLoading] = useState(true);
  const [waStatus, setWaStatus] = useState<WhatsAppStatus | null>(null);
  const [waLoading, setWaLoading] = useState(true);
  const [dmPolicy, setDmPolicy] = useState<DmPolicy>('allowlist');
  const [groupPolicy, setGroupPolicy] = useState<GroupPolicy>('disabled');
  const [groupTrigger, setGroupTrigger] = useState<GroupTriggerConfig>({ mode: 'mention_only' });
  const [channelOverrides, setChannelOverrides] = useState<Record<string, ChannelOverrides>>({});
  const [policySaving, setPolicySaving] = useState(false);
  const [groups, setGroups] = useState<GroupInfo[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [groupsRefreshing, setGroupsRefreshing] = useState(false);
  const [channelStatuses, setChannelStatuses] = useState<Record<string, string>>({});
  const [channelActivities, setChannelActivities] = useState<Record<string, ChannelActivityInfo>>({});
  const [channelIssues, setChannelIssues] = useState<Record<string, ChannelIssue[]>>({});
  const [reactionLevel, setReactionLevel] = useState<ReactionLevel>('full');
  const [processingEmoji, setProcessingEmoji] = useState('👀');
  const [completionEmoji, setCompletionEmoji] = useState('✅');
  const [togglingChannel, setTogglingChannel] = useState<string | null>(null);
  // Free response (no mention required) whitelisted chats
  const [freeResponseChats, setFreeResponseChats] = useState<string[]>([]);

  // ─── Internal helpers ──────────────────────────────────────────────

  const updateChannelStatusMaps = useCallback((statuses: ChannelStatusEntry[]) => {
    const statusMap: Record<string, string> = {};
    const activityMap: Record<string, ChannelActivityInfo> = {};
    const issuesMap: Record<string, ChannelIssue[]> = {};
    for (const s of statuses) {
      statusMap[s.name] = s.status === 'running' && !s.connected ? 'running_idle' : s.status;
      activityMap[s.name] = { last_active_at: s.last_active_at };
      if (s.issues?.length) issuesMap[s.name] = s.issues;
    }
    setChannelStatuses(statusMap);
    setChannelActivities(activityMap);
    setChannelIssues(issuesMap);
  }, []);

  const clearChannelMaps = useCallback(() => {
    setChannelStatuses({});
    setChannelActivities({});
    setChannelIssues({});
  }, []);

  const fetchChannelStatuses = useCallback(() => {
    listChannelStatuses().then(updateChannelStatusMaps).catch(clearChannelMaps);
  }, [updateChannelStatusMaps, clearChannelMaps]);

  const refreshGroupsAndStatuses = useCallback(() => {
    setGroupsRefreshing(true);
    Promise.all([
      listGroups(true)
        .then(setGroups)
        .catch(() => setGroups([])),
      listChannelStatuses().then(updateChannelStatusMaps).catch(clearChannelMaps),
    ]).finally(() => setGroupsRefreshing(false));
  }, [updateChannelStatusMaps, clearChannelMaps]);

  const fetchWhatsAppStatus = useCallback((showLoading = false) => {
    if (showLoading) setWaLoading(true);
    getWhatsAppStatus()
      .then((next) => {
        setWaStatus((prev) => {
          if (!prev) return next;
          if (prev.connected !== next.connected) return next;
          if (Boolean(prev.qr_code) !== Boolean(next.qr_code)) return next;
          return prev;
        });
      })
      .catch(() => {
        setWaStatus((prev) => prev ?? { connected: false, status: 'unavailable', qr_code: null, phone_number: null });
      })
      .finally(() => setWaLoading(false));
  }, []);

  const fetchWhatsAppStatusRef = useRef(fetchWhatsAppStatus);
  fetchWhatsAppStatusRef.current = fetchWhatsAppStatus;

  // ─── Policy persistence ────────────────────────────────────────────

  const saveAllPolicies = useCallback(
    async (
      dm: DmPolicy,
      group: GroupPolicy,
      trigger: GroupTriggerConfig,
      overrides: Record<string, ChannelOverrides>,
      reactionOverrides?: {
        level?: ReactionLevel;
        processing?: string;
        completion?: string;
        freeResponseChats?: string[];
      },
    ) => {
      setPolicySaving(true);
      try {
        const channelsCfg: Record<string, { dmPolicy?: DmPolicy; groupPolicy?: GroupPolicy }> = {};
        for (const [ch, o] of Object.entries(overrides)) {
          if (o.dmPolicy || o.groupPolicy) channelsCfg[ch] = { ...o };
        }
        const hasOverrides = Object.keys(channelsCfg).length > 0;
        await saveChannelsConfig({
          dmPolicy: dm,
          groupPolicy: group,
          groupTrigger: trigger,
          selfChatEnabled: true,
          reactionLevel: reactionOverrides?.level ?? reactionLevel,
          processingEmoji: reactionOverrides?.processing ?? processingEmoji,
          completionEmoji: reactionOverrides?.completion ?? completionEmoji,
          freeResponseChats: reactionOverrides?.freeResponseChats ?? freeResponseChats,
          channels: hasOverrides ? channelsCfg : undefined,
        });
        toast.success(t('policySaved'));
      } catch {
        toast.error(t('policySaveError'));
      } finally {
        setPolicySaving(false);
      }
    },
    [t, reactionLevel, processingEmoji, completionEmoji, freeResponseChats],
  );

  // ─── Event handlers ────────────────────────────────────────────────

  const handleDmPolicyChange = useCallback(
    async (policy: DmPolicy) => {
      setDmPolicy(policy);
      await saveAllPolicies(policy, groupPolicy, groupTrigger, channelOverrides);
    },
    [channelOverrides, groupPolicy, groupTrigger, saveAllPolicies],
  );

  const handleGroupPolicyChange = useCallback(
    async (policy: GroupPolicy) => {
      setGroupPolicy(policy);
      await saveAllPolicies(dmPolicy, policy, groupTrigger, channelOverrides);
    },
    [channelOverrides, dmPolicy, groupTrigger, saveAllPolicies],
  );

  const handleGroupTriggerChange = useCallback(
    async (trigger: GroupTriggerConfig) => {
      setGroupTrigger(trigger);
      await saveAllPolicies(dmPolicy, groupPolicy, trigger, channelOverrides);
    },
    [channelOverrides, dmPolicy, groupPolicy, saveAllPolicies],
  );

  const handleChannelOverride = useCallback(
    async (channel: string, overrides: ChannelOverrides | undefined) => {
      const next = { ...channelOverrides };
      if (!overrides || (!overrides.dmPolicy && !overrides.groupPolicy)) {
        delete next[channel];
      } else {
        next[channel] = overrides;
      }
      setChannelOverrides(next);
      await saveAllPolicies(dmPolicy, groupPolicy, groupTrigger, next);
    },
    [channelOverrides, dmPolicy, groupPolicy, groupTrigger, saveAllPolicies],
  );

  const handleGroupToggle = useCallback(
    async (jid: string, enabled: boolean) => {
      const updated = groups.map((g) => (g.jid === jid ? { ...g, is_enabled: enabled } : g));
      setGroups(updated);
      const enabledJids = updated.filter((g) => g.is_enabled).map((g) => g.jid);
      try {
        await updateEnabledGroups(enabledJids);
        toast.success(t('groupsSaved'));
      } catch {
        toast.error(t('groupsSaveError'));
        setGroups(groups);
      }
    },
    [groups, t],
  );

  const handleFreeResponseToggle = useCallback(
    async (jid: string, enabled: boolean) => {
      const next = enabled
        ? [...freeResponseChats.filter((id) => id !== jid), jid]
        : freeResponseChats.filter((id) => id !== jid);
      setFreeResponseChats(next);
      await saveAllPolicies(dmPolicy, groupPolicy, groupTrigger, channelOverrides, {
        freeResponseChats: next,
      });
    },
    [freeResponseChats, dmPolicy, groupPolicy, groupTrigger, channelOverrides, saveAllPolicies],
  );

  const handleGroupsRefresh = useCallback(async () => {
    setGroupsRefreshing(true);
    try {
      const fresh = await listGroups(true);
      setGroups(fresh);
    } catch {
      toast.error(t('groupsRefreshError'));
    } finally {
      setGroupsRefreshing(false);
    }
  }, [t]);

  const handleReactionLevelChange = useCallback(
    async (level: ReactionLevel) => {
      setReactionLevel(level);
      await saveAllPolicies(dmPolicy, groupPolicy, groupTrigger, channelOverrides, { level });
    },
    [channelOverrides, dmPolicy, groupPolicy, groupTrigger, saveAllPolicies],
  );

  const handleProcessingEmojiChange = useCallback(
    async (emoji: string) => {
      setProcessingEmoji(emoji);
      await saveAllPolicies(dmPolicy, groupPolicy, groupTrigger, channelOverrides, {
        processing: emoji,
      });
    },
    [channelOverrides, dmPolicy, groupPolicy, groupTrigger, saveAllPolicies],
  );

  const handleCompletionEmojiChange = useCallback(
    async (emoji: string) => {
      setCompletionEmoji(emoji);
      await saveAllPolicies(dmPolicy, groupPolicy, groupTrigger, channelOverrides, {
        completion: emoji,
      });
    },
    [channelOverrides, dmPolicy, groupPolicy, groupTrigger, saveAllPolicies],
  );

  const handleAddPairing = useCallback(async (channel: string, senderId: string) => {
    const p = await createPairing({ channel, sender_id: senderId });
    setPairings((prev) => [p, ...prev]);
  }, []);

  const handleDeletePairing = useCallback(async (id: string) => {
    await deletePairing(id);
    setPairings((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const handleUpdatePairingStatus = useCallback(
    async (id: string, status: 'active' | 'blocked') => {
      try {
        const updated = await updatePairingStatus(id, status);
        setPairings((prev) => prev.map((p) => (p.id === id ? updated : p)));
        if (status === 'active') toast.dismiss('pairing-pending');
      } catch {
        toast.error(t('policySaveError'));
      }
    },
    [t],
  );

  const handleUpdatePairingDisplayName = useCallback(
    async (id: string, displayName: string) => {
      try {
        const updated = await updatePairingDisplayName(id, displayName);
        setPairings((prev) => prev.map((p) => (p.id === id ? updated : p)));
      } catch {
        toast.error(t('policySaveError'));
      }
    },
    [t],
  );

  const handleChannelToggle = useCallback(
    async (channelName: string, enabled: boolean) => {
      setTogglingChannel(channelName);
      try {
        const result = await toggleChannel(channelName, enabled);
        const mappedStatus = result.status === 'running' && !result.connected ? 'running_idle' : result.status;
        setChannelStatuses((prev) => ({ ...prev, [channelName]: mappedStatus }));
        toast.success(
          enabled
            ? t('channelEnableSuccess', { name: channelName })
            : t('channelDisableSuccess', { name: channelName }),
        );
        if (channelName === 'whatsapp') fetchWhatsAppStatus();
      } catch {
        toast.error(t('channelToggleError'));
      } finally {
        setTogglingChannel(null);
      }
    },
    [t, fetchWhatsAppStatus],
  );

  // ─── Effects ───────────────────────────────────────────────────────

  useEffect(() => {
    listPairings()
      .then(setPairings)
      .catch(() => setPairings([]))
      .finally(() => setPairingsLoading(false));

    fetchWhatsAppStatus(true);

    listGroups()
      .then(setGroups)
      .catch(() => setGroups([]))
      .finally(() => setGroupsLoading(false));

    fetchChannelStatuses();

    getChannelsConfig().then((cfg) => {
      if (cfg?.dmPolicy) setDmPolicy(cfg.dmPolicy);
      if (cfg?.groupPolicy) setGroupPolicy(cfg.groupPolicy);
      if (cfg?.groupTrigger) setGroupTrigger(cfg.groupTrigger);
      if (cfg?.reactionLevel) setReactionLevel(cfg.reactionLevel);
      if (cfg?.processingEmoji) setProcessingEmoji(cfg.processingEmoji);
      if (cfg?.completionEmoji) setCompletionEmoji(cfg.completionEmoji);
      if (cfg?.freeResponseChats) setFreeResponseChats(cfg.freeResponseChats);
      if (cfg?.channels) {
        const overrides: Record<string, ChannelOverrides> = {};
        for (const [ch, chCfg] of Object.entries(cfg.channels)) {
          const o: ChannelOverrides = {};
          if (chCfg?.dmPolicy) o.dmPolicy = chCfg.dmPolicy;
          if (chCfg?.groupPolicy) o.groupPolicy = chCfg.groupPolicy;
          if (o.dmPolicy || o.groupPolicy) overrides[ch] = o;
        }
        setChannelOverrides(overrides);
      }
    });
  }, [fetchWhatsAppStatus, fetchChannelStatuses]);

  useEffect(() => {
    if (!waStatus?.qr_code) return;
    const timer = setInterval(fetchWhatsAppStatus, 15_000);
    return () => clearInterval(timer);
  }, [waStatus?.connected, waStatus?.qr_code, fetchWhatsAppStatus]);

  useEffect(() => {
    const handleSseEvent = () => fetchChannelStatuses();
    window.addEventListener('channel-status-change', handleSseEvent);
    return () => {
      window.removeEventListener('channel-status-change', handleSseEvent);
    };
  }, [fetchChannelStatuses]);

  useEffect(() => {
    const hasPairingPolicy =
      dmPolicy === 'pairing' || Object.values(channelOverrides).some((o) => o.dmPolicy === 'pairing');
    if (!hasPairingPolicy) return;
    const timer = setInterval(() => {
      listPairings()
        .then(setPairings)
        .catch(() => setPairings([]));
    }, 15_000);
    return () => clearInterval(timer);
  }, [dmPolicy, channelOverrides]);

  useEffect(() => {
    const handleChannelStatusChange = (event: Event) => {
      const customEvent = event as CustomEvent<{
        channel: string;
        status: string;
        type: string;
      }>;
      const { channel, type } = customEvent.detail;

      if (type === 'channel_connected') {
        toast.success(t('channelConnectedRefreshing', { channels: channel }));
        refreshGroupsAndStatuses();
        if (channel === 'whatsapp') fetchWhatsAppStatusRef.current();
      } else if (type === 'channel_disconnected') {
        fetchChannelStatuses();
        if (channel === 'whatsapp') fetchWhatsAppStatusRef.current();
      }
    };

    const handleGroupsUpdated = () => {
      listGroups()
        .then(setGroups)
        .catch(() => setGroups([]));
    };

    const handlePairingsUpdated = () => {
      listPairings()
        .then(setPairings)
        .catch(() => setPairings([]));
    };

    let credsSavedTimer: ReturnType<typeof setTimeout> | null = null;
    const handleCredentialsSaved = () => {
      if (credsSavedTimer) clearTimeout(credsSavedTimer);
      credsSavedTimer = setTimeout(fetchChannelStatuses, 2000);
    };

    window.addEventListener('channel-status-change', handleChannelStatusChange);
    window.addEventListener('groups-updated', handleGroupsUpdated);
    window.addEventListener('pairings-updated', handlePairingsUpdated);
    window.addEventListener('channel-credentials-saved', handleCredentialsSaved);
    return () => {
      window.removeEventListener('channel-status-change', handleChannelStatusChange);
      window.removeEventListener('groups-updated', handleGroupsUpdated);
      window.removeEventListener('pairings-updated', handlePairingsUpdated);
      window.removeEventListener('channel-credentials-saved', handleCredentialsSaved);
      if (credsSavedTimer) clearTimeout(credsSavedTimer);
    };
  }, [t, refreshGroupsAndStatuses, fetchChannelStatuses]);

  return {
    pairings,
    pairingsLoading,
    waStatus,
    waLoading,
    fetchWhatsAppStatus,
    dmPolicy,
    groupPolicy,
    groupTrigger,
    channelOverrides,
    policySaving,
    groups,
    groupsLoading,
    groupsRefreshing,
    channelStatuses,
    channelActivities,
    channelIssues,
    reactionLevel,
    processingEmoji,
    completionEmoji,
    togglingChannel,
    freeResponseChats,
    handleDmPolicyChange,
    handleGroupPolicyChange,
    handleGroupTriggerChange,
    handleChannelOverride,
    handleGroupToggle,
    handleFreeResponseToggle,
    handleGroupsRefresh,
    handleReactionLevelChange,
    handleProcessingEmojiChange,
    handleCompletionEmojiChange,
    handleAddPairing,
    handleDeletePairing,
    handleUpdatePairingStatus,
    handleUpdatePairingDisplayName,
    handleChannelToggle,
  };
}
