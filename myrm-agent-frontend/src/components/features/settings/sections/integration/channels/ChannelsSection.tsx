'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type SetStateAction } from 'react';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';
import { IconAlertTriangle, IconXCircle, IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { Navigation } from 'lucide-react';
import SettingsSection from '../../SettingsSection';
import { PolicySelector } from './DmPolicySelector';
import { ChannelPolicyOverride } from './ChannelPolicyOverride';
import { GroupManager, CHANNELS_WITH_GROUPS } from './GroupManager';
import ChannelList, { buildChannelEntries } from './ChannelList';
import { useChannelsState } from './useChannelsState';
import { installChannelDependencies, type ChannelIssue } from '@/services/channels';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import type { WhatsAppCardProps } from './WhatsAppCard';
import { Switch } from '@/components/primitives/switch';
import { isSandbox } from '@/lib/deploy-mode';
import { CardSkeleton } from '../../../common/SettingsSkeleton';
import { useIngressRequirement } from '@/hooks/useIngressRequirement';
import { ChannelIngressBadge } from './ChannelIngressBadge';

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

// ─── Sub-components ──────────────────────────────────────────────────

const SEVERITY_STYLES: Record<string, { bg: string; border: string; icon: typeof IconXCircle }> = {
  error: { bg: 'bg-destructive/10', border: 'border-destructive/30', icon: IconXCircle },
  warning: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', icon: IconAlertTriangle },
  info: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', icon: IconAlertCircle },
};

type IssuePattern = [pattern: RegExp, key: string, prefixOnly?: boolean];

const ISSUE_MESSAGE_PATTERNS: IssuePattern[] = [
  [/not configured/i, 'notConfigured'],
  [/missing (configuration|credentials)/i, 'missingCredentials'],
  [/authentication failed/i, 'authFailed'],
  [/degraded (state|mode)/i, 'degradedMode'],
  [/(error state|in ERROR)/i, 'errorState'],
  [/must use HTTPS/i, 'webhookHttps'],
  [/webhook.*(setup|set up) failed/i, 'webhookFailed'],
  [/SDK.*not installed/i, 'sdkNotInstalled'],
  [/mautrix not installed/i, 'msgMautrixMissing'],
  [/lark-oapi not installed/i, 'msgLarkMissing'],
  [/Run: uv sync/i, 'msgUvSyncRequired'],
  [/token.*failed/i, 'tokenFailed'],
  [/connection failed/i, 'connectionFailed'],
  [/encryption not configured/i, 'encryptionNotConfigured'],
  [/not logged in/i, 'notLoggedIn'],
  [/^last error:\s*/i, 'lastError', true],
];

const ISSUE_FIX_PATTERNS: IssuePattern[] = [
  [/configure in settings/i, 'fixConfigureInSettings'],
  [/verify.*valid.*permissions/i, 'fixCheckCredentials'],
  [/verify.*(token|password|secret)/i, 'fixVerifyToken'],
  [/scan QR code to login/i, 'fixScanQrCode'],
];

function useIssueTranslator() {
  const t = useTranslations('channels.issues');
  return useCallback(
    (text: string, patterns: IssuePattern[]) => {
      for (const [pattern, key, prefixOnly] of patterns) {
        if (!pattern.test(text)) continue;
        if (prefixOnly) return `${t(key)} ${text.replace(pattern, '').trim()}`;
        return t(key);
      }
      return text;
    },
    [t],
  );
}

const UV_INSTALL_COMMAND = /^uv sync\b/;

function ChannelIssueFix({
  fix,
  channelName,
  onInstalled,
}: {
  fix: string;
  channelName: string;
  onInstalled: () => void;
}) {
  const t = useTranslations('channels.issues');
  const translate = useIssueTranslator();
  const [copied, setCopied] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current !== null) {
        clearTimeout(copiedTimerRef.current);
      }
    };
  }, []);

  const handleCopy = useCallback(async () => {
    const ok = await writeToClipboard(fix, true);
    if (ok) {
      setCopied(true);
      if (copiedTimerRef.current !== null) {
        clearTimeout(copiedTimerRef.current);
      }
      copiedTimerRef.current = setTimeout(() => setCopied(false), 2000);
    }
  }, [fix]);

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    setInstallError(null);
    try {
      const result = await installChannelDependencies(channelName);
      if (!result.registered) {
        setInstallError(result.message || t('installDependenciesRegisterFailed'));
        return;
      }
      onInstalled();
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : t('installDependenciesFailed'));
    } finally {
      setInstalling(false);
    }
  }, [channelName, onInstalled, t]);

  if (UV_INSTALL_COMMAND.test(fix)) {
    return (
      <div className="mt-1.5 space-y-1.5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <button
            type="button"
            onClick={() => void handleInstall()}
            disabled={installing}
            className="shrink-0 rounded-lg border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs font-medium hover:bg-primary/20 disabled:opacity-60"
          >
            {installing ? t('installingDependencies') : t('installDependencies')}
          </button>
          <button
            type="button"
            onClick={() => void handleCopy()}
            className="shrink-0 rounded-lg border px-3 py-1.5 text-xs hover:bg-accent"
          >
            {copied ? t('copiedInstallCommand') : t('copyInstallCommand')}
          </button>
        </div>
        {installError ? (
          <p className="text-destructive text-xs">{installError}</p>
        ) : null}
        <p className="text-muted-foreground text-xs">{t('fixRunUvSync')}</p>
        <code className="block min-w-0 break-all rounded-md border border-border/60 bg-background/80 px-2 py-1.5 font-mono text-xs">
          {fix}
        </code>
      </div>
    );
  }

  return (
    <p className="mt-0.5 text-muted-foreground text-xs">{translate(fix, ISSUE_FIX_PATTERNS)}</p>
  );
}

