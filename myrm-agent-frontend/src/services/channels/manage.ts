import { apiRequest } from '@/lib/api';

// ==================== Types ====================

export interface ChannelPairing {
  id: string;
  channel: string;
  sender_id: string;
  user_id: string;
  status: string;
  display_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreatePairingRequest {
  channel: string;
  sender_id: string;
}

// ==================== Channel Status ====================

export interface ChannelIssue {
  kind: string;
  severity: string;
  message: string;
  fix: string;
}

export interface ChannelStatus {
  name: string;
  status: string;
  connected: boolean;
  channelType: string;
  instanceId: string;
  displayName: string;
  last_inbound_at: number | null;
  last_outbound_at: number | null;
  last_active_at: number | null;
  issues: ChannelIssue[];
}

export async function listChannelStatuses(): Promise<ChannelStatus[]> {
  return apiRequest('/channels/manage/status');
}

export interface ChannelInstallDependenciesResult {
  ok: boolean;
  message: string;
  registered: boolean;
}

export async function installChannelDependencies(
  channelName: string,
): Promise<ChannelInstallDependenciesResult> {
  return apiRequest(`/channels/manage/${channelName}/install-dependencies`, {
    method: 'POST',
  });
}

// ── Channel Instances ──

export interface ChannelInstance {
  instanceId: string;
  channelType: string;
  channelName: string;
  displayName: string;
  status: string;
}

export async function listChannelInstances(channelType?: string): Promise<ChannelInstance[]> {
  const params = channelType ? `?channel_type=${channelType}` : '';
  return apiRequest(`/channels/manage/instances${params}`);
}

export async function createChannelInstance(
  channelType: string,
  displayName?: string,
  credentials?: Record<string, string>,
): Promise<ChannelInstance> {
  return apiRequest('/channels/manage/instances', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channelType, displayName: displayName ?? '', credentials }),
  });
}

export async function deleteChannelInstance(instanceId: string): Promise<void> {
  return apiRequest(`/channels/manage/instances/${instanceId}`, { method: 'DELETE' });
}

// ── Channel Display Name ──

export async function updateChannelDisplayName(channelName: string, displayName: string): Promise<ChannelInstance> {
  return apiRequest(`/channels/manage/${channelName}/display-name`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ displayName }),
  });
}

// ==================== API ====================

export async function listPairings(): Promise<ChannelPairing[]> {
  return apiRequest('/channels/manage/pairings');
}

export async function createPairing(data: CreatePairingRequest): Promise<ChannelPairing> {
  return apiRequest('/channels/manage/pairings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function deletePairing(id: string): Promise<void> {
  return apiRequest(`/channels/manage/pairings/${id}`, { method: 'DELETE' });
}

export async function updatePairingStatus(id: string, status: 'active' | 'blocked'): Promise<ChannelPairing> {
  return apiRequest(`/channels/manage/pairings/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
}

export async function updatePairingDisplayName(id: string, displayName: string): Promise<ChannelPairing> {
  return apiRequest(`/channels/manage/pairings/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName }),
  });
}

// ==================== Policies ====================

export type DmPolicy = 'disabled' | 'open' | 'allowlist' | 'pairing';
export type GroupPolicy = 'disabled' | 'open' | 'allowlist';
export type GroupTriggerMode = 'mention_only' | 'prefix' | 'all';

export interface GroupTriggerConfig {
  mode: GroupTriggerMode;
  prefixes?: string[];
}

export type ReactionLevel = 'off' | 'simple' | 'full';

export interface ChannelsConfig {
  dmPolicy: DmPolicy;
  groupPolicy?: GroupPolicy;
  groupTrigger?: GroupTriggerConfig;
  selfChatEnabled: boolean;
  reactionLevel?: ReactionLevel;
  processingEmoji?: string;
  completionEmoji?: string;
  failureEmoji?: string;
  freeResponseChats?: string[];
  channels?: Record<string, { dmPolicy?: DmPolicy; groupPolicy?: GroupPolicy; freeResponseChats?: string[] }>;
}

export async function getChannelsConfig(): Promise<ChannelsConfig | null> {
  try {
    const record = await apiRequest<{ value: ChannelsConfig }>('/config/channels');
    return record.value;
  } catch {
    return null;
  }
}

export async function saveChannelsConfig(config: ChannelsConfig): Promise<void> {
  await apiRequest('/config/channels', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: config, device_id: 'web' }),
  });
}

// ==================== Groups ====================

export interface GroupInfo {
  jid: string;
  name: string;
  channel: string;
  is_enabled: boolean;
}

export async function listGroups(forceRefresh: boolean = false): Promise<GroupInfo[]> {
  const params = forceRefresh ? '?force_refresh=true' : '';
  return apiRequest(`/channels/manage/groups${params}`);
}

export async function updateEnabledGroups(enabledGroups: string[]): Promise<void> {
  await apiRequest('/channels/manage/groups', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled_groups: enabledGroups }),
  });
}

export interface ChannelToggleResult {
  name: string;
  enabled: boolean;
  status: string;
  connected: boolean;
}

export async function toggleChannel(channelName: string, enabled: boolean): Promise<ChannelToggleResult> {
  return apiRequest(`/channels/manage/${channelName}/toggle`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
}

// ── Channel Routing ──

export type ThreadSharingMode = 'isolated' | 'shared';

export type ReplyMode = 'auto' | 'draft_review';
export type DraftTimeoutAction = 'auto_send' | 'auto_reject';

export interface TopicBinding {
  topicId: string;
  agentId: string | null;
  displayName: string | null;
  avatarUrl: string | null;
  threadSharingMode: ThreadSharingMode;
  replyMode: ReplyMode;
  draftTimeoutMinutes: number;
  draftTimeoutAction: DraftTimeoutAction;
}

export interface ChannelTopicsResponse {
  channel: string;
  globalAgentId: string | null;
  topics: TopicBinding[];
}

export async function getChannelTopics(channel: string): Promise<ChannelTopicsResponse> {
  return apiRequest(`/channels/manage/${channel}/topics`);
}

export async function bindTopicAgent(
  channel: string,
  topicId: string,
  agentId: string | null,
  threadSharingMode?: ThreadSharingMode,
  replyMode?: ReplyMode,
  draftTimeoutMinutes?: number,
  draftTimeoutAction?: DraftTimeoutAction,
): Promise<void> {
  return apiRequest(`/channels/manage/${channel}/topics/${encodeURIComponent(topicId)}/bind`, {
    method: 'POST',
    body: JSON.stringify({ agentId, threadSharingMode, replyMode, draftTimeoutMinutes, draftTimeoutAction }),
  });
}

export async function setChannelDefaultAgent(channel: string, agentId: string | null): Promise<void> {
  return apiRequest(`/channels/manage/${channel}/default-agent`, {
    method: 'POST',
    body: JSON.stringify({ agentId }),
  });
}
