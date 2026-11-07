'use client';

import { useCallback, useMemo, useState, type SetStateAction } from 'react';
import { useTranslations } from 'next-intl';
import { Navigation } from 'lucide-react';
import SettingsSection from '../../SettingsSection';
import { PolicySelector } from './DmPolicySelector';
import { ChannelPolicyOverride } from './ChannelPolicyOverride';
import { ChannelDataPlaneSection } from './ChannelDataPlaneSection';
import { GroupManager, CHANNELS_WITH_GROUPS } from './GroupManager';
import ChannelList, { buildChannelEntries } from './ChannelList';
import { useChannelsState } from './useChannelsState';
import { type ChannelIssue } from '@/services/channels';
import { Switch } from '@/components/primitives/switch';
import { isSandbox } from '@/lib/deploy-mode';
import { useIngressRequirement } from '@/hooks/billing/useIngressRequirement';
import { ChannelIngressBadge } from './ChannelIngressBadge';
import { ChannelIssueBanner } from './ChannelIssueBanner';
import { ChannelConfigPanel } from './ChannelConfigPanel';

// ─── Channel auth-type classification ────────────────────────────────

const QR_LOGIN_CHANNELS = new Set(['whatsapp', 'wechat']);
const CONNECTION_CONFIG_CHANNELS = new Set(['onebot', 'irc']);

function getChannelNotConfiguredKey(channel: string): string {
  if (QR_LOGIN_CHANNELS.has(channel)) {
    return 'channelNotConfiguredQr';
  }
  if (CONNECTION_CONFIG_CHANNELS.has(channel)) {
    return 'channelNotConfiguredConnection';
  }
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
  'wechat_official',
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
  wechat_official: 'https://mp.weixin.qq.com/',
  teams: 'https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps',
  line: 'https://developers.line.biz/console/',
  qq: 'https://q.qq.com/',
  googlechat: 'https://console.cloud.google.com/',
  github: 'https://github.com/settings/tokens',
};

function CredentialGuide({ channel, t }: { channel: string; t: (key: string) => string }) {
  if (!CHANNELS_WITH_GUIDE.has(channel)) {
    return null;
  }
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

// ─── Main Section ────────────────────────────────────────────────────

const CHANNEL_STORAGE_KEY = 'myrm-selected-channel';
const DEFAULT_CHANNEL = isSandbox() ? 'feishu' : 'whatsapp';

export default function ChannelsSection() {
  const t = useTranslations('channels');
  const state = useChannelsState(t);
  const ingressSnapshot = useIngressRequirement();
  const channelEntries = buildChannelEntries(t, isSandbox());
  const [selectedChannel, _setSelectedChannel] = useState(() => {
    if (typeof window === 'undefined') {
      return DEFAULT_CHANNEL;
    }
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
      if (!status || status === 'disabled' || status === 'unavailable') {
        return false;
      }
      if (ch === 'whatsapp') {
        return !!state.waStatus?.connected;
      }
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
          {ingressSnapshot?.channels[ch] ? <ChannelIngressBadge mode={ingressSnapshot.channels[ch]} /> : null}
          <CredentialGuide channel={ch} t={t} />
          {status && status !== 'disabled' && status !== 'unavailable' && (
            <ChannelConfigPanel
              channel={ch}
              waStatus={state.waStatus}
              waLoading={state.waLoading}
              onRefreshWa={() => state.fetchWhatsAppStatus(true)}
              onSelectChannel={setSelectedChannel}
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
            onUpdatePairingRole={state.handleUpdatePairingRole}
            onUpdatePairingQuota={state.handleUpdatePairingQuota}
            saving={state.policySaving}
            t={t}
          />
          <ChannelDataPlaneSection channel={ch} />
        </div>
      );
    },
    [state, t, isChannelEffectivelyEnabled, ingressSnapshot, setSelectedChannel],
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

          {state.reactionLevel !== 'off' && (
            <p className="text-xs leading-relaxed text-muted-foreground">{t('reactionPlatformNote')}</p>
          )}
        </div>
      </SettingsSection>
    </div>
  );
}