function ChannelIssueBanner({
  issues,
  channelName,
  onInstalled,
}: {
  issues: ChannelIssue[];
  channelName: string;
  onInstalled: () => void;
}) {
  const translate = useIssueTranslator();
  if (!issues.length) return null;
  return (
    <div className="space-y-2">
      {issues.map((issue, i) => {
        const style = SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.info;
        const Icon = style.icon;
        return (
          <div
            key={`${issue.kind}-${i}`}
            className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 ${style.bg} ${style.border}`}
          >
            <Icon className="h-4 w-4 mt-0.5 shrink-0 text-current opacity-70" />
            <div className="min-w-0 flex-1 text-sm">
              <span className="font-medium">{translate(issue.message, ISSUE_MESSAGE_PATTERNS)}</span>
              {issue.fix ? (
                <ChannelIssueFix fix={issue.fix} channelName={channelName} onInstalled={onInstalled} />
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Channel auth-type classification ────────────────────────────────

const QR_LOGIN_CHANNELS = new Set(['whatsapp', 'wechat']);
const CONNECTION_CONFIG_CHANNELS = new Set(['onebot', 'irc']);

function getChannelNotConfiguredKey(channel: string): string {
  if (QR_LOGIN_CHANNELS.has(channel)) return 'channelNotConfiguredQr';
  if (CONNECTION_CONFIG_CHANNELS.has(channel)) return 'channelNotConfiguredConnection';
  return 'channelNotConfigured';
}

// ─── Credential guide ────────────────────────────────────────────────

const CHANNELS_WITH_GUIDE = new Set([
  'telegram',
  'feishu',
  'dingtalk',
  'slack',
  'discord',
  'wecom',
  'wecom_aibot',
  'teams',
  'matrix',
  'googlechat',
  'qq',
  'email',
  'signal',
  'line',
  'mattermost',
  'github',
]);

const DEVELOPER_PORTAL_URLS: Record<string, string> = {
  telegram: 'https://t.me/BotFather',
  feishu: 'https://open.feishu.cn/app',
  dingtalk: 'https://open-dev.dingtalk.com/',
  slack: 'https://api.slack.com/apps',
  discord: 'https://discord.com/developers/applications',
  wecom: 'https://work.weixin.qq.com/wework_admin/frame#apps',
  wecom_aibot: 'https://work.weixin.qq.com/wework_admin/frame#apps',
  teams: 'https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps',
  line: 'https://developers.line.biz/console/',
  qq: 'https://q.qq.com/',
  googlechat: 'https://console.cloud.google.com/',
  github: 'https://github.com/settings/tokens',
};

function CredentialGuide({ channel, t }: { channel: string; t: (key: string) => string }) {
  if (!CHANNELS_WITH_GUIDE.has(channel)) return null;
  const guideKey = `credentialGuide${channel.charAt(0).toUpperCase()}${channel.slice(1).replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())}`;
  const url = DEVELOPER_PORTAL_URLS[channel];
  return (
    <p className="text-xs text-muted-foreground/70 px-1">
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
          {t(guideKey)} ↗
        </a>
      ) : (
        t(guideKey)
      )}
    </p>
  );
}

// ─── Channel config renderer ─────────────────────────────────────────

function ChannelConfigPanel({
  channel,
  waStatus,
  waLoading,
  onRefreshWa,
  t,
}: {
  channel: string;
  waStatus: WhatsAppCardProps['waStatus'];
  waLoading: boolean;
  onRefreshWa: () => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  switch (channel) {
    case 'whatsapp':
      return <WhatsAppCard waStatus={waStatus} loading={waLoading} onRefresh={onRefreshWa} t={t} />;
    case 'wechat':
      return <WeChatConfigCard />;
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

// ─── Main Section ────────────────────────────────────────────────────

const CHANNEL_STORAGE_KEY = 'myrm-selected-channel';
const DEFAULT_CHANNEL = isSandbox() ? 'feishu' : 'whatsapp';

export default function ChannelsSection() {
  const t = useTranslations('channels');
  const state = useChannelsState(t);
  const ingressSnapshot = useIngressRequirement();
  const channelEntries = buildChannelEntries(t, isSandbox());
  const [selectedChannel, _setSelectedChannel] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_CHANNEL;
    const stored = localStorage.getItem(CHANNEL_STORAGE_KEY);
    return stored && channelEntries.some((e) => e.id === stored) ? stored : DEFAULT_CHANNEL;
  });
  const setSelectedChannel = useCallback((v: SetStateAction<string>) => {
    _setSelectedChannel((prev) => {
      const next = typeof v === 'function' ? v(prev) : v;
      try {
        localStorage.setItem(CHANNEL_STORAGE_KEY, next);
      } catch {
        /* quota exceeded */
      }
      return next;
    });
  }, []);

  const groupCountByChannel = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const g of state.groups) {
      counts[g.channel] = (counts[g.channel] ?? 0) + 1;
    }
    return counts;
  }, [state.groups]);

  const isChannelEffectivelyEnabled = useCallback(
    (ch: string) => {
      const status = state.channelStatuses[ch];
      if (!status || status === 'disabled' || status === 'unavailable') return false;
      if (ch === 'whatsapp') return !!state.waStatus?.connected;
      if (QR_LOGIN_CHANNELS.has(ch)) {
        return status === 'running' || status === 'running_idle';
      }
      return true;
    },
    [state.channelStatuses, state.waStatus?.connected],
  );

  const renderChannelDetail = useCallback(
    (ch: string) => {
      const status = state.channelStatuses[ch];
      const effectivelyEnabled = isChannelEffectivelyEnabled(ch);

      return (
        <div className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <span className="text-sm text-muted-foreground">
              {!status
                ? t(getChannelNotConfiguredKey(ch))
                : status === 'unavailable'
                  ? t('channelSdkUnavailable')
                  : status === 'disabled'
                    ? t('channelDisabled')
                    : !effectivelyEnabled
                      ? t(getChannelNotConfiguredKey(ch))
                      : t('channelEnabled')}
            </span>
            <Switch
              checked={effectivelyEnabled}
              onCheckedChange={(checked) => state.handleChannelToggle(ch, checked)}
              disabled={!status || status === 'unavailable' || state.togglingChannel === ch}
            />
          </div>
          <ChannelIssueBanner
            issues={state.channelIssues[ch] ?? []}
            channelName={ch}
            onInstalled={state.fetchChannelStatuses}
          />
          {ingressSnapshot?.channels[ch] ? (
            <ChannelIngressBadge mode={ingressSnapshot.channels[ch]} />
          ) : null}
          <CredentialGuide channel={ch} t={t} />
          {status && status !== 'disabled' && status !== 'unavailable' && (
            <ChannelConfigPanel
              channel={ch}
              waStatus={state.waStatus}
              waLoading={state.waLoading}
              onRefreshWa={() => state.fetchWhatsAppStatus(true)}
              t={t}
            />
          )}
          {CHANNELS_WITH_GROUPS.has(ch) && (
            <GroupManager
              groups={state.groups}
              channelFilter={ch}
              channelStatus={state.channelStatuses[ch]}
              isChannelConnected={ch === 'whatsapp' ? state.waStatus?.connected : undefined}
              loading={state.groupsLoading}
              groupPolicy={state.channelOverrides[ch]?.groupPolicy ?? state.groupPolicy}
              onToggle={state.handleGroupToggle}
              onRefresh={state.handleGroupsRefresh}
              refreshing={state.groupsRefreshing}
              freeResponseChats={state.freeResponseChats}
              onFreeResponseToggle={state.handleFreeResponseToggle}
              t={t}
            />
          )}
          <ChannelPolicyOverride
            channel={ch}
            globalDmPolicy={state.dmPolicy}
            globalGroupPolicy={state.groupPolicy}
            globalGroupTrigger={state.groupTrigger}
            overrides={state.channelOverrides[ch]}
            onOverride={state.handleChannelOverride}
            pairings={state.pairings}
            pairingsLoading={state.pairingsLoading}
            onAddPairing={state.handleAddPairing}
            onDeletePairing={state.handleDeletePairing}
            onUpdatePairingStatus={state.handleUpdatePairingStatus}
            onUpdatePairingDisplayName={state.handleUpdatePairingDisplayName}
            saving={state.policySaving}
            t={t}
          />
        </div>
      );
    },
    [state, t, isChannelEffectivelyEnabled, ingressSnapshot],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Navigation className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-base font-semibold">{t('sectionTitle')}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{t('sectionDesc')}</p>
      {isSandbox() && (
        <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          {t('saasChannelInfo')}
        </p>
      )}

      <SettingsSection title={t('channelConfigTitle')} description={t('channelConfigDesc')}>
        <div className="flex flex-col lg:flex-row gap-6 lg:min-h-[400px]">
          <div className="w-full lg:w-48 flex-shrink-0">
            <ChannelList
              channels={channelEntries}
              selectedId={selectedChannel}
              onSelect={setSelectedChannel}
              statuses={state.channelStatuses}
              activities={state.channelActivities}
              issueCountByChannel={Object.fromEntries(
                Object.entries(state.channelIssues).map(([k, v]) => [k, (v as ChannelIssue[]).length]),
              )}
              groupCountByChannel={groupCountByChannel}
              renderDetail={renderChannelDetail}
              t={t}
            />
          </div>
          <div className="hidden lg:block flex-1 min-w-0">{renderChannelDetail(selectedChannel)}</div>
        </div>
      </SettingsSection>

      <SettingsSection title={t('policyTitle')} description={t('policyDesc')} data-section="policy">
        <PolicySelector
          dmPolicy={state.dmPolicy}
          groupPolicy={state.groupPolicy}
          groupTrigger={state.groupTrigger}
          onDmPolicyChange={state.handleDmPolicyChange}
          onGroupPolicyChange={state.handleGroupPolicyChange}
          onGroupTriggerChange={state.handleGroupTriggerChange}
          saving={state.policySaving}
          t={t}
        />
      </SettingsSection>

      <SettingsSection title={t('reactionTitle')} description={t('reactionDesc')}>
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {(
              [
                { value: 'off', label: t('reactionOff'), desc: t('reactionOffDesc') },
                { value: 'simple', label: t('reactionSimple'), desc: t('reactionSimpleDesc') },
                { value: 'full', label: t('reactionFull'), desc: t('reactionFullDesc') },
              ] as const
            ).map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => state.handleReactionLevelChange(opt.value)}
                className={`flex flex-col items-center gap-1 rounded-lg border px-4 py-2 transition-all duration-200 ${
                  state.reactionLevel === opt.value
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/30'
                    : 'border-border hover:border-primary/50 hover:bg-accent/50'
                }`}
              >
                <span className="text-sm font-medium">{opt.label}</span>
                <span className="text-xs text-muted-foreground">{opt.desc}</span>
              </button>
            ))}
          </div>

          {state.reactionLevel === 'full' && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">{t('processingEmojiLabel')}</p>
              <div className="flex flex-wrap gap-2">
                {['👀', '🤔', '⏳', '💭', '🧠', '✨'].map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    onClick={() => state.handleProcessingEmojiChange(emoji)}
                    className={`h-10 w-10 rounded-lg border text-lg transition-all duration-200 ${
                      state.processingEmoji === emoji
                        ? 'border-primary bg-primary/10 ring-2 ring-primary/30'
                        : 'border-border hover:border-primary/50 hover:bg-accent/50'
                    }`}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
          )}

          {state.reactionLevel !== 'off' && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">{t('completionEmojiLabel')}</p>
              <div className="flex flex-wrap gap-2">
                {['✅', '👍', '🎉', '✨', '💯', '🙌'].map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    onClick={() => state.handleCompletionEmojiChange(emoji)}
                    className={`h-10 w-10 rounded-lg border text-lg transition-all duration-200 ${
                      state.completionEmoji === emoji
                        ? 'border-primary bg-primary/10 ring-2 ring-primary/30'
                        : 'border-border hover:border-primary/50 hover:bg-accent/50'
                    }`}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
          )}

          {state.reactionLevel !== 'off' && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">{t('failureEmojiLabel')}</p>
              <div className="flex flex-wrap gap-2">
                {['❌', '⚠️', '💔', '🚫', '⛔', '😵'].map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    onClick={() => state.handleFailureEmojiChange(emoji)}
                    className={`h-10 w-10 rounded-lg border text-lg transition-all duration-200 ${
                      state.failureEmoji === emoji
                        ? 'border-primary bg-primary/10 ring-2 ring-primary/30'
                        : 'border-border hover:border-primary/50 hover:bg-accent/50'
                    }`}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </SettingsSection>
    </div>
  );
}
