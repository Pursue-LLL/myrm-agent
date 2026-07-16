import { apiRequest } from '@/lib/api';
import { isSandbox } from '@/lib/deploy-mode';
import { cpChannelRequest, createChannelCredentialService, type ChannelTestResult } from './core';

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
  signingSecret?: string;
  replyInThread: boolean;
}

const slackService = createChannelCredentialService<SlackCredentials>(
  'slackCredentials',
  '/channels/manage/slack/test',
);

export async function getSlackCredentials(): Promise<SlackCredentials | null> {
  if (isSandbox()) {
    try {
      const status = await cpChannelRequest<{ configured: string[] }>('/api/channels/credentials/status');
      if (!status.configured.includes('slack')) return null;
      return { botToken: '', appToken: '', signingSecret: '', replyInThread: true };
    } catch {
      return null;
    }
  }
  return slackService.get();
}

export async function saveSlackCredentials(creds: SlackCredentials): Promise<void> {
  if (isSandbox()) {
    if (!creds.signingSecret?.trim()) {
      throw new Error('Signing secret is required for SaaS Slack');
    }
    await cpChannelRequest('/api/channels/credentials/slack', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bot_token: creds.botToken,
        signing_secret: creds.signingSecret,
        app_token: creds.appToken,
        reply_in_thread: creds.replyInThread,
      }),
    });
    return;
  }
  await slackService.save(creds);
}
export async function testSlackConnection(botToken: string, appToken: string): Promise<ChannelTestResult> {
  return slackService.test({ botToken, appToken });
}

// ==================== Discord ====================

export interface DiscordCredentials {
  botToken: string;
  applicationId?: string;
  publicKey?: string;
  enableGateway?: boolean;
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

export async function getDiscordCredentials(): Promise<DiscordCredentials | null> {
  if (isSandbox()) {
    try {
      const status = await cpChannelRequest<{ configured: string[] }>('/api/channels/credentials/status');
      if (!status.configured.includes('discord')) return null;
      return { botToken: '', botPolicy: 'mention_only', enableGateway: true };
    } catch {
      return null;
    }
  }
  return discordService.get();
}

export async function saveDiscordCredentials(creds: DiscordCredentials): Promise<void> {
  if (isSandbox()) {
    if (!creds.applicationId?.trim() || !creds.publicKey?.trim()) {
      throw new Error('Application ID and public key are required for SaaS Discord');
    }
    await cpChannelRequest('/api/channels/credentials/discord', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bot_token: creds.botToken,
        application_id: creds.applicationId,
        public_key: creds.publicKey,
        enable_gateway: creds.enableGateway ?? true,
      }),
    });
    return;
  }
  await discordService.save(creds);
}
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

export async function getTelegramCredentials(): Promise<TelegramCredentials | null> {
  if (isSandbox()) {
    try {
      const status = await cpChannelRequest<{ configured: string[]; webhook_urls: Record<string, string> }>(
        '/api/channels/credentials/status',
      );
      if (!status.configured.includes('telegram')) return null;
      return {
        botToken: '',
        botPolicy: 'mention_only',
        webhookUrl: status.webhook_urls?.telegram,
      };
    } catch {
      return null;
    }
  }
  return telegramService.get();
}

export async function saveTelegramCredentials(creds: TelegramCredentials): Promise<void> {
  if (isSandbox()) {
    await cpChannelRequest('/api/channels/credentials/telegram', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_token: creds.botToken }),
    });
    return;
  }
  await telegramService.save(creds);
}
export async function testTelegramConnection(botToken: string): Promise<ChannelTestResult> {
  return telegramService.test({ botToken });
}
