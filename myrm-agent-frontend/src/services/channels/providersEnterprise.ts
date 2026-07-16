import { createChannelCredentialService, type ChannelTestResult } from './core';

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

// ==================== GitHub ====================

export interface GitHubCredentials {
  personalAccessToken: string;
  webhookSecret: string;
}

const githubService = createChannelCredentialService<GitHubCredentials>(
  'githubCredentials',
  '/channels/manage/github/test',
);
export const getGitHubCredentials = githubService.get;
export const saveGitHubCredentials = githubService.save;
export async function testGitHubConnection(personalAccessToken: string): Promise<ChannelTestResult> {
  return githubService.test({ personalAccessToken });
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
  webhookUrl?: string;
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
