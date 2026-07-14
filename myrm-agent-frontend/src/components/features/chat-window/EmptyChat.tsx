import MessageInput from './MessageInput';
import CompanionWidget from '../companion/CompanionWidget';
import NoProviderBanner from './NoProviderBanner';
import { useTranslations } from 'next-intl';
import React from 'react';
import AgentConfigPanel from './agent-config-panel/AgentConfigPanel';
import SamplePrompts from './SamplePrompts';
import MigrationDiscoveryBanner from './MigrationDiscoveryBanner';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import WorkUnitBalanceBar from '@/components/billing/WorkUnitBalanceBar';

const EmptyChat = React.memo(() => {
  const t = useTranslations('chat');
  const isCompanionEnabled = useFeatureGateStore((s) => s.isEnabled('companion_mode'));

  const title = t('researchBegins');

  return (
    <div className="relative min-h-screen overflow-visible">
      <div className="flex flex-col items-center max-w-screen-md lg:max-w-[820px] mx-auto px-4 pt-[20vh] pb-4 space-y-6">
        <h2 className="text-black/70 dark:text-white/70 text-3xl font-medium">{title}</h2>
        <NoProviderBanner />
        <div className="flex justify-center w-full">
          <WorkUnitBalanceBar />
        </div>
        <div className="flex items-end gap-2 w-full">
          {isCompanionEnabled && <CompanionWidget />}
          <div className="flex-1 min-w-0">
            <MessageInput loading={false} />
          </div>
        </div>

        <MigrationDiscoveryBanner />

        <SamplePrompts />
      </div>

      {/* Full-width bleed section — avoids narrow-column + overflow-x-hidden clipping the ink background */}
      <section className="relative w-full overflow-visible pb-8">
        <div className="max-w-screen-md lg:max-w-[820px] mx-auto px-4">
          <AgentConfigPanel className="mt-4" />
        </div>
      </section>
    </div>
  );
});

EmptyChat.displayName = 'EmptyChat';

export default EmptyChat;
