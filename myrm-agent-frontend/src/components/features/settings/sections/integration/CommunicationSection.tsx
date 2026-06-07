'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { MessageSquare, Waypoints, Mic } from 'lucide-react';
import { defaultSubTabResolver, useSettingsSubTabUrl } from '@/hooks/useSettingsSubTabUrl';
import ChannelsSection from './channels/ChannelsSection';
import ChannelRoutingSection from './channels/ChannelRoutingSection';
import VoiceSection from './channels/VoiceSection';

const CommunicationSection = memo(() => {
  const t = useTranslations('settings');
  const tComm = useTranslations('settings.communication.desc');
  const searchParams = useSearchParams();
  const { handleTabChange: syncTabChange } = useSettingsSubTabUrl('channels');

  const [activeTab, setActiveTab] = useState<string>('channels');

  useEffect(() => {
    const sub = searchParams.get('sub');
    if (sub === 'routing' || sub === 'channelRouting') {
      setActiveTab('routing');
    } else if (sub === 'voice') {
      setActiveTab('voice');
    } else {
      setActiveTab('channels');
    }
  }, [searchParams]);

  const handleTabChange = (value: string) => {
    syncTabChange(value, setActiveTab, defaultSubTabResolver('channels'));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{t('menu.channels')}</h1>
        <p className="text-sm text-muted-foreground">
          {activeTab === 'channels'
            ? tComm('channels')
            : activeTab === 'routing'
              ? tComm('routing')
              : tComm('voice')}
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="grid w-full max-w-xl grid-cols-3 bg-secondary/50 backdrop-blur-sm p-1 rounded-xl border border-border/40 mb-6">
          <TabsTrigger
            value="channels"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <MessageSquare className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.channels')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="routing"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Waypoints className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.channelRouting')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="voice"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Mic className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.voice')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="channels" className="focus-visible:outline-none focus-visible:ring-0">
          <ChannelsSection />
        </TabsContent>
        <TabsContent value="routing" className="focus-visible:outline-none focus-visible:ring-0">
          <ChannelRoutingSection />
        </TabsContent>
        <TabsContent value="voice" className="focus-visible:outline-none focus-visible:ring-0">
          <VoiceSection />
        </TabsContent>
      </Tabs>
    </div>
  );
});

CommunicationSection.displayName = 'CommunicationSection';

export default CommunicationSection;
