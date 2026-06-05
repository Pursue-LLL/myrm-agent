import { apiRequest } from '@/lib/api';

// ==================== Channel Service Factory ====================

export interface ChannelTestResult {
  ok: boolean;
  message: string;
}

function createChannelCredentialService<T>(configKey: string, testEndpoint: string) {
  return {
    get: async (): Promise<T | null> => {
      try {
        const record = await apiRequest<{ value: T }>(`/config/${configKey}`);
        return record.value;
      } catch {
        return null;
      }
    },
    save: async (creds: T): Promise<void> => {
      await apiRequest(`/config/${configKey}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: creds, deviceId: 'web' }),
      });
    },
    test: async (params: Record<string, unknown>): Promise<ChannelTestResult> => {
      return apiRequest(testEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
    },
  };
}

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

// ==================== WhatsApp ====================

export interface WhatsAppStatus {
  connected: boolean;
  status: string;
  qr_code: string | null;
  phone_number: string | null;
}

export async function getWhatsAppStatus(): Promise<WhatsAppStatus> {
  return apiRequest('/channels/manage/whatsapp/status', { silent: true });
}

// ==================== WeChat ====================

export interface WeChatCredentials {
  botToken: string;
  ilinkBotId: string;
  baseUrl: string;
  ilinkUserId: string;
}

export interface WeChatStatus {
  connected: boolean;
  qr_code: string | null;
  bot_id: string | null;
  status: string;
  error?: string;
}

const wechatService = createChannelCredentialService<WeChatCredentials>(
  'wechatCredentials',
  '/channels/manage/wechat/test',
);
export const getWeChatCredentials = wechatService.get;
export const saveWeChatCredentials = wechatService.save;

export async function getWeChatStatus(channelName: string = 'wechat'): Promise<WeChatStatus> {
  if (channelName === 'wechat') {
    return apiRequest('/channels/manage/wechat/status');
  }
  return apiRequest(`/channels/manage/${channelName}/wechat-status`);
}

export async function triggerWeChatLogin(channelName: string = 'wechat'): Promise<{ status: string; bot_id?: string }> {
  if (channelName === 'wechat') {
    return apiRequest('/channels/manage/wechat/login', { method: 'POST', silent: true });
  }
  return apiRequest(`/channels/manage/${channelName}/wechat-login`, { method: 'POST', silent: true });
}

export async function logoutWeChatChannel(channelName: string = 'wechat'): Promise<{ status: string }> {
  return apiRequest(`/channels/manage/${channelName}/wechat-logout`, { method: 'POST', silent: true });
}

// ==================== Feishu ====================

export interface FeishuCredentials {
  appId: string;
  appSecret: string;
  botOpenId: string;
  verificationToken: string;
  encryptKey: string;
  useLark: boolean;
  renderMode: 'auto' | 'raw' | 'card';
  transport: 'webhook' | 'websocket';
  botPolicy: 'deny' | 'mention_only' | 'allow';
}

const feishuService = createChannelCredentialService<FeishuCredentials>(
  'feishuCredentials',
  '/channels/manage/feishu/test',
);
export const getFeishuCredentials = feishuService.get;
export const saveFeishuCredentials = feishuService.save;
export async function testFeishuConnection(
  appId: string,
  appSecret: string,
  useLark: boolean = false,
): Promise<ChannelTestResult> {
  return feishuService.test({ appId, appSecret, useLark });
}

// ==================== DingTalk ====================

export interface DingTalkCredentials {
  clientId: string;
  clientSecret: string;
  cardTemplateId?: string;
}

const dingtalkService = createChannelCredentialService<DingTalkCredentials>(
  'dingtalkCredentials',
  '/channels/manage/dingtalk/test',
);
export const getDingTalkCredentials = dingtalkService.get;
export const saveDingTalkCredentials = dingtalkService.save;
export async function testDingTalkConnection(clientId: string, clientSecret: string): Promise<ChannelTestResult> {
  return dingtalkService.test({ clientId, clientSecret });
}

// ==================== Slack ====================

export interface SlackCredentials {
  botToken: string;
  appToken: string;
  replyInThread: boolean;
}

const slackService = createChannelCredentialService<SlackCredentials>(
  'slackCredentials',
  '/channels/manage/slack/test',
);
export const getSlackCredentials = slackService.get;
export const saveSlackCredentials = slackService.save;
export async function testSlackConnection(botToken: string, appToken: string): Promise<ChannelTestResult> {
  return slackService.test({ botToken, appToken });
}

// ==================== Discord ====================

export interface DiscordCredentials {
  botToken: string;
  botPolicy: 'deny' | 'mention_only' | 'allow';
  autoThread?: boolean;
  noThreadChannels?: string;
  voiceEnabled?: boolean;
  voiceBargeInEnabled?: boolean;
  voiceWakeWords?: string;
  voiceTimeout?: number;
  voiceAutoJoinChannel?: string;
  voiceTextChannel?: string;
  voiceFollowUsers?: string;
  voiceAllowedChannels?: string;
}

const discordService = createChannelCredentialService<DiscordCredentials>(
  'discordCredentials',
  '/channels/manage/discord/test',
);
export const getDiscordCredentials = discordService.get;
export const saveDiscordCredentials = discordService.save;
export async function testDiscordConnection(botToken: string): Promise<ChannelTestResult> {
  return discordService.test({ botToken });
}

// ==================== WeCom ====================

export interface WeComCredentials {
  corpId: string;
  corpSecret: string;
  agentId: string;
  token: string;
  encodingAesKey: string;
}

const wecomService = createChannelCredentialService<WeComCredentials>(
  'wecomCredentials',
  '/channels/manage/wecom/test',
);
export const getWeComCredentials = wecomService.get;
export const saveWeComCredentials = wecomService.save;
export async function testWeComConnection(corpId: string, corpSecret: string): Promise<ChannelTestResult> {
  return wecomService.test({ corpId, corpSecret });
}

// ==================== WeCom AI Bot ====================

export interface WeComAiBotCredentials {
  botId: string;
  secret: string;
}

const wecomAibotService = createChannelCredentialService<WeComAiBotCredentials>(
  'wecomAibotCredentials',
  '/channels/manage/wecom_aibot/test',
);
export const getWeComAiBotCredentials = wecomAibotService.get;
export const saveWeComAiBotCredentials = wecomAibotService.save;
export async function testWeComAiBotConnection(botId: string, secret: string): Promise<ChannelTestResult> {
  return wecomAibotService.test({ botId, secret });
}

// ==================== MS Teams ====================

export interface TeamsCredentials {
  appId: string;
  appPassword: string;
  tenantId: string;
  welcomeText: string;
  promptStarters: string;
}

const teamsService = createChannelCredentialService<TeamsCredentials>(
  'teamsCredentials',
  '/channels/manage/teams/test',
);
export const getTeamsCredentials = teamsService.get;
export const saveTeamsCredentials = teamsService.save;
export async function testTeamsConnection(
  appId: string,
  appPassword: string,
  tenantId: string,
): Promise<ChannelTestResult> {
  return teamsService.test({ appId, appPassword, tenantId });
}

// ==================== Matrix ====================

export interface MatrixCredentials {
  homeserverUrl: string;
  accessToken: string;
  deviceId: string;
  userId: string;
  password: string;
  encryption: boolean;
  proxy: string;
}

const matrixService = createChannelCredentialService<MatrixCredentials>(
  'matrixCredentials',
  '/channels/manage/matrix/test',
);
export const getMatrixCredentials = matrixService.get;
export const saveMatrixCredentials = matrixService.save;
export async function testMatrixConnection(homeserverUrl: string, accessToken: string): Promise<ChannelTestResult> {
  return matrixService.test({ homeserverUrl, accessToken });
}

// ==================== Telegram ====================

export interface BotCommand {
  command: string;
  description: string;
}

export interface TelegramCredentials {
  botToken: string;
  commands?: BotCommand[];
  webhookUrl?: string;
  botPolicy: 'deny' | 'mention_only' | 'allow';
  autoTopic?: boolean;
  notificationsMode?: 'important' | 'all';
  guestMode?: boolean;
}

const telegramService = createChannelCredentialService<TelegramCredentials>(
  'telegramCredentials',
  '/channels/manage/telegram/test',
);
export const getTelegramCredentials = telegramService.get;
export const saveTelegramCredentials = telegramService.save;
export async function testTelegramConnection(botToken: string): Promise<ChannelTestResult> {
  return telegramService.test({ botToken });
}

// ==================== OneBot ====================

export interface OneBotCredentials {
  host: string;
  port: string;
  accessToken: string;
}

const onebotService = createChannelCredentialService<OneBotCredentials>(
  'onebotCredentials',
  '/channels/manage/onebot/test',
);
export const getOneBotCredentials = onebotService.get;
export const saveOneBotCredentials = onebotService.save;
export async function testOneBotConnection(
  host: string,
  port: string,
  accessToken: string,
): Promise<ChannelTestResult> {
  return onebotService.test({ host, port, accessToken });
}

// ==================== Google Chat ====================

export interface GoogleChatCredentials {
  serviceAccountJson: string;
}

const googlechatService = createChannelCredentialService<GoogleChatCredentials>(
  'googlechatCredentials',
  '/channels/manage/googlechat/test',
);
export const getGoogleChatCredentials = googlechatService.get;
export const saveGoogleChatCredentials = googlechatService.save;
export async function testGoogleChatConnection(serviceAccountJson: string): Promise<ChannelTestResult> {
  return googlechatService.test({ serviceAccountJson });
}

// ==================== QQ ====================

export interface QQCredentials {
  appId: string;
  clientSecret: string;
}

const qqService = createChannelCredentialService<QQCredentials>('qqCredentials', '/channels/manage/qq/test');
export const getQQCredentials = qqService.get;
export const saveQQCredentials = qqService.save;
export async function testQQConnection(appId: string, clientSecret: string): Promise<ChannelTestResult> {
  return qqService.test({ appId, clientSecret });
}

// ==================== Email ====================

export interface EmailCredentials {
  imapHost: string;
  imapPort: number;
  smtpHost: string;
  smtpPort: number;
  username: string;
  password: string;
}

const emailService = createChannelCredentialService<EmailCredentials>(
  'emailCredentials',
  '/channels/manage/email/test',
);
export const getEmailCredentials = emailService.get;
export const saveEmailCredentials = emailService.save;
export async function testEmailConnection(
  imapHost: string,
  imapPort: number,
  username: string,
  password: string,
): Promise<ChannelTestResult> {
  return emailService.test({ imapHost, imapPort, username, password });
}

// ==================== Voice/Twilio ====================

export interface VoiceCredentials {
  accountSid: string;
  authToken: string;
}

const voiceService = createChannelCredentialService<VoiceCredentials>(
  'voiceCredentials',
  '/channels/manage/voice/test',
);
export const getVoiceCredentials = voiceService.get;
export const saveVoiceCredentials = voiceService.save;
export async function testVoiceConnection(accountSid: string, authToken: string): Promise<ChannelTestResult> {
  return voiceService.test({ accountSid, authToken });
}

// ==================== SMS/Twilio ====================

export interface SMSCredentials {
  accountSid: string;
  authToken: string;
  phoneNumber: string;
}

const smsService = createChannelCredentialService<SMSCredentials>('smsCredentials', '/channels/manage/sms/test');
export const getSMSCredentials = smsService.get;
export const saveSMSCredentials = smsService.save;
export async function testSMSConnection(
  accountSid: string,
  authToken: string,
  phoneNumber: string,
): Promise<ChannelTestResult> {
  return smsService.test({ accountSid, authToken, phoneNumber });
}

// ==================== Signal ====================

export interface SignalCredentials {
  apiUrl: string;
  phoneNumber: string;
}

const signalService = createChannelCredentialService<SignalCredentials>(
  'signalCredentials',
  '/channels/manage/signal/test',
);
export const getSignalCredentials = signalService.get;
export const saveSignalCredentials = signalService.save;
export async function testSignalConnection(apiUrl: string, phoneNumber: string): Promise<ChannelTestResult> {
  return signalService.test({ apiUrl, phoneNumber });
}

// ==================== LINE ====================

export interface LINECredentials {
  channelAccessToken: string;
  channelSecret: string;
}

const lineService = createChannelCredentialService<LINECredentials>('lineCredentials', '/channels/manage/line/test');
export const getLINECredentials = lineService.get;
export const saveLINECredentials = lineService.save;
export async function testLINEConnection(channelAccessToken: string): Promise<ChannelTestResult> {
  return lineService.test({ channelAccessToken });
}

// ==================== iMessage ====================

export interface IMessageCredentials {
  apiUrl: string;
  password: string;
}

const imessageService = createChannelCredentialService<IMessageCredentials>(
  'imessageCredentials',
  '/channels/manage/imessage/test',
);
export const getIMessageCredentials = imessageService.get;
export const saveIMessageCredentials = imessageService.save;
export async function testIMessageConnection(apiUrl: string, password: string): Promise<ChannelTestResult> {
  return imessageService.test({ apiUrl, password });
}

// ==================== IRC ====================

export interface IRCCredentials {
  server: string;
  port: number;
  nick: string;
  channels: string;
  password: string;
  useSsl: boolean;
}

const ircService = createChannelCredentialService<IRCCredentials>('ircCredentials', '/channels/manage/irc/test');
export const getIRCCredentials = ircService.get;
export const saveIRCCredentials = ircService.save;
export async function testIRCConnection(server: string, port: number, nick: string): Promise<ChannelTestResult> {
  return ircService.test({ server, port, nick });
}

// ==================== Zalo ====================

export interface ZaloCredentials {
  accessToken: string;
}

const zaloService = createChannelCredentialService<ZaloCredentials>('zaloCredentials', '/channels/manage/zalo/test');
export const getZaloCredentials = zaloService.get;
export const saveZaloCredentials = zaloService.save;
export async function testZaloConnection(accessToken: string): Promise<ChannelTestResult> {
  return zaloService.test({ accessToken });
}

// ==================== Mattermost ====================

export interface MattermostCredentials {
  serverUrl: string;
  accessToken: string;
}

const mattermostService = createChannelCredentialService<MattermostCredentials>(
  'mattermostCredentials',
  '/channels/manage/mattermost/test',
);
export const getMattermostCredentials = mattermostService.get;
export const saveMattermostCredentials = mattermostService.save;
export async function testMattermostConnection(serverUrl: string, accessToken: string): Promise<ChannelTestResult> {
  return mattermostService.test({ serverUrl, accessToken });
}

// ==================== Async Login Protocol ====================

import type { StartLoginResponse, LoginEvent } from '@/types/channels';

/**
 * Start async login flow
 */
export async function startLogin(channelId: string, method: string): Promise<StartLoginResponse> {
  return apiRequest(`/channels/${channelId}/login/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method }),
    silent: true,
  });
}

