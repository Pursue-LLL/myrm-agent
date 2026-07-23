'use client';

/**
 * [INPUT]
 * @/components/features/settings/sections/integration/channels/useChannelRouting (POS: Channel routing state hook)
 * @/components/features/settings/sections/integration/channels/ChannelRoutingTopicRow (POS: Topic binding row UI)
 * @/components/features/memory/SharedContextTargetBinding (POS: Shared Context runtime binding component)
 *
 * [OUTPUT]
 * ChannelRoutingSection: Channel-level Agent routing, thread sharing, and Shared Context binding UI.
 *
 * [POS]
 * Settings section for configuring connected channel routing and inherited Shared Contexts.
 */

import { useTranslations, useLocale } from 'next-intl';
import { IconPlug, IconAlertCircle, IconLoader } from '@/components/features/icons/PremiumIcons';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import SettingsSection from '../../SettingsSection';
import { SharedContextTargetBinding } from '@/components/features/memory/SharedContextTargetBinding';
import { ChannelRoutingTopicRow } from './ChannelRoutingTopicRow';
import { useChannelRouting } from './useChannelRouting';

export default function ChannelRoutingSection() {
  const t = useTranslations('settings.sections.channelRouting');
  const locale = useLocale();
  const {
    channelBindableAgents,
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
  } = useChannelRouting({
    initialLoadError: t('errors.initialLoad'),
    topicsLoadError: t('errors.topicsLoad'),
    agentBoundToast: t('toasts.agentBound'),
    agentBindError: t('errors.agentBind'),
    threadSharingUpdatedToast: t('toasts.threadSharingUpdated'),
    threadSharingError: t('errors.threadSharing'),
    replyModeUpdatedToast: t('toasts.replyModeUpdated'),
    replyModeError: t('errors.replyMode'),
    draftTimeoutUpdatedToast: t('toasts.draftTimeoutUpdated'),
    draftTimeoutError: t('errors.draftTimeout'),
    globalAgentSetToast: t('toasts.globalAgentSet'),
    globalAgentError: t('errors.globalAgent'),
  });

  if (loadingChannels) {
    return (
      <div className="flex items-center justify-center py-12">
        <IconLoader className="w-8 h-8 animate-spin text-primary/50" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="flex flex-col lg:flex-row gap-6">
          <div className="w-full lg:w-48 flex-shrink-0 border-r pr-4">
            <h3 className="text-sm font-medium mb-3 text-muted-foreground">{t('connectedChannels')}</h3>
            {channels.length === 0 ? (
              <div className="text-sm text-muted-foreground flex items-center gap-2 p-3 bg-muted/30 rounded-lg">
                <IconAlertCircle className="w-4 h-4" />
                {t('noConnectedChannels')}
              </div>
            ) : (
              <div className="space-y-1">
                {channels.map((channel) => (
                  <button
                    key={channel.name}
                    onClick={() => setSelectedChannel(channel.name)}
                    className={`w-full text-left px-3 py-2 rounded-full text-sm transition-colors ${
                      selectedChannel === channel.name
                        ? 'bg-primary/10 text-primary font-medium'
                        : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <span>{channel.displayName || channel.name}</span>
                    {channel.displayName && channel.displayName !== channel.name ? (
                      <span className="block truncate text-[11px] opacity-70">{channel.name}</span>
                    ) : null}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="flex-1 min-w-0">
            {selectedChannel ? (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b pb-4">
                  <h3 className="text-lg font-medium">
                    {t('routingFor', {
                      channel: selectedChannelStatus?.displayName || selectedChannel,
                    })}
                  </h3>
                </div>

                {loadingTopics ? (
                  <div className="flex items-center justify-center py-12">
                    <IconLoader className="w-6 h-6 animate-spin text-primary/50" />
                  </div>
                ) : (
                  <div className="space-y-6">
                    <SharedContextTargetBinding
                      targetType="channel"
                      targetId={selectedChannel}
                      targetLabel={t('sharedContexts.targetLabel')}
                      className="bg-muted/20"
                    />

                    <div className="bg-muted/30 p-4 rounded-lg border border-border/50">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <h4 className="font-medium text-sm">{t('globalDefaultAgent')}</h4>
                          <p className="text-xs text-muted-foreground">{t('globalDefaultAgentDesc')}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          {saving === 'global' && <IconLoader className="w-4 h-4 animate-spin text-primary/50" />}
                          <select
                            value={globalAgentId || 'none'}
                            onChange={(event) => handleSetGlobalAgent(event.target.value)}
                            disabled={saving === 'global'}
                            className="bg-background border border-input rounded-full text-sm px-3 py-1.5 focus:ring-2 focus:ring-primary/20 outline-none"
                          >
                            <option value="none">{t('noDefaultAgent')}</option>
                            {channelBindableAgents.map((agent) => (
                              <option key={agent.id} value={agent.id}>
                                {getBuiltinAgentName(agent.id, agent.name, locale)}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </div>

                    <div>
                      <h4 className="font-medium text-sm mb-3">{t('topicBindings')}</h4>
                      {topics.length === 0 ? (
                        <div className="text-sm text-muted-foreground p-4 bg-muted/20 rounded-lg border border-dashed text-center">
                          {t('noActiveTopics')}
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {topics.map((topic) => (
                            <ChannelRoutingTopicRow
                              key={topic.topicId}
                              topic={topic}
                              agents={channelBindableAgents}
                              isSaving={saving === topic.topicId}
                              onBindTopic={handleBindTopic}
                              onSetThreadSharingMode={handleSetThreadSharingMode}
                              onSetReplyMode={handleSetReplyMode}
                              onSetDraftTimeout={handleSetDraftTimeout}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full min-h-[200px] text-muted-foreground flex-col gap-2">
                <IconPlug className="w-8 h-8 opacity-20" />
                <p>{t('selectChannelPrompt')}</p>
              </div>
            )}
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
