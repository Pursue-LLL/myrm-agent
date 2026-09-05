import MessageInput from './MessageInput';
import NewTaskWorkContextCard from './NewTaskWorkContextCard';
import CompanionWidget from '../companion/CompanionWidget';
import NoProviderBanner from './NoProviderBanner';
import { useTranslations } from 'next-intl';
import React, { useMemo } from 'react';
import AgentConfigPanel from './agent-config-panel/AgentConfigPanel';
import SamplePrompts from './SamplePrompts';
import ConversationRecallHint from './ConversationRecallHint';
import MigrationDiscoveryBanner from './MigrationDiscoveryBanner';
import GrowingLoopDiscoveryChip from './GrowingLoopDiscoveryChip';
import MemoryHygieneDiscoverChip from './MemoryHygieneDiscoverChip';
import { ModelOrchestrationPlaybookChip, ModelOrchestrationPlaybookDialog } from './playbook';
import FeaturedExpertChips from './FeaturedExpertChips';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import WorkUnitBalanceBar from '@/components/billing/WorkUnitBalanceBar';
import { useChatTurnPrewarm } from '@/hooks/chat/useChatTurnPrewarm';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';
import { useShallow } from 'zustand/react/shallow';
import { isSmartRoutingActive } from '@/lib/model-binding';
import { Sparkles } from 'lucide-react';

const EmptyChat = React.memo(() => {
  const t = useTranslations('chat');
  const [playbookOpen, setPlaybookOpen] = React.useState(false);
  const isCompanionEnabled = useFeatureGateStore((s) => s.isEnabled('companion_mode'));
  useChatTurnPrewarm({ autoOnMount: true });

  const { actionMode, agentConfig } = useChatStore(
    useShallow((s) => ({
      actionMode: s.actionMode,
      agentConfig: s.agentConfig,
    })),
  );

  const defaultModelConfig = useProviderStore((s) => s.defaultModelConfig);

  const isSmartRouting = useMemo(
    () => isSmartRoutingActive(actionMode, agentConfig, defaultModelConfig),
    [actionMode, agentConfig, defaultModelConfig],
  );

  const title = t('researchBegins');

  return (
    <div className="relative min-h-screen overflow-visible">
      <div className="flex flex-col items-center max-w-screen-md lg:max-w-[820px] mx-auto px-4 pt-[20vh] pb-4 space-y-6">
        <h2 className="text-black/70 dark:text-white/70 text-3xl font-medium">{title}</h2>
        <NoProviderBanner />
        <div className="flex flex-col items-center gap-2 w-full">
          <WorkUnitBalanceBar />
          {isSmartRouting && (
            <button
              type="button"
              onClick={() => setPlaybookOpen(true)}
              data-testid="smart-routing-narrative-badge"
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 text-xs font-medium border border-emerald-500/20 hover:bg-emerald-500/20 transition-all cursor-pointer shadow-2xs group"
              title={t('smartRoutingBadgeClickHint')}
            >
              <Sparkles className="w-3.5 h-3.5 shrink-0 group-hover:scale-110 transition-transform" />
              <span>{t('smartRoutingBadge')}</span>
              <span className="text-[10px] opacity-75 underline ml-1">{t('smartRoutingBadgeAction')}</span>
            </button>
          )}
        </div>
        <div className="flex items-end gap-2 w-full">
          {isCompanionEnabled && <CompanionWidget />}
          <div className="flex-1 min-w-0">
            <MessageInput loading={false} hideWorkspacePicker />
          </div>
        </div>

        <NewTaskWorkContextCard />

        <FeaturedExpertChips />

        <MigrationDiscoveryBanner />

        <GrowingLoopDiscoveryChip />

        <MemoryHygieneDiscoverChip />

        <ModelOrchestrationPlaybookChip />

        <ConversationRecallHint />

        <SamplePrompts />
      </div>

      {/* Full-width bleed section — avoids narrow-column + overflow-x-hidden clipping the ink background */}
      <section className="relative w-full overflow-visible pb-8">
        <div className="max-w-screen-md lg:max-w-[820px] mx-auto px-4">
          <AgentConfigPanel className="mt-4" />
        </div>
      </section>

      <ModelOrchestrationPlaybookDialog open={playbookOpen} onOpenChange={setPlaybookOpen} />
    </div>
  );
});

EmptyChat.displayName = 'EmptyChat';

export default EmptyChat;