/**
 * Subscribe to login state SSE stream
 *
 * @returns EventSource for real-time updates
 */
export function subscribeLoginStream(
  sessionId: string,
  onEvent: (event: LoginEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080/api/v1';
  const url = `${apiBase}/channels/login/${sessionId}/stream`;
  const eventSource = new EventSource(url);

  eventSource.addEventListener('login_state', (e: MessageEvent) => {
    try {
      const event: LoginEvent = JSON.parse(e.data);
      onEvent(event);
    } catch (err) {
      console.error('Failed to parse login event:', err);
    }
  });

  if (onError) {
    eventSource.onerror = onError;
  }

  return eventSource;
}

/**
 * Cancel ongoing login flow
 */
export async function cancelLogin(sessionId: string): Promise<void> {
  return apiRequest(`/channels/login/${sessionId}`, {
    method: 'DELETE',
  });
}

// ── Channel Routing ──

export type ThreadSharingMode = 'isolated' | 'shared';

export interface TopicBinding {
  topicId: string;
  agentId: string | null;
  displayName: string | null;
  avatarUrl: string | null;
  threadSharingMode: ThreadSharingMode;
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
): Promise<void> {
  return apiRequest(`/channels/manage/${channel}/topics/${encodeURIComponent(topicId)}/bind`, {
    method: 'POST',
    body: JSON.stringify({ agentId, threadSharingMode }),
  });
}

export async function setChannelDefaultAgent(channel: string, agentId: string | null): Promise<void> {
  return apiRequest(`/channels/manage/${channel}/default-agent`, {
    method: 'POST',
    body: JSON.stringify({ agentId }),
  });
}
