'use client';

/**
 * [INPUT] ./*ConfigCard / ./WhatsAppCard (POS: 各渠道的配置卡片，按需动态加载), ../../../common/SettingsSkeleton::CardSkeleton (POS: 加载占位)
 * [OUTPUT] ChannelConfigPanel: 按渠道 id 选出对应的配置卡片（WhatsApp 与微信卡片需要父级传入连接状态与跳转回调）
 * [POS] 渠道设置页右侧的配置面板，所有渠道卡片都在这里 dynamic import，避免首屏加载整组渠道代码。
 */

import dynamic from 'next/dynamic';
import type { WhatsAppCardProps } from './WhatsAppCard';
import { CardSkeleton } from '../../../common/SettingsSkeleton';

// 动态加载渠道卡片
const WhatsAppCard = dynamic(() => import('./WhatsAppCard').then((mod) => mod.WhatsAppCard), {
  loading: () => <CardSkeleton />,
});
const WeChatConfigCard = dynamic(() => import('./WeChatConfigCard').then((mod) => mod.WeChatConfigCard), {
  loading: () => <CardSkeleton />,
});
const FeishuConfigCard = dynamic(() => import('./FeishuConfigCard').then((mod) => mod.FeishuConfigCard), {
  loading: () => <CardSkeleton />,
});
const DingTalkConfigCard = dynamic(() => import('./DingTalkConfigCard').then((mod) => mod.DingTalkConfigCard), {
  loading: () => <CardSkeleton />,
});
const SlackConfigCard = dynamic(() => import('./SlackConfigCard').then((mod) => mod.SlackConfigCard), {
  loading: () => <CardSkeleton />,
});
const DiscordConfigCard = dynamic(() => import('./DiscordConfigCard').then((mod) => mod.DiscordConfigCard), {
  loading: () => <CardSkeleton />,
});
const WeComConfigCard = dynamic(() => import('./WeComConfigCard').then((mod) => mod.WeComConfigCard), {
  loading: () => <CardSkeleton />,
});
const WeComAiBotConfigCard = dynamic(() => import('./WeComAiBotConfigCard').then((mod) => mod.WeComAiBotConfigCard), {
  loading: () => <CardSkeleton />,
});
const WeChatOfficialConfigCard = dynamic(
  () => import('./WeChatOfficialConfigCard').then((mod) => mod.WeChatOfficialConfigCard),
  { loading: () => <CardSkeleton /> },
);
const TeamsConfigCard = dynamic(() => import('./TeamsConfigCard').then((mod) => mod.TeamsConfigCard), {
  loading: () => <CardSkeleton />,
});
const MatrixConfigCard = dynamic(() => import('./MatrixConfigCard').then((mod) => mod.MatrixConfigCard), {
  loading: () => <CardSkeleton />,
});
const TelegramConfigCard = dynamic(() => import('./TelegramConfigCard').then((mod) => mod.TelegramConfigCard), {
  loading: () => <CardSkeleton />,
});
const GoogleChatConfigCard = dynamic(() => import('./GoogleChatConfigCard').then((mod) => mod.GoogleChatConfigCard), {
  loading: () => <CardSkeleton />,
});
const QQConfigCard = dynamic(() => import('./QQConfigCard').then((mod) => mod.QQConfigCard), {
  loading: () => <CardSkeleton />,
});
const OneBotConfigCard = dynamic(() => import('./OneBotConfigCard').then((mod) => mod.OneBotConfigCard), {
  loading: () => <CardSkeleton />,
});
const EmailConfigCard = dynamic(() => import('./EmailConfigCard').then((mod) => mod.EmailConfigCard), {
  loading: () => <CardSkeleton />,
});
const VoiceConfigCard = dynamic(() => import('./VoiceConfigCard').then((mod) => mod.VoiceConfigCard), {
  loading: () => <CardSkeleton />,
});
const SMSConfigCard = dynamic(() => import('./SMSConfigCard').then((mod) => mod.SMSConfigCard), {
  loading: () => <CardSkeleton />,
});
const GitHubConfigCard = dynamic(() => import('./GitHubConfigCard').then((mod) => mod.GitHubConfigCard), {
  loading: () => <CardSkeleton />,
});
const SignalConfigCard = dynamic(() => import('./SignalConfigCard').then((mod) => mod.SignalConfigCard), {
  loading: () => <CardSkeleton />,
});
const LINEConfigCard = dynamic(() => import('./LINEConfigCard').then((mod) => mod.LINEConfigCard), {
  loading: () => <CardSkeleton />,
});
const IMessageConfigCard = dynamic(() => import('./IMessageConfigCard').then((mod) => mod.IMessageConfigCard), {
  loading: () => <CardSkeleton />,
});
const IRCConfigCard = dynamic(() => import('./IRCConfigCard').then((mod) => mod.IRCConfigCard), {
  loading: () => <CardSkeleton />,
});
const ZaloConfigCard = dynamic(() => import('./ZaloConfigCard').then((mod) => mod.ZaloConfigCard), {
  loading: () => <CardSkeleton />,
});
const MattermostConfigCard = dynamic(() => import('./MattermostConfigCard').then((mod) => mod.MattermostConfigCard), {
  loading: () => <CardSkeleton />,
});

// ─── Channel config renderer ─────────────────────────────────────────

export function ChannelConfigPanel({
  channel,
  waStatus,
  waLoading,
  onRefreshWa,
  onSelectChannel,
  t,
}: {
  channel: string;
  waStatus: WhatsAppCardProps['waStatus'];
  waLoading: boolean;
  onRefreshWa: () => void;
  onSelectChannel?: (channel: string) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  switch (channel) {
    case 'whatsapp':
      return <WhatsAppCard waStatus={waStatus} loading={waLoading} onRefresh={onRefreshWa} t={t} />;
    case 'wechat':
      return <WeChatConfigCard onNavigateToWeCom={() => onSelectChannel?.('wecom')} />;
    case 'wechat_official':
      return <WeChatOfficialConfigCard />;
    case 'feishu':
      return <FeishuConfigCard />;
    case 'dingtalk':
      return <DingTalkConfigCard />;
    case 'slack':
      return <SlackConfigCard />;
    case 'discord':
      return <DiscordConfigCard />;
    case 'wecom':
      return <WeComConfigCard />;
    case 'wecom_aibot':
      return <WeComAiBotConfigCard />;
    case 'teams':
      return <TeamsConfigCard />;
    case 'matrix':
      return <MatrixConfigCard />;
    case 'telegram':
      return <TelegramConfigCard />;
    case 'googlechat':
      return <GoogleChatConfigCard />;
    case 'qq':
      return <QQConfigCard />;
    case 'onebot':
      return <OneBotConfigCard />;
    case 'email':
      return <EmailConfigCard />;
    case 'voice':
      return <VoiceConfigCard />;
    case 'sms':
      return <SMSConfigCard />;
    case 'github':
      return <GitHubConfigCard />;
    case 'signal':
      return <SignalConfigCard />;
    case 'line':
      return <LINEConfigCard />;
    case 'imessage':
      return <IMessageConfigCard />;
    case 'irc':
      return <IRCConfigCard />;
    case 'zalo':
      return <ZaloConfigCard />;
    case 'mattermost':
      return <MattermostConfigCard />;
    default:
      return null;
  }
}
