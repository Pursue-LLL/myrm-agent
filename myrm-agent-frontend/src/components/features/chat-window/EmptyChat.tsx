import MessageInput from './MessageInput';
import CompanionWidget from '../companion/CompanionWidget';
import { useTranslations } from 'next-intl';
import React from 'react';
import AgentConfigPanel from './agent-config-panel/AgentConfigPanel';
import SamplePrompts from './SamplePrompts';
import CompetitorMigrationBanner from './CompetitorMigrationBanner';
import { TaskAdaptivePreview } from './TaskAdaptivePreview';
import useChatStore from '@/store/useChatStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { toast } from 'sonner';
import WorkUnitBalanceBar from '@/components/billing/WorkUnitBalanceBar';

const EmptyChat = React.memo(() => {
  const t = useTranslations('chat');
  const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);
  const actionMode = useChatStore((state) => state.actionMode);
  const agentConfig = useChatStore((state) => state.agentConfig);
  const isCompanionEnabled = useFeatureGateStore((s) => s.isEnabled('companion_mode'));

  const title = agentConfig?.agentName ? t('agentReady', { agentName: agentConfig.agentName }) : t('researchBegins');

  return (
    <div className="relative min-h-screen">
      <div className="flex flex-col items-center max-w-screen-md lg:max-w-[820px] mx-auto px-4 pt-[20vh] pb-8 space-y-6">
        <h2 className="text-black/70 dark:text-white/70 text-3xl font-medium">{title}</h2>
        <div className="flex justify-center w-full">
          <WorkUnitBalanceBar />
        </div>
        <div className="flex items-end gap-2 w-full">
          {isCompanionEnabled && <CompanionWidget />}
          <div className="flex-1 min-w-0">
            <MessageInput loading={false} />
          </div>
        </div>

        <CompetitorMigrationBanner />

        <SamplePrompts />

        {actionMode === 'agent' && (
          <TaskAdaptivePreview
            className="mt-2 w-full"
            onApplyContext={(digest) => {
              updateAgentConfig({ taskAdaptiveDigest: digest as unknown as Record<string, unknown> });
              toast.success('Kanban JIT Context Applied', {
                description: 'Historical evidence has been injected into the next execution.',
                duration: 3000,
              });
            }}
          />
        )}

        <AgentConfigPanel className="mt-4" />
      </div>
    </div>
  );
});

EmptyChat.displayName = 'EmptyChat';

export default EmptyChat;
